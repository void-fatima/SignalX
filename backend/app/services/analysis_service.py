from datetime import timedelta
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from app.models import Product, ImportBatch, AnalysisRun, Analysis, Usage, utcnow
from app.schemas.api import ProductOut
from app.core.errors import AppError
from app.core.config import settings
from app.agents.contracts import ProductSnapshot, RunConfig, AnalysisResult
from app.agents.pipeline import analyze, get_provider
from app.services.context_service import load_messages


def create_run(session, payload, key: str):
    if not key.strip() or len(key) > 200:
        raise AppError("invalid_idempotency_key", "Idempotency-Key must contain 1–200 characters")
    existing = session.scalar(select(AnalysisRun).where(AnalysisRun.idempotency_key == key))
    if existing:
        if existing.product_id != str(payload.product_id) or existing.batch_id != str(payload.batch_id):
            raise AppError("idempotency_conflict", "Key was used with a different payload", 409)
        return existing
    product = session.get(Product, str(payload.product_id))
    batch = session.get(ImportBatch, str(payload.batch_id))
    if product is None or batch is None:
        raise AppError("not_found", "Product or batch does not exist", 404)
    get_provider(settings().provider_mode)
    snapshot = ProductOut.model_validate(product).model_dump(mode="json", exclude={"id", "created_at"})
    run = AnalysisRun(product_id=product.id, batch_id=batch.id, product_snapshot=snapshot,
        config_snapshot=RunConfig(provider_mode=settings().provider_mode).model_dump(), idempotency_key=key, total_count=batch.row_count)
    try:
        session.add(run)
        session.commit()
    except IntegrityError:
        session.rollback()
        return create_run(session, payload, key)
    return run


def recover_interrupted(factory):
    cutoff = utcnow() - timedelta(seconds=settings().heartbeat_timeout_seconds)
    with factory() as session:
        session.execute(update(AnalysisRun).where(AnalysisRun.status == "running",
            (AnalysisRun.heartbeat_at < cutoff) | AnalysisRun.heartbeat_at.is_(None)).values(
                status="interrupted", finished_at=utcnow(), error="Worker heartbeat expired; start a new run explicitly"))
        session.commit()


def process_one(factory, provider_override=None) -> bool:
    with factory() as session:
        run = session.scalar(select(AnalysisRun).where(AnalysisRun.status == "queued").order_by(AnalysisRun.created_at).with_for_update(skip_locked=True).limit(1))
        if run is None:
            return False
        run.status = "running"
        run.started_at = run.heartbeat_at = utcnow()
        session.commit()
        run_id, batch_id = run.id, run.batch_id
        product, config = ProductSnapshot.model_validate(run.product_snapshot), RunConfig.model_validate(run.config_snapshot)
    try:
        provider = provider_override or get_provider(config.provider_mode)
        with factory() as session:
            messages = load_messages(session, batch_id)
        for target in messages:
            with factory() as session:
                session.get(AnalysisRun, run_id).heartbeat_at = utcnow()
                session.commit()
            # All database sessions/transactions are closed before provider invocation.
            try:
                result, usage = analyze(product, target, messages, config, provider)
            except Exception as exc:
                usage = getattr(exc, "usage", [])
                result = AnalysisResult(status="failed", is_candidate=True, screening_reason="processing_error",
                    decision=None, reason=str(exc)[:1000])
            with factory() as session:
                analysis = Analysis(run_id=run_id, message_id=target.id, **result.model_dump(mode="json"))
                session.add(analysis)
                session.flush()
                for event in usage:
                    session.add(Usage(run_id=run_id, message_id=target.id, analysis_id=analysis.id, **event.model_dump()))
                current = session.get(AnalysisRun, run_id)
                current.processed_count += 1
                current.failed_count += int(result.status == "failed")
                current.heartbeat_at = utcnow()
                session.commit()
        with factory() as session:
            current = session.get(AnalysisRun, run_id)
            current.status = "completed" if current.failed_count == 0 else "failed" if current.failed_count == current.total_count else "partial"
            current.finished_at = utcnow()
            session.commit()
    except Exception as exc:
        with factory() as session:
            current = session.get(AnalysisRun, run_id)
            current.status, current.error, current.finished_at = "failed", str(exc)[:1000], utcnow()
            session.commit()
    return True
