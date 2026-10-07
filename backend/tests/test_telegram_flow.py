"""SQLite + real Agent entry point + fake HTTP: no external calls or fake auth in production."""
import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.auth.contracts import CurrentUser
from app.core.config import settings
from app.integrations.telegram import dependencies
from app.integrations.telegram.client import TelegramClient
from app.integrations.telegram.config import TelegramSettings
from app.integrations.telegram.models import TelegramChatMapping, TelegramDelivery, TelegramReceipt
from app.main import app
from app.models import Analysis, AnalysisRun, ImportBatch, Message, Product, Usage, User
from app.agents.providers.factory import real_provider_client
from app.services.analysis_service import process_one

TOKEN = "123456:fake-telegram-flow-token"
SECRET = "fake-telegram-flow-secret"
OWNER = str(uuid4())
HEADERS = {"Authorization": "Bearer fake-auth-token"}


def update(update_id=10, message_id=7, chat=-100123, text="I need a Python course for beginners. How much?", thread=None, reply=None):
    message = dict(message_id=message_id, date=1791360000 + message_id,
        chat=dict(id=chat, type="supergroup", title="Test group"), text=text,
        **{"from": dict(id=8, is_bot=False, first_name="User", username="test_user")})
    if thread is not None:
        message["message_thread_id"] = thread
    if reply is not None:
        message["reply_to_message"] = dict(message_id=reply, chat=dict(id=chat))
    return dict(update_id=update_id, message=message)


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    for name, value in dict(TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_WEBHOOK_SECRET=SECRET,
        TELEGRAM_WEBHOOK_PATH="/integrations/telegram/webhook", TELEGRAM_TIMEOUT_SECONDS="15",
        LLM_PROVIDER="avalai", OPENAI_MODEL="gpt-5.6-luna", OPENAI_BASE_URL="https://api.avalai.ir/v1",
        OPENAI_API_KEY="fake-telegram-flow-llm-key").items():
        monkeypatch.setenv(name, value)
    for name in ("OPENAI_PRICE_VERSION", "OPENAI_INPUT_USD_PER_MILLION", "OPENAI_OUTPUT_USD_PER_MILLION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings(), "provider_mode", "real")
    class Auth:
        def current_user(self, token):
            if token != "fake-auth-token":
                raise ValueError("invalid session")
            return CurrentUser(id=OWNER, email="user@example.test", created_at=datetime.now(timezone.utc))
    monkeypatch.setattr(app.state, "telegram_auth_service", Auth(), raising=False)
    monkeypatch.setattr(app.state, "telegram_product_access", lambda user, product_id: True, raising=False)


@pytest.fixture
def business(factory):
    with factory() as session:
        session.add(User(id=OWNER, email="user@example.test", password_hash="external-test-auth"))
        session.flush()
        product = Product(owner_user_id=OWNER, name="Python Starter Course", description="Beginner Python course.", target_customer="Beginners",
            problems_solved=[], best_fit=[], not_fit=[], currency="USD")
        session.add(product)
        session.flush()
        session.add(TelegramChatMapping(owner_user_id=OWNER, product_id=product.id, telegram_chat_id=-100123))
        session.commit()
        return product.id


@pytest.fixture
def llm_http():
    requests = []
    def handle(request):
        requests.append(request)
        body = json.loads(request.content)
        if body["text"]["format"]["name"] == "qualification":
            source = json.loads(body["input"][-1]["content"])
            target = source["target"]
            value = dict(intent="asking_price", need=target["content"], purchase_intent=.8,
                product_fit=.9, need_strength=.8, urgency=0., confidence=.9, response_opportunity=.8,
                evidence=[dict(message_id=target["id"], quote=target["content"], reason="Actual target")], limitations=[])
        else:
            value = dict(parts=[dict(kind="question", text="What would you like to learn?", product_field=None)])
        return httpx.Response(200, json=dict(status="completed", model=body["model"],
            output=[dict(type="message", content=[dict(type="output_text", text=json.dumps(value, ensure_ascii=False))])],
            usage=dict(input_tokens=100, output_tokens=50, input_tokens_details=dict(cached_tokens=0))))
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with real_provider_client(http):
            yield requests


@pytest.fixture
def telegram_http(client):
    requests = []
    def handle(request):
        requests.append(request)
        body = json.loads(request.content)
        return httpx.Response(200, json=dict(ok=True, result=dict(message_id=99, chat=dict(id=body["chat_id"]))))
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        app.dependency_overrides[dependencies.telegram_client] = lambda: TelegramClient(TelegramSettings(), client=http)
        yield requests
        app.dependency_overrides.pop(dependencies.telegram_client, None)


def post(client, payload, **kwargs):
    return client.post("/integrations/telegram/webhook", json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, **kwargs)


def complete(client, factory, payload=None):
    assert post(client, payload or update()).json()["status"] == "queued"
    assert process_one(factory)
    with factory() as session:
        analysis = session.scalar(select(Analysis).order_by(Analysis.created_at.desc()))
        assert analysis.status == "completed"
        return analysis.id


@pytest.mark.parametrize("secret", [None, "wrong", "x" * 257, "سلام"])
def test_invalid_webhook_secret_no_storage(client, factory, secret):
    headers = {} if secret is None else {"X-Telegram-Bot-Api-Secret-Token": secret}
    # HTTP headers are ASCII; send UTF-8 bytes explicitly for the malformed case.
    if secret == "سلام":
        headers = [(b"X-Telegram-Bot-Api-Secret-Token", secret.encode())]
    response = client.post("/integrations/telegram/webhook", json=update(), headers=headers)
    assert response.status_code == 403
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Message)) == 0


@pytest.mark.parametrize("text", ["I need a Python course", "دنبال دوره پایتون هستم. قیمتش چقدره؟"])
def test_webhook_only_enqueues_correct_business_and_preserves_metadata(client, factory, business, llm_http, text):
    assert post(client, update(text=text, thread=3, reply=6)).json()["status"] == "queued"
    assert llm_http == []  # No Agent/provider call in the webhook.
    with factory() as session:
        run = session.scalar(select(AnalysisRun))
        receipt = session.scalar(select(TelegramReceipt))
        message = session.scalar(select(Message))
        assert run.status == "queued" and run.total_count == 1 and run.product_id == business
        assert run.config_snapshot["provider_mode"] == "real"
        assert message.content == text and message.external_id == "7" and message.reply_to_external_id == "6"
        assert receipt.source_metadata["message_thread_id"] == 3 and receipt.agent_output is None


@pytest.mark.parametrize("changed_update", [False, True])
def test_duplicate_delivery_creates_one_message_job_analysis_lead(client, factory, business, llm_http, changed_update):
    first = update()
    assert post(client, first).json()["status"] == "queued"
    duplicate = {**first, "update_id": 11} if changed_update else first
    assert post(client, duplicate).json()["status"] == "duplicate"
    assert process_one(factory) and not process_one(factory)
    assert len(llm_http) == 1
    with factory() as session:
        for model in (Message, AnalysisRun, Analysis, TelegramReceipt):
            assert session.scalar(select(func.count()).select_from(model)) == 1


def test_unmapped_chat_and_ignored_updates_never_enqueue(client, factory, llm_http):
    assert post(client, update()).json()["status"] == "unmapped"
    payload = update()
    payload["message"]["from"]["is_bot"] = True
    assert post(client, payload).json()["status"] == "ignored"
    assert llm_http == []
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Message)) == 0


def test_real_worker_uses_agent_and_no_automatic_send(client, factory, business, llm_http, telegram_http):
    id = complete(client, factory)
    detail = client.get(f"/api/v1/leads/{id}/telegram", headers=HEADERS)
    assert detail.status_code == 200
    body = detail.json()
    assert body["source"] == "telegram" and body["product_id"] == business
    assert body["analysis"]["scoring"]["decision"] == "RESPOND"
    assert body["analysis"]["suggested_reply"] is None and body["delivery"]["status"] == "not_sent"
    assert body["analysis"]["prompt_version"] == "qualify_real_v1"
    assert body["analysis"]["usage"][0]["estimated_cost"] is None
    assert len(llm_http) == 1 and not telegram_http
    with factory() as session:
        usage = session.scalar(select(Usage))
        assert usage.cost_usd is None and usage.cost_status == "unknown"


def test_context_stays_in_chat_topic_and_only_new_target_is_analyzed(client, factory, business, llm_http):
    for payload in [update(10, 7, text="Has anyone tried this Python course?", thread=3),
                    update(11, 8, text="I need help with Python", thread=4),
                    update(12, 9, text="Yes, but too expensive", thread=3, reply=7)]:
        assert post(client, payload).json()["status"] == "queued"
        assert process_one(factory)
    assert len(llm_http) == 3
    last = json.loads(json.loads(llm_http[-1].content)["input"][-1]["content"])
    assert last["target"]["content"] == "Yes, but too expensive"
    assert [m["content"] for m in last["context"]] == ["Has anyone tried this Python course?"]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Analysis)) == 3


def test_human_send_replies_to_original_and_never_changes_analysis(client, factory, business, llm_http, telegram_http):
    id = complete(client, factory, update(thread=3))
    before = client.get(f"/api/v1/leads/{id}/telegram", headers=HEADERS).json()["analysis"]
    response = client.post(f"/api/v1/leads/{id}/telegram/reply", headers=HEADERS, json=dict(text="Human-approved reply"))
    assert response.status_code == 200
    assert response.json()["analysis"] == before and response.json()["delivery"]["status"] == "sent"
    assert response.json()["delivery"]["telegram_message_id"] == 99
    assert len(llm_http) == 1 and len(telegram_http) == 1
    sent = json.loads(telegram_http[0].content)
    assert sent["chat_id"] == -100123 and sent["reply_parameters"]["message_id"] == 7 and sent["message_thread_id"] == 3
    # Browser retry with identical approved text returns the recorded delivery.
    assert client.post(f"/api/v1/leads/{id}/telegram/reply", headers=HEADERS, json=dict(text="Human-approved reply")).status_code == 200
    assert len(telegram_http) == 1


@pytest.mark.parametrize("text", ["", " ", "x" * 4001])
def test_empty_or_oversized_reply_rejected(client, factory, business, llm_http, telegram_http, text):
    id = complete(client, factory)
    assert client.post(f"/api/v1/leads/{id}/telegram/reply", headers=HEADERS, json=dict(text=text)).status_code == 422
    assert not telegram_http


def test_auth_and_cross_user_ownership_enforced(client, factory, business, llm_http, telegram_http, monkeypatch):
    id = complete(client, factory)
    for headers in ({}, {"Authorization": "Bearer invalid"}):
        assert client.post(f"/api/v1/leads/{id}/telegram/reply", headers=headers, json=dict(text="Human reply")).status_code == 401
    with factory() as session:
        session.scalar(select(TelegramChatMapping)).owner_user_id = str(uuid4())
        session.commit()
    assert client.get(f"/api/v1/leads/{id}/telegram", headers=HEADERS).status_code == 404
    assert client.post(f"/api/v1/leads/{id}/telegram/reply", headers=HEADERS, json=dict(text="Human reply")).status_code == 404
    assert client.get("/api/v1/integrations/telegram/leads", headers=HEADERS).json()["total"] == 0
    assert not telegram_http


def test_missing_auth_adapter_fails_closed(client, business, monkeypatch, telegram_http):
    monkeypatch.setattr(app.state, "telegram_auth_service", None)
    assert client.post(f"/api/v1/leads/{uuid4()}/telegram/reply", headers=HEADERS, json=dict(text="Human reply")).status_code == 503
    assert not telegram_http


def test_mapping_requires_real_backend_product_ownership(client, factory, business, monkeypatch):
    path = "/api/v1/integrations/telegram/chats"
    payload = dict(product_id=business, telegram_chat_id=-100456)
    monkeypatch.delattr(app.state, "telegram_product_access")
    # The real database ownership adapter now replaces the previously missing bridge.
    with factory() as session:
        session.get(Product, business).owner_user_id = None
        session.commit()
    assert client.post(path, json=payload, headers=HEADERS).status_code == 404
    with factory() as session:
        session.get(Product, business).owner_user_id = OWNER
        session.commit()
    monkeypatch.setattr(app.state, "telegram_product_access", lambda *a: False, raising=False)
    assert client.post(path, json=payload, headers=HEADERS).status_code == 404
    monkeypatch.setattr(app.state, "telegram_product_access", lambda *a: True)
    assert client.post(path, json=payload, headers=HEADERS).status_code == 201


@pytest.mark.parametrize("corruption", ["missing", "wrong_chat", "wrong_message"])
def test_missing_or_mismatched_original_metadata_never_sends(client, factory, business, llm_http, telegram_http, corruption):
    id = complete(client, factory)
    with factory() as session:
        receipt = session.scalar(select(TelegramReceipt))
        values = dict(receipt.source_metadata)
        if corruption == "missing":
            values.pop("message_id")
        elif corruption == "wrong_chat":
            values["chat_id"] = -100456
        else:
            values["message_id"] = 88
        receipt.source_metadata = values
        session.commit()
    assert client.post(f"/api/v1/leads/{id}/telegram/reply", headers=HEADERS, json=dict(text="Human reply")).status_code == 409
    assert not telegram_http


def test_suggested_reply_reuses_qualification_and_appends_usage_only(client, factory, business, llm_http, telegram_http):
    id = complete(client, factory)
    path = f"/api/v1/leads/{id}/telegram/suggested-reply"
    before = client.get(f"/api/v1/leads/{id}/telegram", headers=HEADERS).json()["analysis"]
    response = client.post(path, json={}, headers=HEADERS)
    assert response.status_code == 200
    after = response.json()["analysis"]
    assert after["scoring"] == before["scoring"] and after["qualification"] == before["qualification"]
    assert after["suggested_reply"] == "What would you like to learn?"
    assert [u["stage"] for u in after["usage"]] == ["qualification", "suggested_reply"]
    assert client.post(path, json={}, headers=HEADERS).status_code == 200
    assert len(llm_http) == 2 and not telegram_http


def test_uncertain_delivery_prevents_resend(client, factory, business, llm_http, monkeypatch):
    id = complete(client, factory)
    calls = []
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout(TOKEN)
    with httpx.Client(transport=httpx.MockTransport(timeout)) as http:
        app.dependency_overrides[dependencies.telegram_client] = lambda: TelegramClient(TelegramSettings(), client=http)
        path = f"/api/v1/leads/{id}/telegram/reply"
        first = client.post(path, headers=HEADERS, json=dict(text="Human reply"))
        assert first.status_code == 502 and TOKEN not in first.text
        assert client.post(path, headers=HEADERS, json=dict(text="Human reply")).status_code == 409
        app.dependency_overrides.pop(dependencies.telegram_client, None)
    assert len(calls) == 1
    detail = client.get(f"/api/v1/leads/{id}/telegram", headers=HEADERS).json()
    assert detail["delivery"]["status"] == "failed" and detail["delivery"]["delivery_uncertain"]


def test_non_telegram_lead_rejected_without_sending(client, factory, business, llm_http, telegram_http):
    id = complete(client, factory)
    with factory() as session:
        receipt = session.scalar(select(TelegramReceipt))
        session.delete(receipt)
        session.commit()
    assert client.post(f"/api/v1/leads/{id}/telegram/reply", headers=HEADERS, json=dict(text="Human reply")).status_code == 409
    assert not telegram_http


def test_different_chats_select_different_businesses(client, factory, business, llm_http):
    with factory() as session:
        product = Product(owner_user_id=OWNER, name="Vet clinic", description="Care for pets", target_customer="Pet owners",
            problems_solved=[], best_fit=[], not_fit=[], currency="USD")
        session.add(product)
        session.flush()
        other_id = product.id
        session.add(TelegramChatMapping(owner_user_id=OWNER, product_id=other_id, telegram_chat_id=-100456))
        session.commit()
    for payload in (update(), update(11, 8, chat=-100456, text="My dog needs care. What does it cost?")):
        assert post(client, payload).json()["status"] == "queued"
        assert process_one(factory)
    names = [json.loads(json.loads(r.content)["input"][-1]["content"])["product"]["name"] for r in llm_http]
    assert names == ["Python Starter Course", "Vet clinic"]


def test_disabled_mapping_does_not_enqueue_or_send(client, factory, business, llm_http, telegram_http):
    id = complete(client, factory)
    with factory() as session:
        session.scalar(select(TelegramChatMapping)).enabled = False
        session.commit()
    assert post(client, update(11, 8)).json()["status"] == "unmapped"
    assert client.post(f"/api/v1/leads/{id}/telegram/reply", headers=HEADERS, json=dict(text="Human reply")).status_code == 409
    assert not telegram_http


def test_provider_mode_must_not_silently_default_to_mock(client, business, monkeypatch, llm_http):
    monkeypatch.setattr(settings(), "provider_mode", "mock")
    assert post(client, update()).status_code == 503
    assert not llm_http


def test_update_id_reuse_for_another_message_is_a_conflict(client, factory, business):
    assert post(client, update()).json()["status"] == "queued"
    assert post(client, update(message_id=8)).status_code == 409
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Message)) == 1


def test_missing_telegram_schema_returns_safe_retryable_error(client, factory, business):
    with factory() as session:
        TelegramReceipt.__table__.drop(session.get_bind())
    response = post(client, update())
    assert response.status_code == 503 and response.json()["error"]["code"] == "telegram_storage_unavailable"
    assert TOKEN not in response.text and SECRET not in response.text


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500])
def test_api_failure_persists_delivery_status_without_changing_analysis(client, factory, business, llm_http, status):
    id = complete(client, factory)
    before = client.get(f"/api/v1/leads/{id}/telegram", headers=HEADERS).json()["analysis"]
    calls = []
    def failure(request):
        calls.append(request)
        return httpx.Response(status, json=dict(ok=False, error_code=status, description=TOKEN))
    with httpx.Client(transport=httpx.MockTransport(failure)) as http:
        app.dependency_overrides[dependencies.telegram_client] = lambda: TelegramClient(TelegramSettings(), client=http)
        response = client.post(f"/api/v1/leads/{id}/telegram/reply", headers=HEADERS, json=dict(text="Human reply"))
        assert response.status_code == 502 and TOKEN not in response.text
        app.dependency_overrides.pop(dependencies.telegram_client, None)
    detail = client.get(f"/api/v1/leads/{id}/telegram", headers=HEADERS).json()
    assert detail["analysis"] == before and detail["delivery"]["status"] == "failed"
    assert detail["delivery"]["delivery_uncertain"] is (status == 500) and len(calls) == 1


def test_failed_draft_preserves_actual_usage_and_no_qualification_rerun(client, factory, business, llm_http, telegram_http):
    id = complete(client, factory)
    calls = []
    def failure(request):
        calls.append(request)
        raise httpx.ReadTimeout("fake-private-provider-data")
    with httpx.Client(transport=httpx.MockTransport(failure)) as http, real_provider_client(http):
        response = client.post(f"/api/v1/leads/{id}/telegram/suggested-reply", headers=HEADERS, json={})
    assert response.status_code == 502 and len(calls) == 1 and len(llm_http) == 1
    detail = client.get(f"/api/v1/leads/{id}/telegram", headers=HEADERS).json()
    assert [u["stage"] for u in detail["analysis"]["usage"]] == ["qualification", "suggested_reply"]
    assert detail["analysis"]["usage"][-1]["outcome"] == "timeout" and not telegram_http


def test_shared_api_fixture_and_agent_contract_are_valid():
    from pathlib import Path
    from app.integrations.telegram.schemas import TelegramLeadOut
    path = Path(__file__).resolve().parents[2] / "contracts/examples/telegram_lead.json"
    fixture = TelegramLeadOut.model_validate_json(path.read_text(encoding="utf-8"))
    assert fixture.source == "telegram" and fixture.analysis.scoring.score == 76
    assert fixture.analysis.qualification.evidence[0].message_id == str(fixture.message_id)
    assert fixture.delivery.status == "not_sent"
