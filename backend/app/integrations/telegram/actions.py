"""Authorized draft/read/send operations. Provider calls run outside DB transactions."""
import json
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.agents.contracts import AgentInput, AgentOutput
from app.agents.providers.base import ProviderError
from app.agents.providers.real import _legacy_usage
from app.agents.reply import generate_suggested_reply
from app.core.errors import AppError
from app.integrations.telegram.client import TelegramError
from app.integrations.telegram.models import TelegramChatMapping, TelegramDelivery, TelegramReceipt
from app.integrations.telegram.normalization import TelegramMessage
from app.integrations.telegram.schemas import DeliveryOut, TelegramLeadOut
from app.models import Analysis, AnalysisRun, Message, Usage, utcnow
from app.services.analysis_service import validate_key


def owned(session, user_id: str, analysis_id: str):
    analysis = session.get(Analysis, analysis_id)
    if analysis is None:
        raise AppError("not_found", "Lead does not exist", 404)
    receipt = session.scalar(select(TelegramReceipt).where(TelegramReceipt.run_id == analysis.run_id,
        TelegramReceipt.message_id == analysis.message_id).with_for_update())
    if receipt is None:
        raise AppError("not_telegram", "Lead does not originate from Telegram", 409)
    mapping = session.get(TelegramChatMapping, receipt.mapping_id)
    run = session.get(AnalysisRun, analysis.run_id)
    if mapping is None or mapping.owner_user_id != user_id:
        raise AppError("not_found", "Lead does not exist", 404)
    if run is None or run.user_id != user_id:
        raise AppError("not_found", "Lead does not exist", 404)
    if not mapping.enabled or mapping.product_id != run.product_id:
        raise AppError("telegram_mapping_disabled", "Telegram mapping is unavailable", 409)
    if analysis.status != "completed" or receipt.agent_input is None or receipt.agent_output is None:
        raise AppError("analysis_unavailable", "Successful Agent analysis is required", 409)
    return analysis, receipt, run


def _delivery(session, analysis_id):
    delivery = session.scalar(select(TelegramDelivery).where(
        TelegramDelivery.analysis_id == analysis_id,
    ).with_for_update())
    if delivery is None:
        try:
            with session.begin_nested():
                delivery = TelegramDelivery(analysis_id=analysis_id)
                session.add(delivery)
                session.flush()
        except IntegrityError:
            delivery = session.scalar(select(TelegramDelivery).where(TelegramDelivery.analysis_id == analysis_id))
            if delivery is None:
                raise AppError("delivery_conflict", "Reload this lead before sending", 409) from None
    return delivery


def _source(session, receipt):
    try:
        source = TelegramMessage.model_validate_json(json.dumps(receipt.source_metadata))
        message = session.get(Message, receipt.message_id)
        mapping = session.get(TelegramChatMapping, receipt.mapping_id)
        if (source.chat_id != receipt.telegram_chat_id or source.message_id != receipt.telegram_message_id
                or source.chat_id != mapping.telegram_chat_id or source.text != message.content
                or source.external_id != message.external_id or source.conversation_id != message.conversation_id):
            raise ValueError("source mismatch")
        return source
    except (ValueError, TypeError, AttributeError):
        raise AppError("telegram_source_unavailable", "Original Telegram metadata is missing or inconsistent", 409) from None


def lead_view(session, user_id, analysis_id):
    analysis, receipt, run = owned(session, user_id, analysis_id)
    delivery = session.scalar(select(TelegramDelivery).where(TelegramDelivery.analysis_id == analysis.id))
    state = DeliveryOut() if delivery is None else DeliveryOut(status=delivery.state,
        telegram_message_id=delivery.sent_message_id, failure_category=delivery.failure_category,
        delivery_uncertain=delivery.delivery_uncertain, draft_busy=delivery.draft_busy,
        approved_text=delivery.approved_text, failure_http_status=delivery.failure_http_status,
        retry_after_at=delivery.retry_after_at)
    return TelegramLeadOut(id=analysis.id, run_id=run.id, product_id=run.product_id, message_id=analysis.message_id,
        original_message=_source(session, receipt),
        context=AgentInput.model_validate(receipt.agent_input).context_messages,
        analysis=AgentOutput.model_validate(receipt.agent_output), delivery=state)


def draft_reply(session, user_id, analysis_id, *, regenerate=False):
    _, receipt, _ = owned(session, user_id, analysis_id)
    inputs, output = AgentInput.model_validate(receipt.agent_input), AgentOutput.model_validate(receipt.agent_output)
    if output.qualification is None or output.scoring is None or output.scoring.decision.value == "IGNORE":
        raise AppError("reply_not_eligible", "A qualified REVIEW or RESPOND lead is required for drafting", 409)
    if output.suggested_reply is not None and not regenerate:
        return lead_view(session, user_id, analysis_id)
    delivery = _delivery(session, analysis_id)
    if delivery.draft_busy or delivery.state == "sending":
        raise AppError("reply_busy", "A reply operation is already in progress", 409)
    claimed = session.execute(update(TelegramDelivery).where(TelegramDelivery.id == delivery.id,
        TelegramDelivery.draft_busy.is_(False), TelegramDelivery.state != "sending").values(draft_busy=True),
        execution_options={"synchronize_session": False}).rowcount
    if not claimed:
        session.rollback()
        raise AppError("reply_busy", "A reply operation is already in progress", 409)
    receipt_id = receipt.id
    session.commit()
    session.expire_all()
    prior = len(output.usage)
    try:
        # Existing grounded Agent entry point; no qualification rerun or new prompt.
        generated = generate_suggested_reply(inputs, output)
    except Exception as exc:
        delivery = session.scalar(select(TelegramDelivery).where(TelegramDelivery.analysis_id == analysis_id))
        delivery.draft_busy = False
        if isinstance(exc, ProviderError):
            _save_usage(session, analysis_id, inputs.metadata.run_id, inputs.message.id, exc.usage[prior:])
            receipt = session.get(TelegramReceipt, receipt_id)
            receipt.agent_output = output.model_copy(update={"usage": exc.usage}).model_dump(mode="json")
        session.commit()
        if isinstance(exc, ValueError):
            raise AppError("reply_not_eligible", "Stored analysis is not eligible for grounded drafting", 409) from None
        raise AppError("reply_generation_failed", "Suggested reply generation failed; nothing was sent", 502) from None
    receipt = session.get(TelegramReceipt, receipt_id)
    receipt.agent_output = generated.model_dump(mode="json")
    delivery = session.scalar(select(TelegramDelivery).where(TelegramDelivery.analysis_id == analysis_id))
    delivery.draft_busy = False
    _save_usage(session, analysis_id, inputs.metadata.run_id, inputs.message.id, generated.usage[prior:])
    session.commit()
    return lead_view(session, user_id, analysis_id)


def _save_usage(session, analysis_id, run_id, message_id, records):
    run = session.get(AnalysisRun, run_id)
    for event in _legacy_usage(records):
        session.add(Usage(analysis_id=analysis_id, run_id=run_id,
            run_attempt_no=run.attempt_no, message_id=message_id, **event.model_dump()))


def send_reply(session, user_id, analysis_id, text, client, *, idempotency_key=None):
    if idempotency_key is not None:
        validate_key(idempotency_key)
    key_hash = hashlib.sha256((idempotency_key or str(uuid4())).encode()).hexdigest()
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    _, receipt, _ = owned(session, user_id, analysis_id)
    source = _source(session, receipt)
    delivery = _delivery(session, analysis_id)
    for attempt in delivery.send_history or []:
        if attempt.get("key_hash") == key_hash:
            if attempt.get("text_hash") != text_hash:
                raise AppError("idempotency_conflict", "Send key was used with different reply text", 409)
            return lead_view(session, user_id, analysis_id)
    if delivery.state == "sent":
        if delivery.approved_text != text:
            raise AppError("already_sent", "This lead already has a delivered reply", 409)
        return lead_view(session, user_id, analysis_id)
    if delivery.state == "sending" or delivery.delivery_uncertain or delivery.draft_busy:
        raise AppError("delivery_requires_review", "Delivery is in progress or uncertain; verify it before another send", 409)
    if delivery.retry_after_at and delivery.retry_after_at > utcnow():
        raise AppError("telegram_retry_after", "Telegram rate limit is still active; wait before retrying", 409)
    history = [*(delivery.send_history or []), {"key_hash": key_hash, "text_hash": text_hash,
        "started_at": utcnow().isoformat(), "status": "sending"}]
    # The compare-and-swap claim keeps concurrent approvals from sending twice.
    claimed = session.execute(update(TelegramDelivery).where(
        TelegramDelivery.id == delivery.id,
        TelegramDelivery.state.in_(["not_sent", "failed"]),
        TelegramDelivery.delivery_uncertain.is_(False),
        TelegramDelivery.draft_busy.is_(False),
    ).values(state="sending", approved_text=text, approved_by=user_id,
        failure_category=None, failure_http_status=None, retry_after_at=None,
        send_history=history), execution_options={"synchronize_session": False}).rowcount
    if not claimed:
        session.rollback()
        session.expire_all()
        current = session.scalar(select(TelegramDelivery).where(TelegramDelivery.analysis_id == analysis_id))
        if current and any(event.get("key_hash") == key_hash and event.get("text_hash") == text_hash
                           for event in (current.send_history or [])):
            return lead_view(session, user_id, analysis_id)
        raise AppError("delivery_requires_review", "Another reply operation claimed this lead; reload before sending", 409)
    session.commit()
    try:
        sent_id = client.send_message(chat_id=source.chat_id, message_id=source.message_id,
            text=text, thread_id=source.message_thread_id)
    except TelegramError as exc:
        session.expire_all()
        delivery = session.scalar(select(TelegramDelivery).where(TelegramDelivery.analysis_id == analysis_id))
        delivery.state, delivery.failure_category = "failed", exc.category
        delivery.failure_http_status = exc.http_status
        delivery.delivery_uncertain = exc.delivery_uncertain
        if exc.retry_after:
            try:
                delivery.retry_after_at = utcnow() + timedelta(seconds=exc.retry_after)
            except OverflowError:
                delivery.retry_after_at = datetime.max.replace(tzinfo=timezone.utc)
        _finish_send(delivery)
        session.commit()
        raise exc from None
    except Exception:
        session.expire_all()
        delivery = session.scalar(select(TelegramDelivery).where(TelegramDelivery.analysis_id == analysis_id))
        delivery.state, delivery.failure_category, delivery.delivery_uncertain = "failed", "local_failure", True
        _finish_send(delivery)
        session.commit()
        raise AppError("telegram_delivery_failed", "Delivery could not be confirmed; verify before another send", 502) from None
    session.expire_all()
    delivery = session.scalar(select(TelegramDelivery).where(TelegramDelivery.analysis_id == analysis_id))
    delivery.state, delivery.sent_message_id = "sent", sent_id
    _finish_send(delivery)
    session.commit()
    return lead_view(session, user_id, analysis_id)


def _finish_send(delivery):
    history = list(delivery.send_history or [])
    if not history:
        return
    history[-1] = {**history[-1], "status": delivery.state,
        "finished_at": utcnow().isoformat(), "failure_category": delivery.failure_category,
        "http_status": delivery.failure_http_status,
        "retry_after_at": delivery.retry_after_at.isoformat() if delivery.retry_after_at else None,
        "delivery_uncertain": delivery.delivery_uncertain}
    delivery.send_history = history
