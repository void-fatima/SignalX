import hashlib
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.agents.contracts import AnalysisResult, ProductSnapshot, RunConfig
from app.agents.pipeline import analyze, get_provider
from app.agents.providers.base import ProviderError
from app.core.config import settings
from app.core.errors import AppError
from app.models import Analysis, AnalysisRun, ImportBatch, Message, Product, Usage, utcnow
from app.schemas.api import ProductOut
from app.services.agent_contract_service import build_agent_input, persist_agent_output
from app.services.context_service import load_messages


def validate_key(key: str):
    if not key.strip() or len(key) > 200:
        raise AppError("invalid_idempotency_key", "Idempotency-Key must contain 1–200 characters")


def _usage_row(run_id: str, message_id: str, analysis_id: str | None, attempt: int, event) -> Usage:
    values = event.model_dump() if hasattr(event, "model_dump") else dict(event)
    if "estimated_cost" in values:
        values["cost_usd"] = values.pop("estimated_cost")
    values.pop("request_id", None)
    values.pop("run_attempt_no", None)
    return Usage(run_id=run_id, message_id=message_id, analysis_id=analysis_id,
        run_attempt_no=attempt, **values)


def retry_run(session, run_id, user_id: str, key: str):
    """Queue only failed/missing results; retain successful outputs and their IDs."""
    validate_key(key)
    run = session.scalar(select(AnalysisRun).where(
        AnalysisRun.id == str(run_id), AnalysisRun.user_id == user_id,
    ).with_for_update())
    if run is None:
        raise AppError("not_found", "Record does not exist", 404)
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    if any(event.get("key_hash") == key_hash for event in (run.retry_history or [])):
        return run
    if run.status not in {"failed", "partial", "interrupted"}:
        raise AppError("run_not_retryable", "Only failed, partial or interrupted runs can be retried", 409)

    completed_count = session.scalar(select(func.count()).select_from(Analysis).where(
        Analysis.run_id == run.id, Analysis.status == "completed",
    )) or 0
    if completed_count >= run.total_count:
        raise AppError("nothing_to_retry", "All messages already have successful results", 409)
    failures = session.scalars(select(Analysis).where(
        Analysis.run_id == run.id, Analysis.status == "failed",
    )).all()
    attempt = run.attempt_no
    history = [*(run.retry_history or []), {
        "key_hash": key_hash,
        "requested_at": utcnow().isoformat(),
        "previous_attempt_no": attempt,
        "previous_status": run.status,
        "failures": [
            {"analysis_id": row.id, "message_id": row.message_id, "failure_category": row.failure_category}
            for row in failures
        ],
    }]
    claimed = session.execute(update(AnalysisRun).where(
        AnalysisRun.id == run.id,
        AnalysisRun.status == run.status,
        AnalysisRun.attempt_no == attempt,
    ).values(
        status="queued",
        attempt_no=attempt + 1,
        retry_history=history,
        processed_count=completed_count,
        failed_count=0,
        error=None,
        started_at=None,
        finished_at=None,
        heartbeat_at=None,
    ), execution_options={"synchronize_session": False}).rowcount
    if not claimed:
        session.rollback()
        raise AppError("retry_conflict", "A retry is already in progress; reload the run", 409)
    session.commit()
    session.expire_all()
    return session.get(AnalysisRun, run.id)


def failure_details(exc):
    """Return only allowlisted failure categories and fixed safe descriptions."""
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


def create_run(session, payload, key: str, user_id: str, *, commit: bool = True):
    if not key.strip() or len(key) > 200:
        raise AppError("invalid_idempotency_key", "Idempotency-Key must contain 1–200 characters")
    existing = session.scalar(select(AnalysisRun).where(
        AnalysisRun.user_id == user_id, AnalysisRun.idempotency_key == key,
    ))
    if existing:
        if existing.product_id != str(payload.product_id) or existing.batch_id != str(payload.batch_id):
            raise AppError("idempotency_conflict", "Key was used with a different payload", 409)
        return existing
    product = session.scalar(select(Product).where(
        Product.id == str(payload.product_id), Product.user_id == user_id,
    ))
    batch = session.scalar(select(ImportBatch).where(
        ImportBatch.id == str(payload.batch_id), ImportBatch.user_id == user_id,
    ))
    if product is None or batch is None:
        raise AppError("not_found", "Product or batch does not exist", 404)
    get_provider(settings().provider_mode)
    snapshot = ProductOut.model_validate(product).model_dump(mode="json", exclude={"created_at"})
    run = AnalysisRun(
        user_id=user_id,
        product_id=product.id,
        batch_id=batch.id,
        product_snapshot=snapshot,
        config_snapshot=RunConfig(provider_mode=settings().provider_mode).model_dump(),
        idempotency_key=key,
        total_count=batch.row_count,
    )
    session.add(run)
    if not commit:
        # Telegram ingestion owns the surrounding transaction that also writes
        # its message and receipt. Let that transaction roll back atomically.
        session.flush()
        return run
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return create_run(session, payload, key, user_id)
    return run


def recover_interrupted(factory):
    cutoff = utcnow() - timedelta(seconds=settings().heartbeat_timeout_seconds)
    with factory() as session:
        session.execute(update(AnalysisRun).where(
            AnalysisRun.status == "running",
            (AnalysisRun.heartbeat_at < cutoff) | AnalysisRun.heartbeat_at.is_(None),
        ).values(
            status="interrupted",
            finished_at=utcnow(),
            error="Worker heartbeat expired. Retry explicitly; completed results are preserved.",
        ))
        session.commit()


def _lease(session, run_id: str, attempt: int) -> bool:
    """Conditionally refresh the lease; also fences writes against recovery/retry."""
    result = session.execute(update(AnalysisRun).where(
        AnalysisRun.id == run_id,
        AnalysisRun.status == "running",
        AnalysisRun.attempt_no == attempt,
    ).values(heartbeat_at=utcnow()), execution_options={"synchronize_session": False})
    return result.rowcount == 1


def _counts(session, run: AnalysisRun):
    rows = dict(session.execute(select(Analysis.status, func.count()).where(
        Analysis.run_id == run.id,
    ).group_by(Analysis.status)).all())
    run.failed_count = rows.get("failed", 0)
    run.processed_count = rows.get("completed", 0) + run.failed_count


def _persist_result(session, *, run_id: str, attempt: int, message_id: str,
                    result: AnalysisResult, usage, failure_category: str | None = None):
    analysis = session.scalar(select(Analysis).where(
        Analysis.run_id == run_id, Analysis.message_id == message_id,
    ).with_for_update())
    if analysis is not None and analysis.status == "completed":
        return analysis
    values = result.model_dump(mode="json")
    if result.status == "failed":
        # Qualification/scoring did not complete, so do not attach model defaults
        # that could be mistaken for executed-stage metadata.
        values.update(scoring_version=None, prompt_version=None)
    if analysis is None:
        analysis = Analysis(run_id=run_id, message_id=message_id, **values)
        session.add(analysis)
    else:
        for name, value in values.items():
            setattr(analysis, name, value)
    analysis.failure_category = failure_category
    session.flush()
    for event in usage:
        session.add(_usage_row(run_id, message_id, analysis.id, attempt, event))
    return analysis


def _save_late_usage(session, run_id: str, attempt: int, message_id: str, usage):
    """Keep real provider accounting when its result loses the worker lease."""
    previous = session.scalar(select(Analysis).where(
        Analysis.run_id == run_id, Analysis.message_id == message_id,
    ))
    for event in usage:
        session.add(_usage_row(run_id, message_id, previous.id if previous else None, attempt, event))


def process_one(factory, provider_override=None, agent_orchestrator=None) -> bool:
    with factory() as session:
        run = session.scalar(select(AnalysisRun).where(
            AnalysisRun.status == "queued",
        ).order_by(AnalysisRun.created_at).with_for_update(skip_locked=True).limit(1))
        if run is None:
            return False
        run_id, batch_id, attempt = run.id, run.batch_id, run.attempt_no
        claimed = session.execute(update(AnalysisRun).where(
            AnalysisRun.id == run_id,
            AnalysisRun.status == "queued",
            AnalysisRun.attempt_no == attempt,
        ).values(status="running", started_at=utcnow(), heartbeat_at=utcnow()),
            execution_options={"synchronize_session": False}).rowcount
        session.commit()
        if claimed != 1:
            return True
        product_id = run.product_id
        product_snapshot = dict(run.product_snapshot) if isinstance(run.product_snapshot, dict) else run.product_snapshot
        config_snapshot = dict(run.config_snapshot) if isinstance(run.config_snapshot, dict) else run.config_snapshot

    try:
        from app.integrations.telegram.models import TelegramReceipt

        with factory() as session:
            if not _lease(session, run_id, attempt):
                session.rollback()
                return True
            telegram_run = session.scalar(select(TelegramReceipt.id).where(
                TelegramReceipt.run_id == run_id,
            )) is not None
            messages = load_messages(session, batch_id)
            product = ProductSnapshot.model_validate(product_snapshot)
            config = RunConfig.model_validate(config_snapshot)
            provider = None if telegram_run or agent_orchestrator is not None else (
                provider_override or get_provider(config.provider_mode)
            )
            completed_ids = set(session.scalars(select(Analysis.message_id).where(
                Analysis.run_id == run_id, Analysis.status == "completed",
            )).all())
            if telegram_run:
                from app.integrations.telegram.worker_adapter import prepare_work

                active_run = session.get(AnalysisRun, run_id)
                telegram_input, telegram_target = prepare_work(session, active_run, messages, config)
            session.commit()  # Save the exact Telegram input before the Agent invocation.

        targets = [telegram_target] if telegram_run else messages
        for target in targets:
            if str(target.id) in completed_ids:
                continue
            with factory() as session:
                if not _lease(session, run_id, attempt):
                    session.rollback()
                    return True
                session.commit()

            result = None
            output = None
            usage = []
            failure_category = None
            failure_reason = None
            if telegram_run:
                try:
                    from app.integrations.telegram.worker_adapter import analyze_work

                    _, _, output = analyze_work(telegram_input)
                    usage = output.usage
                except Exception as exc:
                    failure_category, failure_reason = failure_details(exc)
                    usage = getattr(exc, "usage", [])
            else:
                try:
                    if agent_orchestrator is not None:
                        agent_input = build_agent_input(
                            product_snapshot={**product_snapshot, "id": product_id},
                            run_id=run_id,
                            provider_mode=config.provider_mode,
                            target=target,
                            messages=messages,
                            config=config,
                        )
                        output = agent_orchestrator(agent_input)
                        usage = output.usage
                    else:
                        result, usage = analyze(product, target, messages, config, provider)
                except Exception as exc:
                    usage = getattr(exc, "usage", [])
                    failure_category, failure_reason = failure_details(exc)

            if output is None and failure_reason is not None:
                result = AnalysisResult(status="failed", is_candidate=True,
                    screening_reason="processing_error", decision=None, reason=failure_reason,
                    provider_mode=config.provider_mode)

            with factory() as session:
                if not _lease(session, run_id, attempt):
                    _save_late_usage(session, run_id, attempt, str(target.id), usage)
                    session.commit()
                    return True
                if output is not None:
                    analysis = persist_agent_output(session, run_id=run_id,
                        target_message_id=str(target.id), inputs=telegram_input if telegram_run else agent_input,
                        raw_output=output, run_attempt_no=attempt)
                    if telegram_run:
                        receipt = session.scalar(select(TelegramReceipt).where(TelegramReceipt.run_id == run_id))
                        if receipt is None:
                            raise AppError("invalid_telegram_job", "Telegram receipt is missing", 503)
                        receipt.agent_output = output.model_dump(mode="json")
                else:
                    analysis = _persist_result(session, run_id=run_id, attempt=attempt,
                        message_id=str(target.id), result=result, usage=usage,
                        failure_category=failure_category)
                current = session.get(AnalysisRun, run_id)
                _counts(session, current)
                session.commit()

        with factory() as session:
            if not _lease(session, run_id, attempt):
                session.rollback()
                return True
            current = session.get(AnalysisRun, run_id)
            _counts(session, current)
            current.status = (
                "completed" if current.failed_count == 0
                else "failed" if current.failed_count == current.total_count
                else "partial"
            )
            current.error = "Some analyses failed. Open failed results for details and retry explicitly." if current.failed_count else None
            current.finished_at = utcnow()
            session.commit()
    except Exception as exc:
        failure_category, failure_reason = failure_details(exc)
        with factory() as session:
            if not _lease(session, run_id, attempt):
                session.rollback()
                return True
            receipt = session.scalar(select(TelegramReceipt).where(TelegramReceipt.run_id == run_id))
            failed_ids = [receipt.message_id] if receipt else session.scalars(select(Message.id).where(
                Message.batch_id == batch_id,
            )).all()
            mode = config_snapshot.get("provider_mode") if isinstance(config_snapshot, dict) else None
            mode = mode if mode in {"mock", "real"} else "real"
            completed = set(session.scalars(select(Analysis.message_id).where(
                Analysis.run_id == run_id, Analysis.status == "completed",
            )).all())
            for message_id in failed_ids:
                if str(message_id) in completed:
                    continue
                failed_result = AnalysisResult(status="failed", is_candidate=True,
                    screening_reason="processing_error", decision=None, reason=failure_reason,
                    provider_mode=mode)
                _persist_result(session, run_id=run_id, attempt=attempt,
                    message_id=str(message_id), result=failed_result, usage=[],
                    failure_category=failure_category)
            current = session.get(AnalysisRun, run_id)
            _counts(session, current)
            current.status, current.error, current.finished_at = "failed", failure_reason, utcnow()
            session.commit()
    return True
