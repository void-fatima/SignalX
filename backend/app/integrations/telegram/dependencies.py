"""Bind Telegram actions to Backend sessions and verified product ownership."""
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.contracts import CurrentUser
from app.auth.dependencies import session_cookie
from app.auth.service import DatabaseAuthService
from app.core.errors import AppError
from app.db.session import get_session
from app.integrations.telegram.client import TelegramClient
from app.integrations.telegram.config import telegram_settings
from app.models import Product


bearer = HTTPBearer(auto_error=False, scheme_name="BackendSession")


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    cookie_token: Annotated[str | None, Depends(session_cookie)],
    session: Annotated[Session, Depends(get_session)],
) -> CurrentUser:
    token = credentials.credentials if credentials is not None else cookie_token
    if not token or not token.strip():
        raise AppError("authentication_required", "Authentication is required", 401)
    return DatabaseAuthService(session).current_user(token)


def product_access(session: Session, user: CurrentUser, product_id: UUID) -> None:
    product = session.scalar(select(Product).where(
        Product.id == str(product_id), Product.user_id == str(user.id),
    ))
    if product is None:
        raise AppError("not_found", "Product does not exist", 404)


def telegram_client() -> TelegramClient:
    return TelegramClient(telegram_settings())
