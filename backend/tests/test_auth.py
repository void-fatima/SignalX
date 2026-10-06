from datetime import timedelta
from uuid import uuid4
import pytest
from fastapi import Response
from pydantic import ValidationError
from sqlalchemy import select
from app.api.routes.auth import _set_session_cookie
from app.auth.contracts import CurrentUser, Credentials, SessionGrant
from app.auth.service import DatabaseAuthService, _DUMMY_PASSWORD_HASH
from app.auth.security import ScryptPasswordHasher, SessionStore
from app.core.config import Settings
from app.core.errors import AppError
from app.models import User, UserSession, utcnow


def test_registration_login_me_and_logout(app_client, factory):
    credentials = {"email": " Roham@Example.test ", "password": "correct horse battery"}
    assert app_client.get("/api/v1/auth/me").status_code == 401

    registered = app_client.post("/api/v1/auth/register", json=credentials)
    assert registered.status_code == 201
    assert registered.json()["email"] == "roham@example.test"
    assert "password_hash" not in registered.json()

    logged_in = app_client.post("/api/v1/auth/login", json=credentials)
    assert logged_in.status_code == 200
    assert "token" not in logged_in.json()
    token = app_client.cookies.get("singnalx_session")
    assert token
    with factory() as session:
        stored = session.scalar(select(UserSession))
        assert stored.token_digest == SessionStore.token_digest(token)
        assert stored.token_digest != token
    assert app_client.get("/api/v1/auth/me").json()["id"] == registered.json()["id"]

    assert app_client.post("/api/v1/auth/logout").status_code == 204
    assert app_client.get("/api/v1/auth/me").status_code == 401


def test_registration_normalizes_duplicate_email_and_rejects_bad_credentials(app_client):
    assert app_client.post("/api/v1/auth/register", json={
        "email": "Person@example.test", "password": "correct horse battery",
    }).status_code == 201
    duplicate = app_client.post("/api/v1/auth/register", json={
        "email": " person@EXAMPLE.test ", "password": "correct horse battery",
    })
    assert duplicate.status_code == 409
    assert app_client.post("/api/v1/auth/login", json={
        "email": "person@example.test", "password": "incorrect password",
    }).status_code == 401


def test_mutating_request_rejects_unapproved_origin(app_client):
    response = app_client.post("/api/v1/auth/register", headers={"Origin": "https://attacker.invalid"}, json={
        "email": "person@example.test", "password": "correct horse battery",
    })
    assert response.status_code == 403


def test_openapi_documents_cookie_auth_on_protected_routes():
    from app.main import app

    schema = app.openapi()
    cookie = schema["components"]["securitySchemes"]["SessionCookie"]
    assert cookie["type"] == "apiKey" and cookie["in"] == "cookie"
    assert cookie["name"] == "singnalx_session"
    assert "HttpOnly" in cookie["description"]
    assert schema["paths"]["/api/v1/products"]["get"]["security"] == [{"SessionCookie": []}]
    assert "security" not in schema["paths"]["/api/v1/auth/login"]["post"]


def test_login_performs_password_verification_for_missing_and_existing_users(factory, monkeypatch):
    with factory() as session:
        session.add(User(email="known@example.test", password_hash="stored-hash"))
        session.commit()

        verified_hashes = []
        monkeypatch.setattr(ScryptPasswordHasher, "verify", lambda _self, _password, encoded:
            verified_hashes.append(encoded) or False)
        service = DatabaseAuthService(session)
        for email in ("missing@example.test", "known@example.test"):
            with pytest.raises(AppError) as error:
                service.login(Credentials(email=email, password="wrong password"))
            assert error.value.code == "invalid_credentials"

    assert verified_hashes == [_DUMMY_PASSWORD_HASH, "stored-hash"]


def test_successful_login_prunes_expired_and_revoked_sessions(client, factory):
    with factory() as session:
        user = session.scalar(select(User).where(User.email == "default@example.test"))
        now = utcnow()
        expired = UserSession(user_id=user.id,
            token_digest=SessionStore.token_digest("expired-session"),
            expires_at=now - timedelta(seconds=1))
        revoked = UserSession(user_id=user.id,
            token_digest=SessionStore.token_digest("revoked-session"),
            expires_at=now + timedelta(days=1), revoked_at=now)
        session.add_all([expired, revoked])
        session.commit()

    response = client.post("/api/v1/auth/login", json={
        "email": "default@example.test", "password": "correct horse battery",
    })
    assert response.status_code == 200
    with factory() as session:
        digests = set(session.scalars(select(UserSession.token_digest)))
    assert SessionStore.token_digest("expired-session") not in digests
    assert SessionStore.token_digest("revoked-session") not in digests


def test_cross_site_cookie_requires_secure_and_sets_cookie_attributes(monkeypatch):
    with pytest.raises(ValidationError, match="AUTH_COOKIE_SECURE"):
        Settings(auth_cookie_samesite="none", auth_cookie_secure=False)

    configured = Settings(auth_cookie_samesite="none", auth_cookie_secure=True)
    monkeypatch.setattr("app.api.routes.auth.settings", lambda: configured)
    user = CurrentUser(id=uuid4(), email="user@example.test", created_at=utcnow())
    grant = SessionGrant(user=user, token="opaque-session", expires_at=utcnow() + timedelta(hours=1))
    response = Response()
    _set_session_cookie(response, grant)

    cookie = response.headers["set-cookie"].lower()
    assert "samesite=none" in cookie and "secure" in cookie and "httponly" in cookie
