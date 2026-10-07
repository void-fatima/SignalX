"""Authenticated product setup and existing Agent/Telegram integration, entirely offline."""
import json
from pathlib import Path
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text

from app.agents.providers.factory import real_provider_client
from app.core.config import settings
from app.integrations.telegram import worker_adapter
from app.models import Analysis, AnalysisRun, AuthSession, ImportBatch, Product, User, utcnow
from app.services.analysis_service import process_one

PROFILE = {"name": "SensorWorks", "description": "Calibration and repairs for precision sensors.",
           "target_customer": "Laboratories that need reliable measurements."}
CSV = b"external_id,conversation_id,author,content,timestamp\n1,lab,alex,I need sensor calibration,2026-10-08T10:00:00Z\n"


@pytest.fixture(autouse=True)
def local_sessions(monkeypatch):
    monkeypatch.setattr(settings(), "auth_cookie_secure", False)
    monkeypatch.setattr(settings(), "provider_mode", "mock")


def register(client, email="owner@example.test"):
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "offline-test-password"})
    assert response.status_code == 201
    return response.json(), {"Authorization": "Bearer " + client.cookies.get("signalx_session")}


def create(client, profile=None):
    response = client.post("/api/v1/products", json=profile or PROFILE)
    assert response.status_code == 201
    return response.json()


def batch(client):
    response = client.post("/api/v1/imports", data={"community_name": "lab"}, files={"file": ("lab.csv", CSV)})
    assert response.status_code == 201
    return response.json()["batch"]["id"]


def test_create_view_list_update_and_optional_fields(client, factory):
    user, _ = register(client)
    profile = create(client)
    assert profile["name"] == PROFILE["name"] and profile["price"] is None
    assert client.get(f"/api/v1/products/{profile['id']}").json() == profile
    assert client.get("/api/v1/products").json()["items"] == [profile]
    response = client.patch(f"/api/v1/products/{profile['id']}", json={"description": " Updated offering ", "price": "0.00", "best_fit": ["Labs"]})
    assert response.status_code == 200 and response.json()["description"] == "Updated offering"
    assert response.json()["name"] == PROFILE["name"] and response.json()["best_fit"] == ["Labs"]
    with factory() as session:
        assert session.get(Product, profile["id"]).owner_user_id == user["id"]


def test_list_is_scoped_and_paginated(client):
    _, owner = register(client)
    first = create(client)
    second = create(client, {**PROFILE, "name": "Second offering"})
    page = client.get("/api/v1/products?limit=1&offset=1").json()
    assert page["total"] == 2 and [p["id"] for p in page["items"]] == [second["id"]]
    register(client, "other@example.test")
    assert client.get("/api/v1/products").json()["total"] == 0
    assert client.get("/api/v1/products", headers=owner).json()["total"] == 2
    assert client.get(f"/api/v1/products/{first['id']}").status_code == 404
    assert client.patch(f"/api/v1/products/{first['id']}", json={"name": "stolen"}).status_code == 404
    assert client.get(f"/api/v1/products/{first['id']}", headers=owner).json()["name"] == first["name"]


@pytest.mark.parametrize("field", ["name", "description", "target_customer"])
@pytest.mark.parametrize("value", [None, "", " \n\t "])
def test_required_fields_reject_blank_and_null(client, field, value):
    register(client)
    assert client.post("/api/v1/products", json={**PROFILE, field: value}).status_code == 422
    profile = create(client)
    assert client.patch(f"/api/v1/products/{profile['id']}", json={field: value}).status_code == 422
    assert client.get(f"/api/v1/products/{profile['id']}").json()[field] == PROFILE[field]


@pytest.mark.parametrize("field", ["name", "description", "target_customer"])
def test_required_fields_cannot_be_omitted(client, field):
    register(client)
    assert client.post("/api/v1/products", json={k: v for k, v in PROFILE.items() if k != field}).status_code == 422


@pytest.mark.parametrize("field,limit", [("name", 200), ("description", 4000), ("target_customer", 2000)])
def test_field_length_limits(client, field, limit):
    register(client)
    assert client.post("/api/v1/products", json={**PROFILE, field: "x" * (limit + 1)}).status_code == 422


def test_owner_cannot_be_set_in_payload(client):
    register(client)
    assert client.post("/api/v1/products", json={**PROFILE, "owner_user_id": str(uuid4())}).status_code == 422
    profile = create(client)
    assert client.patch(f"/api/v1/products/{profile['id']}", json={"owner_user_id": str(uuid4())}).status_code == 422


def test_unassigned_historical_profiles_are_preserved_but_not_claimable(client, factory):
    with factory() as session:
        old = Product(**PROFILE, problems_solved=[], best_fit=[], not_fit=[], currency="USD")
        session.add(old); session.commit(); old_id = old.id
    register(client)
    assert client.get("/api/v1/products").json()["total"] == 0
    assert client.get(f"/api/v1/products/{old_id}").status_code == 404
    assert client.patch(f"/api/v1/products/{old_id}", json={"name": "claim"}).status_code == 404
    with factory() as session:
        assert session.get(Product, old_id).name == PROFILE["name"]


@pytest.mark.parametrize("method,path", [("get", "/products"), ("post", "/products"),
    ("get", "/products/00000000-0000-0000-0000-000000000000"), ("patch", "/products/00000000-0000-0000-0000-000000000000"),
    ("post", "/imports"), ("post", "/analysis/runs"), ("get", "/leads"), ("get", "/messages")])
def test_private_routes_require_authentication(client, method, path):
    options = {"json": PROFILE} if method in {"post", "patch"} else {}
    assert getattr(client, method)("/api/v1" + path, **options).status_code == 401


def test_authentication_session_security_and_revocation(client, factory):
    user, _ = register(client, " Owner@Example.test ")
    assert user["email"] == "owner@example.test" and set(user) == {"id", "email", "created_at"}
    token = client.cookies.get("signalx_session")
    assert client.get("/api/v1/auth/me").json() == user
    with factory() as session:
        stored_user = session.get(User, user["id"])
        stored_session = session.scalar(select(AuthSession))
        assert stored_user.password_hash.startswith("pbkdf2_sha256$")
        assert "offline-test-password" not in stored_user.password_hash
        assert token != stored_session.token_hash and len(stored_session.token_hash) == 64
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": user["email"], "password": "wrong-password"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": user["email"], "password": "offline-test-password"}).status_code == 200


def test_expired_session_is_rejected(client, factory):
    register(client)
    with factory() as session:
        session.scalar(select(AuthSession)).expires_at = utcnow() - timedelta(seconds=1)
        session.commit()
    assert client.get("/api/v1/products").status_code == 401


def test_secure_cookie_default_can_be_used_over_https(client, monkeypatch):
    monkeypatch.setattr(settings(), "auth_cookie_secure", True)
    response = client.post("/api/v1/auth/register", json={"email": "secure@example.test", "password": "offline-test-password"})
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie and "Max-Age=86400" in cookie
    # The HTTP test client must not send the Secure cookie over plaintext.
    assert client.get("/api/v1/auth/me").status_code == 401


def test_cookie_mutations_reject_untrusted_origins(client):
    register(client)
    assert client.post("/api/v1/products", json=PROFILE, headers={"Origin": "https://attacker.example"}).status_code == 403
    assert client.post("/api/v1/auth/logout", headers={"Origin": "null"}).status_code == 403
    assert client.post("/api/v1/products", json=PROFILE, headers={"Origin": "http://localhost:3000"}).status_code == 201


def test_import_run_and_lead_ownership_cannot_expose_product_snapshots(client, factory):
    _, owner = register(client)
    profile = create(client); first_batch = batch(client)
    payload = {"product_id": profile["id"], "batch_id": first_batch}
    run = client.post("/api/v1/analysis/runs", json=payload, headers={"Idempotency-Key": "shared-key"}).json()
    assert process_one(factory)
    with factory() as session:
        lead_id = session.scalar(select(Analysis.id))
    register(client, "other@example.test")
    other_profile = create(client); other_batch = batch(client)
    assert other_batch != first_batch
    assert client.get(f"/api/v1/messages?batch_id={first_batch}").status_code == 404
    for path in (f"/analysis/runs/{run['id']}", f"/leads?run_id={run['id']}", f"/leads/{lead_id}"):
        assert client.get("/api/v1" + path).status_code == 404
        assert client.get("/api/v1" + path, headers=owner).status_code == 200
    for body in (payload, {"product_id": profile["id"], "batch_id": other_batch}, {"product_id": other_profile["id"], "batch_id": first_batch}):
        assert client.post("/api/v1/analysis/runs", json=body, headers={"Idempotency-Key": "shared-key"}).status_code == 404
    other_run = client.post("/api/v1/analysis/runs", json={"product_id": other_profile["id"], "batch_id": other_batch}, headers={"Idempotency-Key": "shared-key"})
    assert other_run.status_code == 202 and other_run.json()["id"] != run["id"]


def test_queued_analysis_keeps_selected_product_snapshot_after_edit(client, factory):
    register(client); profile = create(client); imported = batch(client)
    response = client.post("/api/v1/analysis/runs", json={"product_id": profile["id"], "batch_id": imported}, headers={"Idempotency-Key": "snapshot"})
    assert response.status_code == 202
    assert client.patch(f"/api/v1/products/{profile['id']}", json={"name": "Changed later"}).status_code == 200
    with factory() as session:
        run = session.get(AnalysisRun, response.json()["id"])
        assert run.product_id == profile["id"] and run.product_snapshot["name"] == PROFILE["name"]
        assert "owner_user_id" not in run.product_snapshot


@pytest.mark.parametrize("profile", [PROFILE,
    {"name": "PawCare Veterinary Clinic", "description": "Consultations and orthopedic treatment for dogs and cats.", "target_customer": "Pet owners"},
    {"name": "LedgerFlow", "description": "Accounting, invoicing and financial reporting software.", "target_customer": "Small-business finance teams"}])
def test_selected_business_reaches_real_agent_through_existing_telegram_flow(client, factory, monkeypatch, profile):
    register(client); product = create(client, profile)
    monkeypatch.setattr(settings(), "provider_mode", "real")
    for key, value in {"LLM_PROVIDER": "avalai", "OPENAI_MODEL": "gpt-5.6-luna", "OPENAI_BASE_URL": "https://api.avalai.ir/v1",
                       "OPENAI_API_KEY": "fake-business-test-key", "TELEGRAM_WEBHOOK_SECRET": "fake-business-test-secret"}.items():
        monkeypatch.setenv(key, value)
    assert client.post("/api/v1/integrations/telegram/chats", json={"product_id": product["id"], "telegram_chat_id": -100123}).status_code == 201
    captured, requests = [], []
    original = worker_adapter.analyze_agent
    def spy(inputs):
        captured.append(inputs)
        return original(inputs)
    monkeypatch.setattr(worker_adapter, "analyze_agent", spy)
    def respond(request):
        requests.append(request)
        body = json.loads(request.content)
        data = json.loads(body["input"][-1]["content"])
        assert {k: data["product"][k] for k in PROFILE} == profile
        target = data["target"]
        qualification = dict(intent="searching_for_product", need="The author requests help.", purchase_intent=.8,
            product_fit=.8, need_strength=.8, urgency=0, confidence=.9, response_opportunity=.8,
            evidence=[dict(message_id=target["id"], quote=target["content"], reason="Explicit request")], limitations=[])
        return httpx.Response(200, json=dict(status="completed", model=body["model"],
            output=[dict(type="message", content=[dict(type="output_text", text=json.dumps(qualification))])], usage=dict(input_tokens=100, output_tokens=50)))
    update = {"update_id": 1, "message": {"message_id": 2, "date": 1791453600, "chat": {"id": -100123, "type": "supergroup"},
              "from": {"id": 3, "first_name": "Alex", "is_bot": False}, "text": "I'm looking for help. How much does it cost?"}}
    with httpx.Client(transport=httpx.MockTransport(respond)) as http, real_provider_client(http):
        queued = client.post("/integrations/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "fake-business-test-secret"})
        assert queued.status_code == 200 and queued.json()["status"] == "queued" and not requests
        assert process_one(factory)
    assert len(captured) == len(requests) == 1
    assert captured[0].product.model_dump() == {"id": product["id"], **profile}
    with factory() as session:
        run = session.scalar(select(AnalysisRun))
        analysis = session.scalar(select(Analysis))
        assert run.product_id == product["id"] and analysis.status == "completed"
        run_id, analysis_id = run.id, analysis.id
    assert client.get(f"/api/v1/analysis/runs/{run_id}").json()["product_id"] == product["id"]
    detail = client.get(f"/api/v1/leads/{analysis_id}")
    assert detail.status_code == 200 and detail.json()["analysis"]["provider_mode"] == "real"
    assert detail.json()["product_snapshot"]["name"] == profile["name"]


def test_telegram_mapping_requires_current_owners_product_even_with_adapter(client, monkeypatch):
    from app.main import app
    register(client); product = create(client)
    register(client, "other@example.test")
    monkeypatch.setattr(app.state, "telegram_product_access", lambda *args: True, raising=False)
    assert client.post("/api/v1/integrations/telegram/chats", json={"product_id": product["id"], "telegram_chat_id": -100123}).status_code == 404


def test_openapi_has_authentication_and_required_product_fields():
    from app.main import app
    schema = app.openapi()
    for path in ("/api/v1/products", "/api/v1/products/{id}", "/api/v1/analysis/runs"):
        for operation in schema["paths"][path].values():
            assert operation["security"] == [{"BackendSession": []}, {"BrowserSession": []}]
    assert schema["components"]["schemas"]["ProductInput"]["required"] == ["name", "description", "target_customer"]
    from app.auth.contracts import CurrentUser
    fixture = Path(__file__).resolve().parents[2] / "contracts/examples/current_user.json"
    assert CurrentUser.model_validate_json(fixture.read_text()).email == "owner@example.test"


def test_readiness_checks_migration_and_required_tables(client, factory):
    with factory() as session:
        session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        session.execute(text("INSERT INTO alembic_version VALUES ('0001')")); session.commit()
    assert client.get("/api/v1/ready").status_code == 503
    with factory() as session:
        session.execute(text("UPDATE alembic_version SET version_num='0004'")); session.commit()
    assert client.get("/api/v1/ready").json() == {"status": "ready", "revision": "0004"}
    with factory() as session:
        AuthSession.__table__.drop(session.get_bind())
    assert client.get("/api/v1/ready").status_code == 503


@pytest.mark.parametrize("body", [{"email": "bad-email", "password": "offline-test-password"},
                                  {"email": "owner@example.test", "password": "short"}])
def test_invalid_credentials_are_not_echoed(client, body):
    response = client.post("/api/v1/auth/register", json=body)
    assert response.status_code == 422 and body["password"] not in response.text


def test_invalid_bearer_does_not_fall_back_to_valid_cookie(client):
    register(client)
    assert client.get("/api/v1/products", headers={"Authorization": "Basic invalid"}).status_code == 401
    assert client.get("/api/v1/products", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_telegram_ownership_mismatch_does_not_ingest(client, factory, monkeypatch):
    from app.integrations.telegram.ingestion import ingest
    from app.integrations.telegram.models import TelegramChatMapping
    from app.integrations.telegram.normalization import normalize_update
    from app.core.errors import AppError
    register(client); product = create(client)
    assert client.post("/api/v1/integrations/telegram/chats", json={"product_id": product["id"], "telegram_chat_id": -100123}).status_code == 201
    with factory() as session:
        session.scalar(select(TelegramChatMapping)).owner_user_id = str(uuid4())
        session.commit()
        source = normalize_update({"update_id": 1, "message": {"message_id": 2, "date": 1791453600,
            "chat": {"id": -100123, "type": "supergroup"}, "from": {"id": 3, "first_name": "Alex", "is_bot": False}, "text": "I need help"}})
        with pytest.raises(AppError) as caught:
            ingest(session, source)
        assert caught.value.code == "telegram_ownership_unavailable"
        assert session.scalar(select(AnalysisRun)) is None


def test_shared_auth_adapter_uses_same_login_lookup_and_revocation(client, factory, monkeypatch):
    from app.auth.contracts import CurrentUser, SessionGrant
    from app.main import app
    user, _ = register(client)
    user = CurrentUser.model_validate(user)
    class Adapter:
        active = False
        def login(self, credentials):
            self.active = True
            return SessionGrant(user=user, token="fake-adapter-session", expires_at=utcnow() + timedelta(hours=24))
        def current_user(self, token):
            if token != "fake-adapter-session" or not self.active:
                raise ValueError("expired")
            return user
        def logout(self, token):
            self.active = False
    adapter = Adapter()
    monkeypatch.setattr(app.state, "telegram_auth_service", adapter, raising=False)
    assert client.post("/api/v1/auth/login", json={"email": user.email, "password": "offline-test-password"}).status_code == 200
    assert client.get("/api/v1/auth/me").json()["id"] == str(user.id)
    assert create(client)["name"] == PROFILE["name"]
    assert client.post("/api/v1/auth/logout").status_code == 204 and not adapter.active
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer fake-adapter-session"}).status_code == 401


def test_telegram_unassigned_historical_batch_requires_verified_backfill(client, factory, monkeypatch):
    import hashlib
    from app.integrations.telegram.ingestion import ingest
    from app.integrations.telegram.models import TelegramChatMapping
    from app.integrations.telegram.normalization import normalize_update
    from app.core.errors import AppError
    register(client); product = create(client)
    assert client.post("/api/v1/integrations/telegram/chats", json={"product_id": product["id"], "telegram_chat_id": -100123}).status_code == 201
    monkeypatch.setattr(settings(), "provider_mode", "real")
    source = normalize_update({"update_id": 1, "message": {"message_id": 2, "date": 1791453600,
        "chat": {"id": -100123, "type": "supergroup"}, "from": {"id": 3, "first_name": "Alex", "is_bot": False}, "text": "I need help"}})
    with factory() as session:
        mapping = session.scalar(select(TelegramChatMapping))
        namespace = "telegram:" + mapping.id + ":" + source.conversation_id
        session.add(ImportBatch(community_name=namespace, checksum=hashlib.sha256(namespace.encode()).hexdigest(), filename="telegram", row_count=0))
        session.commit()
        with pytest.raises(AppError) as caught:
            ingest(session, source)
        assert caught.value.code == "telegram_ownership_unavailable"
        assert session.scalar(select(AnalysisRun)) is None
