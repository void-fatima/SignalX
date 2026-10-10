"""Actual production Agent with fake Responses HTTP; no model/network substitution."""
import json
import httpx
import pytest
from sqlalchemy import select
from app.core.config import settings
from app.discovery import qualification as module
from app.discovery.models import DiscoveryProspect, DiscoveryBudget
from app.agents.providers.factory import real_provider_client
from app.agents.contracts import UsageInfo
from app.agents.providers.base import ProviderError
from test_discovery_api import source, product, search

@pytest.fixture
def saved(client,source):
    result=search(client,product(client)).json()
    return client.post("/api/v1/discovery/prospects",json={"search_id":result["id"],"source_ids":[result["results"][0]["source_id"]]}).json()[0]

@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE","real")
    monkeypatch.setenv("LLM_PROVIDER","avalai")
    monkeypatch.setenv("OPENAI_API_KEY","offline-qualification-key")
    monkeypatch.setenv("OPENAI_BASE_URL","https://api.avalai.ir/v1")
    monkeypatch.setenv("OPENAI_MODEL","offline-model")
    settings.cache_clear()
    yield
    settings.cache_clear()


def qualify(client,id,key="one-evaluation"):
    return client.post(f"/api/v1/discovery/prospects/{id}/qualify",headers={"Idempotency-Key":key})


def body(value,tokens=True):
    payload={"status":"completed","model":"offline-model","output":[{"type":"message","content":[{"type":"output_text","text":json.dumps(value)}]}]}
    if tokens: payload["usage"]={"input_tokens":120,"output_tokens":40,"input_tokens_details":{"cached_tokens":0}}
    return payload


def good(id):
    return dict(intent="technical_help",need="Invoicing tools",purchase_intent=.2,product_fit=.8,need_strength=.7,urgency=0,confidence=.8,response_opportunity=.4,evidence=[dict(message_id=id,quote="We use invoicing tools",reason="Source excerpt")],limitations=["No verified purchasing request"])


def test_explicit_real_evaluation_historical_profile_usage_and_idempotency(client,saved,configured,factory):
    calls=[]
    def handle(request):
        calls.append(request)
        assert request.url.host=="api.avalai.ir"
        assert request.headers["Authorization"]=="Bearer offline-qualification-key"
        return httpx.Response(200,json=body(good(saved["id"])))
    client.patch(f"/api/v1/products/{saved['product_id']}",json={"name":"Changed after search"})
    with real_provider_client(httpx.Client(transport=httpx.MockTransport(handle))):
        result=qualify(client,saved["id"]).json()
        assert qualify(client,saved["id"]).json()==result
        assert qualify(client,saved["id"],"different-key").status_code==409
    assert len(calls)==1
    supplied=json.loads(json.loads(calls[0].content)["input"][-1]["content"])
    assert supplied["product"]["name"]=="LedgerFlow" and supplied["context"]==[]
    assert "We use invoicing tools" in supplied["target"]["content"]
    assert result["qualification_status"]=="completed" and result["signal"]=="possible_need"
    assert "unverified" in result["explanation"]
    usage=result["qualification_usage"][0]
    assert usage["input_tokens"]==120 and usage["output_tokens"]==40
    assert usage["estimated_cost"] is None and usage["cost_status"]=="unknown" and usage["provider_mode"]=="real"
    with factory() as session:
        row=session.get(DiscoveryProspect,saved["id"])
        assert row.agent_output["scoring_version"]=="score_v1" and row.agent_output["suggested_reply"] is None
        assert session.scalar(select(DiscoveryBudget).where(DiscoveryBudget.source=="qualification")).request_count==1

@pytest.mark.parametrize("valid_repair",[True,False])
def test_bounded_repair_and_grounding_never_weakened(client,saved,configured,valid_repair):
    calls=[]; wrong=good(saved["id"]); wrong["evidence"][0]["quote"]="invented purchasing request"
    def handle(request):
        calls.append(request)
        return httpx.Response(200,json=body(good(saved["id"]) if len(calls)==2 and valid_repair else wrong))
    with real_provider_client(httpx.Client(transport=httpx.MockTransport(handle))):
        result=qualify(client,saved["id"]).json()
        qualify(client,saved["id"])
    assert len(calls)==2 and len(result["qualification_usage"])==2
    assert result["qualification_status"]==("completed" if valid_repair else "failed")
    assert result["qualification_usage"][0]["outcome"]=="invalid_output"
    assert result["qualification_usage"][1]["stage"]=="qualification_repair"
    if not valid_repair: assert result["signal"]=="not_evaluated"

@pytest.mark.parametrize("status",[401,403,429,500])
def test_provider_error_usage_retained_no_retry(client,saved,configured,status):
    calls=[]
    def handle(request): calls.append(request); return httpx.Response(status,json={"error":{"message":"private upstream value"}})
    with real_provider_client(httpx.Client(transport=httpx.MockTransport(handle))):
        result=qualify(client,saved["id"]).json(); qualify(client,saved["id"])
    assert len(calls)==1 and result["qualification_status"]=="failed"
    assert len(result["qualification_usage"])==1
    assert "private upstream value" not in result["qualification_error"]
    assert result["qualification_usage"][0]["input_tokens"] is None


def test_missing_real_config_no_mock_fallback(client,saved,monkeypatch):
    monkeypatch.setattr(module,"analyze_agent",lambda _:pytest.fail("Must not call any provider"))
    response=qualify(client,saved["id"])
    assert response.status_code==503 and "offline" not in response.text


def test_places_and_ownership_reject_before_provider(client,saved,configured,factory,monkeypatch):
    monkeypatch.setattr(module,"analyze_agent",lambda _:pytest.fail("Must not call any provider"))
    with factory() as session:
        row=session.get(DiscoveryProspect,saved["id"]);row.source="places";session.commit()
    assert qualify(client,saved["id"]).status_code==422
    client.post("/api/v1/auth/logout")
    credentials={"email":"foreign-qual@example.test","password":"correct horse battery"}
    client.post("/api/v1/auth/register",json=credentials);client.post("/api/v1/auth/login",json=credentials)
    assert qualify(client,saved["id"]).status_code==404


def test_unknown_usage_stays_unknown(client,saved,configured):
    with real_provider_client(httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=body(good(saved["id"]),False))))):
        result=qualify(client,saved["id"]).json()
    assert result["qualification_usage"][0]["input_tokens"] is None
    assert result["qualification_usage"][0]["estimated_cost"] is None


def test_evaluation_budget_before_model(client,saved,configured,factory,monkeypatch):
    from app.models import utcnow
    with factory() as session:
        session.add(DiscoveryBudget(source="qualification",window_started_at=utcnow(),request_count=10))
        session.commit()
    monkeypatch.setattr(module,"analyze_agent",lambda _:pytest.fail("Quota must stop before provider"))
    assert qualify(client,saved["id"]).status_code==429
    with factory() as session:
        assert session.get(DiscoveryProspect,saved["id"]).qualification_key is None


def test_projection_failure_preserves_actual_usage(client,saved,configured,factory,monkeypatch):
    from app.agents.contracts import AgentOutput,ScreeningResult
    class BrokenProjection:
        qualification=None
        usage=[UsageInfo(stage="qualification",provider_mode="real",input_tokens=120,output_tokens=40)]
        def model_dump(self,**kwargs): raise RuntimeError("private persistence detail")
    monkeypatch.setattr(module,"analyze_agent",lambda _:BrokenProjection())
    result=qualify(client,saved["id"]).json()
    assert result["qualification_status"]=="failed" and result["qualification_usage"][0]["input_tokens"]==120
    assert "private persistence detail" not in result["qualification_error"]
    with factory() as session: assert session.get(DiscoveryProspect,saved["id"]).agent_output is None
