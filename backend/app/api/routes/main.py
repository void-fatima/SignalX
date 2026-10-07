import hashlib
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, Form, Header, Query
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.models import Product, ImportBatch, Message, AnalysisRun, Analysis, Usage, User as UserRecord, AuthSession
from app.integrations.telegram.models import TelegramChatMapping, TelegramReceipt, TelegramDelivery
from app.schemas.api import ProductInput, ProductPatch, ProductOut, ImportOut, BatchOut, MessageOut, RunInput, RunOut, AnalysisOut, LeadDetail, Page
from app.core.errors import AppError
from app.core.config import settings
from app.services.import_service import import_csv
from app.services.analysis_service import create_run
from app.auth.contracts import CurrentUser
from app.auth.dependencies import current_user
from app.services.ownership_service import owned, owned_run

router = APIRouter()
DB = Annotated[Session, Depends(get_session)]
User = Annotated[CurrentUser, Depends(current_user)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def find(session, model, id):
    row = session.get(model, str(id))
    if row is None:
        raise AppError("not_found", "Record does not exist", 404)
    return row


def page(session, statement, limit, offset):
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    return {"items": session.scalars(statement.limit(limit).offset(offset)).all(), "total": total, "limit": limit, "offset": offset}


@router.get("/health")
def health():
    return {"status": "ok", "project": "singnalX", "provider_mode": settings().provider_mode}


@router.get("/ready")
def ready(session: DB):
    try:
        revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if revision != "0003":
            raise ValueError("Migration revision is not current")
        for model in (Product, ImportBatch, Message, AnalysisRun, Analysis, Usage, UserRecord, AuthSession,
                      TelegramChatMapping, TelegramReceipt, TelegramDelivery):
            session.execute(select(model).limit(1))
    except Exception as exc:
        raise AppError("not_ready", "Database or migration is not ready", 503) from exc
    return {"status": "ready", "revision": revision}


@router.post("/products", response_model=ProductOut, status_code=201)
def add_product(payload: ProductInput, session: DB, user: User):
    product = Product(owner_user_id=str(user.id), **payload.model_dump())
    session.add(product)
    session.commit()
    return product


@router.get("/products", response_model=Page[ProductOut])
def products(session: DB, user: User, limit: Limit = 20, offset: Offset = 0):
    return page(session, select(Product).where(Product.owner_user_id == str(user.id)).order_by(Product.created_at, Product.id), limit, offset)


@router.get("/products/{id}", response_model=ProductOut)
def product(id: UUID, session: DB, user: User):
    return owned(session, Product, id, user.id)


@router.patch("/products/{id}", response_model=ProductOut)
def patch_product(id: UUID, payload: ProductPatch, session: DB, user: User):
    product = owned(session, Product, id, user.id)
    changes = payload.model_dump(exclude_unset=True)
    if any(value is None and key != "price" for key, value in changes.items()):
        raise AppError("validation_error", "Only price may be null")
    for key, value in changes.items():
        setattr(product, key, value)
    session.commit()
    return product


@router.post("/imports", response_model=ImportOut, status_code=201)
async def upload(session: DB, user: User, file: Annotated[UploadFile, File()], community_name: Annotated[str, Form()]):
    content = await file.read(5 * 1024 * 1024 + 1)
    batch, duplicate, warnings = import_csv(session, content, file.filename, community_name, owner_user_id=str(user.id))
    return {"batch": BatchOut.model_validate(batch), "count": batch.row_count, "duplicate": duplicate, "warnings": warnings}


@router.get("/messages", response_model=Page[MessageOut])
def messages(batch_id: UUID, session: DB, user: User, limit: Limit = 20, offset: Offset = 0):
    owned(session, ImportBatch, batch_id, user.id)
    return page(session, select(Message).where(Message.batch_id == str(batch_id)).order_by(Message.timestamp, Message.external_id), limit, offset)


@router.post("/analysis/runs", response_model=RunOut, status_code=202)
def start_run(payload: RunInput, session: DB, user: User, idempotency_key: Annotated[str, Header(alias="Idempotency-Key")]):
    owned(session, Product, payload.product_id, user.id)
    owned(session, ImportBatch, payload.batch_id, user.id)
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise AppError("invalid_idempotency_key", "Idempotency-Key must contain 1–200 characters")
    key = "user:" + str(user.id) + ":" + hashlib.sha256(idempotency_key.encode()).hexdigest()
    return create_run(session, payload, key)


@router.get("/analysis/runs/{id}", response_model=RunOut)
def run(id: UUID, session: DB, user: User):
    return owned_run(session, id, user.id)


@router.get("/leads", response_model=Page[AnalysisOut])
def leads(run_id: UUID, session: DB, user: User, decision: Literal["ignore", "review", "respond"] | None = None,
          min_score: Annotated[int | None, Query(ge=0, le=100)] = None, limit: Limit = 20, offset: Offset = 0):
    owned_run(session, run_id, user.id)
    statement = select(Analysis).where(Analysis.run_id == str(run_id))
    statement = statement.where(Analysis.decision == decision) if decision else statement.where(Analysis.decision.in_(["review", "respond"]))
    if min_score is not None:
        statement = statement.where(Analysis.lead_score >= min_score)
    return page(session, statement.order_by(Analysis.lead_score.desc(), Analysis.id), limit, offset)


@router.get("/leads/{id}", response_model=LeadDetail)
def lead(id: UUID, session: DB, user: User):
    analysis = find(session, Analysis, id)
    message = find(session, Message, analysis.message_id)
    run = owned_run(session, analysis.run_id, user.id)
    context = session.scalars(select(Message).where(Message.id.in_(analysis.context_message_ids), Message.batch_id == run.batch_id,
        Message.conversation_id == message.conversation_id).order_by(Message.timestamp, Message.external_id)).all()
    return {"analysis": analysis, "message": message, "context": context, "product_snapshot": run.product_snapshot, "offline_context": True}
