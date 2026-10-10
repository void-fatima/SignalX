from datetime import timedelta
from sqlalchemy import select
import httpx
import pytest
from app.discovery import service
from app.discovery.providers import PublicAPIProvider
from app.discovery.models import DiscoverySearch, DiscoveryProspect, DiscoveryBudget
from app.models import AnalysisRun, Usage, utcnow

@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY","offline-search-key")
    monkeypatch.setenv("DISCOVERY_BRAVE_STORAGE_ALLOWED","true")
    requests=[]
    def handle(request):
        requests.append(request)
        return httpx.Response(200,json={"web":{"results":[{"title":"Acme finance","url":"https://acme.example.com/finance","description":"We use invoicing tools"}]}})
    fake=httpx.Client(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(service,"get_discovery_provider",lambda source:PublicAPIProvider(source,client=fake))
    return requests

def product(client):
    response=client.post("/api/v1/products",json={"name":"LedgerFlow","description":"Accounting and invoices","target_customer":"Finance teams"})
    assert response.status_code==201
    return response.json()["id"]

def search(client,id,key="search-1",**updates):
    return client.post("/api/v1/discovery/searches",json={"product_id":id,"source":"brave","keywords":"invoices",**updates},headers={"Idempotency-Key":key})

def test_search_preview_save_history_no_model_calls(client,factory,source):
    id=product(client); response=search(client,id)
    assert response.status_code==200
    result=response.json(); assert result["status"]=="completed" and result["request_count"]==1
    assert result["estimated_cost_usd"] is None and result["cost_status"]=="unknown"
    assert result["results"][0]["signal"]=="not_evaluated"
    selected={"search_id":result["id"],"source_ids":[result["results"][0]["source_id"]]}
    saved=client.post("/api/v1/discovery/prospects",json=selected).json()
    repeated=client.post("/api/v1/discovery/prospects",json=selected).json()
    assert saved[0]["id"]==repeated[0]["id"] and saved[0]["product_id"]==id
    assert saved[0]["qualification_status"]=="not_requested" and saved[0]["qualification_usage"]==[]
    assert len(client.get("/api/v1/discovery/searches").json())==1
    assert len(client.get("/api/v1/discovery/prospects").json())==1
    assert len(source)==1
    with factory() as session:
        assert session.scalar(select(AnalysisRun)) is None and session.scalar(select(Usage)) is None

def test_idempotency_cache_and_conflicting_inputs(client,source):
    id=product(client); first=search(client,id).json()
    replay=search(client,id).json(); cached=search(client,id,"other-key").json()
    assert first["id"]==replay["id"]==cached["id"] and replay["request_count"]==cached["request_count"]==0
    assert len(source)==1
    assert search(client,id,keywords="other query").status_code==409

def test_ownership_and_auth_isolation(client,factory,source):
    id=product(client); result=search(client,id).json()
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/discovery/searches").status_code==401
    credentials={"email":"other@example.test","password":"correct horse battery"}
    assert client.post("/api/v1/auth/register",json=credentials).status_code==201
    assert client.post("/api/v1/auth/login",json=credentials).status_code==200
    assert client.get("/api/v1/discovery/searches").json()==[]
    assert client.get(f"/api/v1/discovery/searches/{result['id']}").status_code==404
    assert search(client,id).status_code==404
    assert client.post("/api/v1/discovery/prospects",json={"search_id":result["id"],"source_ids":[result["results"][0]["source_id"]]}).status_code==404
    assert len(source)==1

def test_invalid_selection_is_atomic_and_origin_protected(client,factory,source):
    result=search(client,product(client)).json()
    selected={"search_id":result["id"],"source_ids":[result["results"][0]["source_id"],"foreign"]}
    assert client.post("/api/v1/discovery/prospects",json=selected).status_code==422
    assert client.post("/api/v1/discovery/prospects",json=selected,headers={"Origin":"https://foreign.example.com"}).status_code==403
    with factory() as session: assert session.scalar(select(DiscoveryProspect)) is None

def test_rate_limits_before_http_and_configuration_specific(client,source,monkeypatch):
    id=product(client); search(client,id)
    assert search(client,id,"new",keywords="different").status_code==429
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY")
    assert search(client,id,"missing",keywords="different").status_code==503
    items=client.get("/api/v1/discovery/sources").json()["items"]
    assert not next(s for s in items if s["source"]=="brave")["configured"]
    assert next(s for s in items if s["source"]=="lever")["configured"]
    assert len(source)==1

def test_provider_failure_persisted_no_automatic_retry(client,monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY","offline-search-key"); monkeypatch.setenv("DISCOVERY_BRAVE_STORAGE_ALLOWED","true")
    requests=[]
    def handle(request): requests.append(request); return httpx.Response(429,json={"error":"secret"})
    fake=httpx.Client(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(service,"get_discovery_provider",lambda source:PublicAPIProvider(source,client=fake))
    id=product(client); failed=search(client,id).json(); replay=search(client,id).json()
    assert failed["status"]==replay["status"]=="failed" and failed["error_code"]=="source_rate_limit"
    assert "secret" not in failed["error"] and len(requests)==1
