from fastapi import Depends, Request
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session
from app.auth.contracts import CurrentUser
from app.auth.service import DatabaseAuthService
from app.core.config import settings
from app.core.errors import AppError
from app.db.session import get_session


session_cookie = APIKeyCookie(
    name=settings().auth_cookie_name,
    scheme_name="SessionCookie",
    description="Opaque HttpOnly session cookie issued by POST /auth/login.",
    auto_error=False,
)


def verify_origin(request: Request) -> None:
    """Reject browser mutations initiated by origins outside the configured app."""
    origin = request.headers.get("origin")
    if origin is None:
        return
    allowed = {value.strip().rstrip("/") for value in settings().cors_origins.split(",") if value.strip()}
    if origin.rstrip("/") not in allowed:
        raise AppError("invalid_origin", "Request origin is not allowed", 403)


def get_current_user(token: str | None = Depends(session_cookie), session: Session = Depends(get_session)) -> CurrentUser:
    if not token:
        raise AppError("authentication_required", "A valid login session is required", 401)
    return DatabaseAuthService(session).current_user(token)
