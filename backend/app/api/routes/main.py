from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, Form, Header, Query
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.models import User, UserSession, Product, ImportBatch, Message, AnalysisRun, Analysis, Usage
from app.schemas.api import ProductInput, ProductPatch, ProductOut, ImportOut, BatchOut, MessageOut, RunInput, RunOut, AnalysisOut, LeadDetail, Page
from app.core.errors import AppError
from app.services.import_service import import_csv
from app.services.analysis_service import create_run
from app.auth.contracts import CurrentUser
from app.auth.dependencies import get_current_user, verify_origin

router = APIRouter()
DB = Annotated[Session, Depends(get_session)]
Current = Annotated[CurrentUser, Depends(get_current_user)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def find(session, model, id):
    row = session.get(model, str(id))
    if row is None:
        raise AppError("not_found", "Record does not exist", 404)
    return row


def find_owned(session, model, id, user_id: str):
    row = session.scalar(select(model).where(model.id == str(id), model.user_id == str(user_id)))
    if row is None:
        raise AppError("not_found", "Record does not exist", 404)
    return row


def page(session, statement, limit, offset):
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    return {"items": session.scalars(statement.limit(limit).offset(offset)).all(), "total": total, "limit": limit, "offset": offset}


@router.get("/health")
def health():
    return {"status": "ok", "project": "singnalX", "provider_mode": "mock"}


@router.get("/ready")
def ready(session: DB):
    try:
        revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if revision != "0002":
            raise ValueError("Migration revision is not current")
        for model in (User, UserSession, Product, ImportBatch, Message, AnalysisRun, Analysis, Usage):
            session.execute(select(model.id).limit(1))
    except Exception as exc:
        raise AppError("not_ready", "Database or migration is not ready", 503) from exc
    return {"status": "ready", "revision": revision}


@router.post("/products", response_model=ProductOut, status_code=201, dependencies=[Depends(verify_origin)])
def add_product(payload: ProductInput, session: DB, current: Current):
    product = Product(user_id=str(current.id), **payload.model_dump())
    session.add(product)
    session.commit()
    return product


@router.get("/products", response_model=Page[ProductOut])
def products(session: DB, current: Current, limit: Limit = 20, offset: Offset = 0):
    statement = select(Product).where(Product.user_id == str(current.id)).order_by(Product.created_at, Product.id)
    return page(session, statement, limit, offset)


@router.get("/products/{id}", response_model=ProductOut)
def product(id: UUID, session: DB, current: Current):
    return find_owned(session, Product, id, str(current.id))


@router.patch("/products/{id}", response_model=ProductOut, dependencies=[Depends(verify_origin)])
def patch_product(id: UUID, payload: ProductPatch, session: DB, current: Current):
    product = find_owned(session, Product, id, str(current.id))
    changes = payload.model_dump(exclude_unset=True)
    if any(value is None and key != "price" for key, value in changes.items()):
        raise AppError("validation_error", "Only price may be null")
    for key, value in changes.items():
        setattr(product, key, value)
    session.commit()
    return product


@router.post("/imports", response_model=ImportOut, status_code=201, dependencies=[Depends(verify_origin)])
async def upload(session: DB, current: Current, file: Annotated[UploadFile, File()], community_name: Annotated[str, Form()]):
    content = await file.read(5 * 1024 * 1024 + 1)
    batch, duplicate, warnings = import_csv(session, content, file.filename, community_name, str(current.id))
    return {"batch": BatchOut.model_validate(batch), "count": batch.row_count, "duplicate": duplicate, "warnings": warnings}


@router.get("/messages", response_model=Page[MessageOut])
def messages(batch_id: UUID, session: DB, current: Current, limit: Limit = 20, offset: Offset = 0):
    find_owned(session, ImportBatch, batch_id, str(current.id))
    statement = select(Message).where(Message.batch_id == str(batch_id)).order_by(Message.timestamp, Message.external_id)
    return page(session, statement, limit, offset)


@router.post("/analysis/runs", response_model=RunOut, status_code=202, dependencies=[Depends(verify_origin)])
def start_run(payload: RunInput, session: DB, current: Current, idempotency_key: Annotated[str, Header(alias="Idempotency-Key")]):
    return create_run(session, payload, idempotency_key, str(current.id))


@router.get("/analysis/runs/{id}", response_model=RunOut)
def run(id: UUID, session: DB, current: Current):
    return find_owned(session, AnalysisRun, id, str(current.id))


@router.get("/leads", response_model=Page[AnalysisOut])
def leads(run_id: UUID, session: DB, current: Current, decision: Literal["ignore", "review", "respond"] | None = None,
          min_score: Annotated[int | None, Query(ge=0, le=100)] = None, limit: Limit = 20, offset: Offset = 0):
    find_owned(session, AnalysisRun, run_id, str(current.id))
    statement = select(Analysis).where(Analysis.run_id == str(run_id))
    statement = statement.where(Analysis.decision == decision) if decision else statement.where(Analysis.decision.in_(["review", "respond"]))
    if min_score is not None:
        statement = statement.where(Analysis.lead_score >= min_score)
    return page(session, statement.order_by(Analysis.lead_score.desc(), Analysis.id), limit, offset)


@router.get("/leads/{id}", response_model=LeadDetail)
def lead(id: UUID, session: DB, current: Current):
    analysis = session.scalar(select(Analysis).join(AnalysisRun, AnalysisRun.id == Analysis.run_id).where(
        Analysis.id == str(id), AnalysisRun.user_id == str(current.id)))
    if analysis is None:
        raise AppError("not_found", "Record does not exist", 404)
    run = find_owned(session, AnalysisRun, analysis.run_id, str(current.id))
    message = session.scalar(select(Message).where(Message.id == analysis.message_id, Message.batch_id == run.batch_id))
    if message is None:
        raise AppError("not_found", "Record does not exist", 404)
    context = session.scalars(select(Message).where(Message.id.in_(analysis.context_message_ids), Message.batch_id == run.batch_id,
        Message.conversation_id == message.conversation_id).order_by(Message.timestamp, Message.external_id)).all()
    return {"analysis": analysis, "message": message, "context": context, "product_snapshot": run.product_snapshot, "offline_context": True}
