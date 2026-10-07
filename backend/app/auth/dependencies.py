"""Shared session and origin checks, including the existing Telegram auth adapter."""
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.contracts import AuthService, CurrentUser
from app.auth.service import DatabaseAuthService
from app.core.config import settings
from app.core.errors import AppError
from app.db.session import get_session

COOKIE_NAME = "signalx_session"
bearer = HTTPBearer(auto_error=False, scheme_name="BackendSession")
browser_session = APIKeyCookie(name=COOKIE_NAME, auto_error=False, scheme_name="BrowserSession")


def trusted_origin(request: Request) -> None:
    # Browsers send Origin for unsafe requests. SameSite=Lax also blocks cross-site POST cookies.
    if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
        origin = request.headers.get("origin")
        allowed = {item.strip().rstrip("/") for item in settings().cors_origins.split(",")}
        if origin is not None and origin.rstrip("/") not in allowed:
            raise AppError("untrusted_origin", "Request origin is not allowed", 403)


def session_token(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
                  cookie: Annotated[str | None, Depends(browser_session)]) -> str:
    if request.headers.get("authorization") and credentials is None:
        raise AppError("authentication_required", "Authentication is required", 401)
    token = credentials.credentials if credentials else cookie or ""
    if not token.strip() or len(token) > 512:
        raise AppError("authentication_required", "Authentication is required", 401)
    return token


def auth_service(request: Request, session: Session) -> AuthService:
    # Preserve Roham's AuthService injection point for login, revocation and lookup alike.
    if hasattr(request.app.state, "telegram_auth_service"):
        service = request.app.state.telegram_auth_service
        if service is None:
            raise AppError("authentication_unavailable", "Backend authentication is unavailable", 503)
        return service
    return DatabaseAuthService(session)


def current_user(request: Request, session: Annotated[Session, Depends(get_session)],
                 token: Annotated[str, Depends(session_token)], _: Annotated[None, Depends(trusted_origin)]) -> CurrentUser:
    service = auth_service(request, session)
    try:
        return CurrentUser.model_validate(service.current_user(token))
    except AppError:
        raise
    except Exception:
        raise AppError("authentication_required", "Session is invalid or expired", 401) from None
