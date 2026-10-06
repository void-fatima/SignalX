from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session
from app.auth.contracts import Credentials, CurrentUser, SessionGrant
from app.auth.dependencies import get_current_user, verify_origin
from app.auth.service import DatabaseAuthService
from app.core.config import settings
from app.db.session import get_session


router = APIRouter(prefix="/auth", tags=["auth"])
DB = Annotated[Session, Depends(get_session)]
Current = Annotated[CurrentUser, Depends(get_current_user)]


def _set_session_cookie(response: Response, grant: SessionGrant) -> None:
    response.set_cookie(
        key=settings().auth_cookie_name,
        value=grant.token,
        max_age=settings().session_lifetime_seconds,
        httponly=True,
        secure=settings().auth_cookie_secure,
        samesite="lax",
        path="/api/v1",
    )


@router.post("/register", response_model=CurrentUser, status_code=201, dependencies=[Depends(verify_origin)])
def register(payload: Credentials, session: DB):
    return DatabaseAuthService(session).register(payload)


@router.post("/login", response_model=SessionGrant, dependencies=[Depends(verify_origin)])
def login(payload: Credentials, response: Response, session: DB):
    grant = DatabaseAuthService(session).login(payload)
    _set_session_cookie(response, grant)
    return grant


@router.post("/logout", status_code=204, dependencies=[Depends(verify_origin)])
def logout(request: Request, response: Response, session: DB):
    token = request.cookies.get(settings().auth_cookie_name)
    if token:
        DatabaseAuthService(session).logout(token)
    response.delete_cookie(
        key=settings().auth_cookie_name,
        path="/api/v1",
        secure=settings().auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.status_code = 204
    return response


@router.get("/me", response_model=CurrentUser)
def me(current: Current):
    return current
