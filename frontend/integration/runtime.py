"""Local acceptance fixture: actual backend routes, temporary SQLite, offline adapters.

Never import this from the application or deploy it. Test-only control routes are
bound to loopback. No provider or Telegram HTTP request leaves this process.
"""
import json
import os
from contextlib import ExitStack
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(DATABASE_URL="sqlite://", PROVIDER_MODE="mock", CORS_ORIGINS="http://localhost:3100",
    AUTH_COOKIE_SECURE="false", AUTH_COOKIE_SAMESITE="lax", OPENAI_TIMEOUT_SECONDS="30",
    HEARTBEAT_TIMEOUT_SECONDS="120", LLM_PROVIDER="avalai", OPENAI_MODEL="gpt-5.6-luna",
    OPENAI_BASE_URL="https://api.avalai.ir/v1", OPENAI_API_KEY="offline-test-key",
    TELEGRAM_BOT_TOKEN="123456:offline-integration-token", TELEGRAM_WEBHOOK_SECRET="offline-integration-secret")

import httpx
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.agents.contracts import UsageInfo
from app.agents.orchestrator import analyze_agent
from app.agents.providers.base import ProviderError
from app.agents.providers.factory import real_provider_client
from app.core.config import settings
from app.db.session import get_session
from app.integrations.telegram import dependencies
from app.integrations.telegram.client import TelegramClient
from app.integrations.telegram.config import TelegramSettings
from app.integrations.telegram.models import TelegramChatMapping, TelegramDelivery
from app.main import app
from app.models import Analysis, Base, utcnow
from app.services.analysis_service import process_one


def llm_response(request):
    body = json.loads(request.content)
    if body["text"]["format"]["name"] == "qualification":
        target = json.loads(body["input"][-1]["content"])["target"]
        value = dict(intent="asking_price", need=target["content"], purchase_intent=.8,
            product_fit=.9, need_strength=.8, urgency=0., confidence=.9, response_opportunity=.8,
            evidence=[dict(message_id=target["id"], quote=target["content"], reason="Test source")], limitations=[])
    else:
        value = dict(parts=[dict(kind="question", text="What would you like to learn?", product_field=None)])
    return httpx.Response(200, json=dict(status="completed", model=body["model"],
        output=[dict(type="message", content=[dict(type="output_text", text=json.dumps(value))])],
        usage=dict(input_tokens=100, output_tokens=50, input_tokens_details=dict(cached_tokens=0))))


sent_requests = []
def telegram_response(request):
    payload = json.loads(request.content)
    sent_requests.append(payload)
    chat = payload["chat_id"]
    if chat == -100503:
        raise httpx.ReadTimeout("Controlled lost acknowledgement")
    if chat == -100502 and sum(item["chat_id"] == chat for item in sent_requests) == 1:
        return httpx.Response(429, json=dict(ok=False, error_code=429, description="Controlled rate limit", parameters=dict(retry_after=60)))
    return httpx.Response(200, json=dict(ok=True, result=dict(message_id=99, chat=dict(id=chat))))


def start():
    with TemporaryDirectory(prefix="signalx-http-acceptance-") as temporary, ExitStack() as cleanup, \
        httpx.Client(transport=httpx.MockTransport(llm_response)) as llm, \
        httpx.Client(transport=httpx.MockTransport(telegram_response)) as bot:
        engine = create_engine(f"sqlite:///{Path(temporary) / 'test.db'}", connect_args={"check_same_thread": False})
        cleanup.callback(engine.dispose)
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        def database():
            with factory() as session:
                yield session
        app.dependency_overrides[get_session] = database
        app.dependency_overrides[dependencies.telegram_client] = lambda: TelegramClient(TelegramSettings(), client=bot)

        with TestClient(app) as client:
            credentials = dict(email="browser-owner@example.test", password="offline integration password")
            assert client.post("/api/v1/auth/register", json=credentials).status_code == 201
            assert client.post("/api/v1/auth/login", json=credentials).status_code == 200
            owner = client.get("/api/v1/auth/me").json()["id"]
            product = client.post("/api/v1/products", json=dict(name="Python course", description="Beginner Python course", target_customer="Beginners")).json()
            batch = client.post("/api/v1/imports", data=dict(community_name="HTTP acceptance"),
                files=dict(file=("fixture.csv", (ROOT / "data/demo_messages.csv").read_bytes(), "text/csv"))).json()["batch"]
            run = client.post("/api/v1/analysis/runs", headers={"Idempotency-Key": "offline-seed"},
                json=dict(product_id=product["id"], batch_id=batch["id"])).json()
            failed_once = False
            def partial(inputs):
                nonlocal failed_once
                if not failed_once:
                    failed_once = True
                    raise ProviderError("Controlled timeout", [UsageInfo(stage="qualification", attempt_no=1, provider_mode="mock", outcome="timeout", cost_status="mock", estimated_cost=0)])
                return analyze_agent(inputs)
            assert process_one(factory, agent_orchestrator=partial)
            fixture = dict(run_id=run["id"], product_id=product["id"], telegram={})
            settings().provider_mode = "real"  # Real adapter with injected offline HTTP, never fallback.
            for label, chat in [("sent", -100501), ("rate", -100502), ("uncertain", -100503)]:
                with factory() as session:
                    session.add(TelegramChatMapping(owner_user_id=owner, product_id=product["id"], telegram_chat_id=chat))
                    session.commit()
                update = dict(update_id=-chat, message=dict(message_id=7, date=1791360007,
                    chat=dict(id=chat, type="supergroup", title="Offline test group"), text="I need a Python course for beginners. How much?",
                    **{"from": dict(id=8, is_bot=False, first_name="Test user", username="test_user")}))
                with real_provider_client(llm):
                    queued = client.post("/integrations/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "offline-integration-secret"})
                    assert queued.json().get("status") == "queued", (queued.status_code, queued.json().get("error", {}).get("code"))
                    assert process_one(factory)
                    with factory() as session:
                        lead_id = session.scalar(select(Analysis).order_by(Analysis.created_at.desc())).id
                    assert client.post(f"/api/v1/leads/{lead_id}/telegram/suggested-reply", json=dict(regenerate=False)).status_code == 200
                fixture["telegram"][label] = lead_id

        # TestClient has already built the middleware stack; rebuild for uvicorn.
        app.middleware_stack = None
        @app.middleware("http")
        async def offline_provider(request, call_next):
            with real_provider_client(llm):
                return await call_next(request)
        @app.get("/__test/fixture")
        def fixture_view():
            return fixture
        @app.get("/__test/deliveries")
        def delivery_requests():
            return sent_requests
        @app.post("/__test/process")
        def process():
            return dict(processed=process_one(factory, agent_orchestrator=analyze_agent))
        @app.post("/__test/expire/{lead_id}")
        def expire(lead_id: str):
            from datetime import timedelta
            with factory() as session:
                delivery = session.scalar(select(TelegramDelivery).where(TelegramDelivery.analysis_id == lead_id))
                delivery.retry_after_at = utcnow() - timedelta(seconds=1)
                session.commit()
            return dict(expired=True)
        uvicorn.run(app, host="127.0.0.1", port=8000, access_log=False, log_level="warning")
        engine.dispose()


if __name__ == "__main__":
    start()
