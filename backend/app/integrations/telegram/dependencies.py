"""Fail-closed bridges to Roham's existing AuthService and product ownership."""
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.contracts import CurrentUser
from app.core.errors import AppError
from app.integrations.telegram.client import TelegramClient
from app.integrations.telegram.config import telegram_settings


bearer = HTTPBearer(auto_error=False, scheme_name="BackendSession")


def current_user(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> CurrentUser:
    if credentials is None or not credentials.credentials.strip():
        raise AppError("authentication_required", "Authentication is required", 401)
    service = getattr(request.app.state, "telegram_auth_service", None)
    if service is None:
        raise AppError("authentication_unavailable", "Backend authentication must be integrated before Telegram user actions", 503)
    try:
        return CurrentUser.model_validate(service.current_user(credentials.credentials))
    except Exception:
        raise AppError("authentication_required", "Session is invalid or expired", 401) from None


def product_access(request: Request, user: CurrentUser, product_id: UUID) -> None:
    access = getattr(request.app.state, "telegram_product_access", None)
    if access is None:
        raise AppError("ownership_unavailable", "Backend product ownership must be integrated before chat mapping", 503)
    # Backend adapter must return exactly True only for verified product access.
    try:
        allowed = access(user, product_id)
    except Exception:
        raise AppError("ownership_unavailable", "Product ownership could not be verified", 503) from None
    if allowed is not True:
        raise AppError("not_found", "Product does not exist", 404)


def telegram_client() -> TelegramClient:
    return TelegramClient(telegram_settings())
