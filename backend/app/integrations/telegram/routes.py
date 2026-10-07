import hmac
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.contracts import CurrentUser
from app.auth.dependencies import verify_origin
from app.core.errors import AppError
from app.db.session import get_session
from app.integrations.telegram import actions, dependencies
from app.integrations.telegram.config import telegram_settings
from app.integrations.telegram.ingestion import ingest
from app.integrations.telegram.models import TelegramChatMapping, TelegramReceipt
from app.integrations.telegram.normalization import normalize_update
from app.integrations.telegram.schemas import (
    ApprovedReply, ChatMappingInput, ChatMappingOut, DraftRequest, TelegramLeadOut, TelegramLeadPage, WebhookOut,
)
from app.models import Analysis

webhook_router = APIRouter(tags=["Telegram webhook"])
router = APIRouter(tags=["Telegram user actions"])
DB = Annotated[Session, Depends(get_session)]
User = Annotated[CurrentUser, Depends(dependencies.current_user)]


@webhook_router.post("/integrations/telegram/webhook", response_model=WebhookOut)
async def webhook(request: Request, session: DB,
    secret: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None):
    expected = telegram_settings().require_secret()
    if secret is None or len(secret) > 256 or not hmac.compare_digest(secret.encode(), expected.encode()):
        raise AppError("invalid_webhook_secret", "Webhook authentication failed", 403)
    # A bounded read avoids loading an arbitrarily large request into memory.
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 128_000:
            raise AppError("telegram_payload_too_large", "Webhook payload is too large", 413)
    try:
        update = json.loads(content)
    except (ValueError, RecursionError):
        raise AppError("invalid_telegram_update", "Webhook payload must be JSON", 400) from None
    normalized = normalize_update(update)
    return WebhookOut(status="ignored" if normalized is None else ingest(session, normalized))


@router.post("/integrations/telegram/chats", response_model=ChatMappingOut, status_code=201,
    dependencies=[Depends(verify_origin)])
def map_chat(payload: ChatMappingInput, session: DB, user: User):
    dependencies.product_access(session, user, payload.product_id)
    existing = session.scalar(select(TelegramChatMapping).where(TelegramChatMapping.telegram_chat_id == payload.telegram_chat_id))
    if existing:
        if existing.owner_user_id != str(user.id) or existing.product_id != str(payload.product_id):
            raise AppError("chat_already_mapped", "Chat is already mapped", 409)
        return ChatMappingOut(id=existing.id, product_id=existing.product_id, telegram_chat_id=existing.telegram_chat_id, enabled=existing.enabled)
    mapping = TelegramChatMapping(owner_user_id=str(user.id), product_id=str(payload.product_id), telegram_chat_id=payload.telegram_chat_id)
    session.add(mapping)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise AppError("chat_already_mapped", "Chat is already mapped", 409) from None
    return ChatMappingOut(id=mapping.id, product_id=mapping.product_id, telegram_chat_id=mapping.telegram_chat_id, enabled=mapping.enabled)


@router.get("/integrations/telegram/leads", response_model=TelegramLeadPage)
def leads(session: DB, user: User, limit: Annotated[int, Query(ge=1, le=100)] = 20,
          offset: Annotated[int, Query(ge=0)] = 0):
    statement = select(Analysis.id).join(TelegramReceipt, (TelegramReceipt.run_id == Analysis.run_id)
        & (TelegramReceipt.message_id == Analysis.message_id)).join(TelegramChatMapping, TelegramChatMapping.id == TelegramReceipt.mapping_id).where(
        TelegramChatMapping.owner_user_id == str(user.id), TelegramChatMapping.enabled.is_(True),
        Analysis.status == "completed", Analysis.decision.in_(["review", "respond"]))
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    ids = session.scalars(statement.order_by(Analysis.lead_score.desc(), Analysis.id).limit(limit).offset(offset)).all()
    return TelegramLeadPage(items=[actions.lead_view(session, str(user.id), id) for id in ids], total=total, limit=limit, offset=offset)


@router.get("/leads/{lead_id}/telegram", response_model=TelegramLeadOut)
def lead(lead_id: UUID, session: DB, user: User):
    return actions.lead_view(session, str(user.id), str(lead_id))


@router.post("/leads/{lead_id}/telegram/suggested-reply", response_model=TelegramLeadOut,
    dependencies=[Depends(verify_origin)])
def suggested_reply(lead_id: UUID, payload: DraftRequest, session: DB, user: User):
    return actions.draft_reply(session, str(user.id), str(lead_id), regenerate=payload.regenerate)


@router.post("/leads/{lead_id}/telegram/reply", response_model=TelegramLeadOut,
    dependencies=[Depends(verify_origin)])
def approved_reply(lead_id: UUID, payload: ApprovedReply, session: DB, user: User,
                   client=Depends(dependencies.telegram_client)):
    return actions.send_reply(session, str(user.id), str(lead_id), payload.text, client)
