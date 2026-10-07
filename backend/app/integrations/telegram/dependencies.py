"""Shared authenticated session and verified Product ownership for Telegram."""
from uuid import UUID

from fastapi import Request

from app.auth.contracts import CurrentUser
from app.auth.dependencies import current_user, bearer
from app.core.errors import AppError
from app.integrations.telegram.client import TelegramClient
from app.integrations.telegram.config import telegram_settings
from app.models import Product
from app.services.ownership_service import owned


def product_access(request: Request, user: CurrentUser, product_id: UUID, session) -> None:
    if not hasattr(request.app.state, "telegram_product_access"):
        owned(session, Product, product_id, user.id)
        return
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
    owned(session, Product, product_id, user.id)


def telegram_client() -> TelegramClient:
    return TelegramClient(telegram_settings())
