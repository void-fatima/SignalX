from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.auth.contracts import Credentials, CurrentUser
from app.auth.dependencies import COOKIE_NAME, auth_service, current_user, session_token, trusted_origin
from app.auth.service import SESSION_SECONDS
from app.core.errors import AppError
from app.core.config import settings
from app.db.session import get_session

router = APIRouter(prefix="/auth", tags=["Authentication"], dependencies=[Depends(trusted_origin)])
DB = Annotated[Session, Depends(get_session)]


def set_session(response: Response, token: str) -> None:
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=settings().auth_cookie_secure,
                        samesite="lax", max_age=SESSION_SECONDS, path="/")
    response.headers["Cache-Control"] = "no-store"


@router.post("/register", response_model=CurrentUser, status_code=201)
def register(payload: Credentials, request: Request, session: DB, response: Response):
    service = auth_service(request, session)
    try:
        service.register(payload)
        grant = service.login(payload)
    except AppError:
        raise
    except Exception:
        raise AppError("authentication_unavailable", "Account registration is unavailable", 503) from None
    set_session(response, grant.token)
    return grant.user


@router.post("/login", response_model=CurrentUser)
def login(payload: Credentials, request: Request, session: DB, response: Response):
    try:
        grant = auth_service(request, session).login(payload)
    except AppError:
        raise
    except Exception:
        raise AppError("authentication_unavailable", "Account login is unavailable", 503) from None
    set_session(response, grant.token)
    return grant.user


@router.get("/me", response_model=CurrentUser)
def me(user: Annotated[CurrentUser, Depends(current_user)], response: Response):
    response.headers["Cache-Control"] = "no-store"
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, session: DB, token: Annotated[str, Depends(session_token)], response: Response):
    try:
        auth_service(request, session).logout(token)
    except AppError:
        raise
    except Exception:
        raise AppError("authentication_unavailable", "Account logout is unavailable", 503) from None
    response.delete_cookie(COOKIE_NAME, path="/", secure=settings().auth_cookie_secure, httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
