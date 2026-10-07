"""Existing worker adapter to the frozen Agent entry point; no scoring/prompt copy."""
from sqlalchemy import select

from app.agents.context import select_context
from app.agents.contracts import AgentInput, AgentOutput, AnalysisResult
from app.agents.orchestrator import analyze_agent
from app.agents.providers.real import _legacy_usage
from app.core.errors import AppError
from app.integrations.telegram.models import TelegramReceipt
from app.models import Message


def prepare_work(session, run, messages, config):
    receipt = session.scalar(select(TelegramReceipt).where(TelegramReceipt.run_id == run.id))
    if receipt is None or config.provider_mode != "real":
        raise AppError("invalid_telegram_job", "Telegram job requires a receipt and real provider mode", 503)
    target = next(m for m in messages if m.id == receipt.message_id)
    original = session.get(Message, target.id)
    allowed = set(session.scalars(select(Message.id).where(Message.batch_id == run.batch_id,
        Message.conversation_id == target.conversation_id, Message.timestamp <= target.timestamp,
        Message.created_at <= original.created_at)).all())
    context = select_context(target, [m for m in messages if m.id in allowed], config)
    snapshot = run.product_snapshot
    inputs = AgentInput(product={"id": run.product_id, **{k: snapshot[k] for k in ("name", "description", "target_customer")}},
        message={"id": target.id, "content": target.content, "author": target.author,
            "timestamp": target.timestamp, "conversation_id": target.conversation_id,
            "reply_to_message_id": next((m.id for m in context if m.external_id == target.reply_to_external_id), None)},
        context_messages=[{"id": m.id, "content": m.content, "author": m.author, "timestamp": m.timestamp} for m in context],
        metadata={"run_id": run.id, "provider_mode": "real"})
    receipt.agent_input = inputs.model_dump(mode="json")
    return inputs, target


def analyze_work(inputs: AgentInput):
    output: AgentOutput = analyze_agent(inputs)
    q, s = output.qualification, output.scoring
    result = AnalysisResult(is_candidate=output.screening.is_candidate,
        screening_reason=output.screening.reason, reason=q.need if q else output.screening.reason,
        intent=q.intent if q else None, need=q.need if q else None,
        signals={name: getattr(q, name) for name in ("purchase_intent", "product_fit", "need_strength", "urgency", "confidence", "response_opportunity")} if q else None,
        evidence=[{"message_id": e.message_id, "quote": e.quote} for e in q.evidence] if q else [],
        limitations=q.limitations if q else [], lead_score=s.score if s else None,
        decision=s.decision.value.lower() if s else "ignore", decision_reason=output.decision_reason,
        context_message_ids=[m.id for m in inputs.context_messages], provider_mode="real",
        # Legacy columns cannot hold NULL yet; the exact nullable public versions
        # live in the authoritative AgentOutput snapshot, never these adapters.
        prompt_version=output.prompt_version or "not_executed",
        scoring_version=output.scoring_version or "not_executed")
    return result, _legacy_usage(output.usage), output
