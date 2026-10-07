"""Run lifecycle. Explicit retries reuse results; provider calls hold no DB locks."""
import hashlib
from datetime import timedelta

from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError

from app.models import Product, ImportBatch, Message, AnalysisRun, Analysis, Usage, utcnow
from app.schemas.api import ProductOut
from app.core.errors import AppError
from app.core.config import settings
from app.agents.contracts import ProductSnapshot, RunConfig, AnalysisResult
from app.agents.providers.base import ProviderError
from app.agents.pipeline import analyze, get_provider
from app.services.context_service import load_messages
from app.services.ownership_service import owned_run


def validate_key(key):
    if not key.strip() or len(key) > 200:
        raise AppError("invalid_idempotency_key", "Idempotency-Key must contain 1-200 characters")


def create_run(session, payload, key: str, *, commit: bool = True):
    validate_key(key)
    existing = session.scalar(select(AnalysisRun).where(AnalysisRun.idempotency_key == key))
    if existing:
        if existing.product_id != str(payload.product_id) or existing.batch_id != str(payload.batch_id):
            raise AppError("idempotency_conflict", "Key was used with a different payload", 409)
        return existing
    product = session.get(Product, str(payload.product_id))
    batch = session.get(ImportBatch, str(payload.batch_id))
    if product is None or batch is None:
        raise AppError("not_found", "Product or batch does not exist", 404)
    try:
        get_provider(settings().provider_mode)
    except ProviderError:
        raise AppError("provider_configuration_unavailable", "AI provider configuration is unavailable", 503) from None
    snapshot = ProductOut.model_validate(product).model_dump(mode="json", exclude={"id", "created_at"})
    run = AnalysisRun(product_id=product.id, batch_id=batch.id, product_snapshot=snapshot,
        config_snapshot=RunConfig(provider_mode=settings().provider_mode).model_dump(), idempotency_key=key, total_count=batch.row_count)
    try:
        session.add(run)
        session.commit() if commit else session.flush()
    except IntegrityError:
        session.rollback()
        if not commit:
            raise
        # One race lookup, never recursive retries on an unrelated constraint failure.
        existing = session.scalar(select(AnalysisRun).where(AnalysisRun.idempotency_key == key))
        if existing and existing.product_id == str(payload.product_id) and existing.batch_id == str(payload.batch_id):
            return existing
        raise AppError("run_conflict", "Run could not be created; reload before trying again", 409) from None
    return run


def retry_run(session, run_id, user_id, key):
    validate_key(key)
    run = owned_run(session, run_id, user_id)
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    if any(event["key_hash"] == key_hash for event in run.retry_history):
        return run
    if run.status not in {"failed", "partial", "interrupted"}:
        raise AppError("run_not_retryable", "Only failed, partial or interrupted runs can be retried", 409)
    failures = session.scalars(select(Analysis).where(Analysis.run_id == run.id, Analysis.status == "failed")).all()
    completed = session.scalar(select(func.count()).select_from(Analysis).where(Analysis.run_id == run.id, Analysis.status == "completed"))
    if completed >= run.total_count:
        raise AppError("nothing_to_retry", "All messages already have successful results", 409)
    history = [*run.retry_history, {"key_hash": key_hash, "requested_at": utcnow().isoformat(),
        "previous_attempt_no": run.attempt_no, "previous_status": run.status,
        "failures": [{"analysis_id": a.id, "message_id": a.message_id, "failure_category": a.failure_category} for a in failures]}]
    claimed = session.execute(update(AnalysisRun).where(AnalysisRun.id == run.id,
        AnalysisRun.status == run.status, AnalysisRun.attempt_no == run.attempt_no).values(
            status="queued", attempt_no=run.attempt_no + 1, retry_history=history,
            processed_count=completed, failed_count=0, error=None,
            started_at=None, finished_at=None, heartbeat_at=None), execution_options={"synchronize_session": False}).rowcount
    session.commit()
    session.expire_all()
    current = session.get(AnalysisRun, run.id)
    if not claimed and not any(event["key_hash"] == key_hash for event in current.retry_history):
        raise AppError("retry_conflict", "A retry is already in progress; reload the run", 409)
    return current


def failure_details(exc):
    """Allowlisted categories and fixed messages: never persist exception text."""
    if not isinstance(exc, ProviderError):
        return "internal_analysis_failure", "Analysis could not be completed. Retry explicitly; contact support if it persists."
    outcomes = {getattr(event, "outcome", None) for event in exc.usage}
    if "timeout" in outcomes:
        return "provider_timeout", "The AI provider timed out. Your message is saved; you can retry."
    if outcomes & {"invalid_output", "incomplete"}:
        return "invalid_provider_output", "The AI provider returned an unusable response. You can retry."
    if "refused" in outcomes:
        return "provider_refusal", "The AI provider could not qualify this message. Review it before retrying."
    return "provider_failure", "The AI provider is unavailable or rejected the request. Check configuration and retry explicitly."


def recover_interrupted(factory):
    cutoff = utcnow() - timedelta(seconds=settings().heartbeat_timeout_seconds)
    with factory() as session:
        session.execute(update(AnalysisRun).where(AnalysisRun.status == "running",
            (AnalysisRun.heartbeat_at < cutoff) | AnalysisRun.heartbeat_at.is_(None)).values(
                status="interrupted", finished_at=utcnow(), error="Worker heartbeat expired. Retry explicitly; completed results are preserved."))
        session.commit()


def _lease(session, run_id, attempt):
    # The conditional write also serializes result persistence against recovery/retry.
    return bool(session.execute(update(AnalysisRun).where(AnalysisRun.id == run_id,
        AnalysisRun.status == "running", AnalysisRun.attempt_no == attempt).values(heartbeat_at=utcnow()),
        execution_options={"synchronize_session": False}).rowcount)


def _save_result(session, run_id, attempt, message_id, result, usage, category=None, agent_output=None):
    analysis = session.scalar(select(Analysis).where(Analysis.run_id == run_id, Analysis.message_id == message_id))
    if analysis is not None and analysis.status == "completed":
        return
    values = result.model_dump(mode="json")
    if analysis is None:
        analysis = Analysis(run_id=run_id, message_id=message_id, **values)
        session.add(analysis)
    else:
        for name, value in values.items():
            setattr(analysis, name, value)
    analysis.failure_category = category
    session.flush()
    if agent_output is not None:
        from app.integrations.telegram.models import TelegramReceipt
        receipt = session.scalar(select(TelegramReceipt).where(TelegramReceipt.run_id == run_id))
        receipt.agent_output = agent_output.model_dump(mode="json")
    for event in usage:
        session.add(Usage(run_id=run_id, run_attempt_no=attempt, message_id=message_id,
            analysis_id=analysis.id, **event.model_dump()))


def _counts(session, run):
    rows = dict(session.execute(select(Analysis.status, func.count()).where(Analysis.run_id == run.id).group_by(Analysis.status)).all())
    run.failed_count = rows.get("failed", 0)
    run.processed_count = rows.get("completed", 0) + run.failed_count


def process_one(factory, provider_override=None) -> bool:
    with factory() as session:
        run = session.scalar(select(AnalysisRun).where(AnalysisRun.status == "queued").order_by(AnalysisRun.created_at).with_for_update(skip_locked=True).limit(1))
        if run is None:
            return False
        run_id, batch_id, attempt = run.id, run.batch_id, run.attempt_no
        claimed = session.execute(update(AnalysisRun).where(AnalysisRun.id == run_id,
            AnalysisRun.status == "queued", AnalysisRun.attempt_no == attempt).values(
                status="running", started_at=utcnow(), heartbeat_at=utcnow()),
            execution_options={"synchronize_session": False}).rowcount
        session.commit()
        if not claimed:
            return True
    try:
        # Snapshot/config errors are failures too, not exceptions escaping the worker.
        product, config = ProductSnapshot.model_validate(run.product_snapshot), RunConfig.model_validate(run.config_snapshot)
        telegram_run = run.idempotency_key.startswith("telegram:v1:")
        provider = None if telegram_run else provider_override or get_provider(config.provider_mode)
        with factory() as session:
            if not _lease(session, run_id, attempt):
                return True
            messages = load_messages(session, batch_id)
            completed = set(session.scalars(select(Analysis.message_id).where(Analysis.run_id == run_id, Analysis.status == "completed")))
            if telegram_run:
                from app.integrations.telegram.worker_adapter import prepare_work
                telegram_input, telegram_target = prepare_work(session, run, messages, config)
            session.commit()
        for target in ([telegram_target] if telegram_run else messages):
            if str(target.id) in completed:
                continue
            with factory() as session:
                if not _lease(session, run_id, attempt):
                    return True
                session.commit()
            category, agent_output = None, None
            try:
                if telegram_run:
                    from app.integrations.telegram.worker_adapter import analyze_work
                    result, usage, agent_output = analyze_work(telegram_input)
                else:
                    result, usage = analyze(product, target, messages, config, provider)
            except Exception as exc:
                category, reason = failure_details(exc)
                usage = exc.usage if isinstance(exc, ProviderError) else []
                if telegram_run:
                    from app.agents.providers.real import _legacy_usage
                    usage = _legacy_usage(usage)
                result = AnalysisResult(status="failed", is_candidate=True, screening_reason="processing_error",
                    decision=None, reason=reason, provider_mode=config.provider_mode)
            with factory() as session:
                if not _lease(session, run_id, attempt):
                    # A timed-out worker must not replace a new result, but its actual
                    # provider consumption is still accounted for under the old attempt.
                    previous = session.scalar(select(Analysis).where(Analysis.run_id == run_id, Analysis.message_id == str(target.id)))
                    for event in usage:
                        session.add(Usage(run_id=run_id, run_attempt_no=attempt, message_id=str(target.id),
                            analysis_id=previous.id if previous else None, **event.model_dump()))
                    session.commit()
                    return True
                _save_result(session, run_id, attempt, str(target.id), result, usage, category, agent_output)
                _counts(session, session.get(AnalysisRun, run_id))
                session.commit()
        with factory() as session:
            if not _lease(session, run_id, attempt):
                return True
            current = session.get(AnalysisRun, run_id)
            _counts(session, current)
            current.status = "completed" if current.failed_count == 0 else "failed" if current.failed_count == current.total_count else "partial"
            current.error = "Some analyses failed. Open failed results for details and retry explicitly." if current.failed_count else None
            current.finished_at = utcnow()
            session.commit()
    except Exception as exc:
        category, reason = failure_details(exc)
        with factory() as session:
            if not _lease(session, run_id, attempt):
                return True
            # Even pre-provider failures produce visible failed results for saved sources.
            from app.integrations.telegram.models import TelegramReceipt
            receipt = session.scalar(select(TelegramReceipt).where(TelegramReceipt.run_id == run_id))
            ids = [receipt.message_id] if receipt else session.scalars(select(Message.id).where(Message.batch_id == batch_id)).all()
            mode = run.config_snapshot.get("provider_mode") if isinstance(run.config_snapshot, dict) else None
            for message_id in ids:
                result = AnalysisResult(status="failed", is_candidate=True, screening_reason="processing_error",
                    decision=None, reason=reason, provider_mode=mode if mode in {"mock", "real"} else "real")
                _save_result(session, run_id, attempt, message_id, result, [], category)
            current = session.get(AnalysisRun, run_id)
            _counts(session, current)
            current.status, current.error, current.finished_at = "failed", reason, utcnow()
            session.commit()
    return True
