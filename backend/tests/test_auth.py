from sqlalchemy import select
from app.auth.security import SessionStore
from app.models import UserSession


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
