import json
from uuid import uuid4
import httpx
import pytest
from app.discovery.providers import PublicAPIProvider, DiscoveryError, public_url, source_status, MAX_BODY_BYTES
from app.discovery.schemas import SearchInput

@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY","offline-search-key")
    monkeypatch.setenv("DISCOVERY_BRAVE_STORAGE_ALLOWED","true")
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY","offline-places-key")
    monkeypatch.setenv("DISCOVERY_PLACES_ENABLED","true")

def inputs(source="brave", **updates):
    return SearchInput.model_validate(dict(product_id=str(uuid4()),source=source,keywords="accounting",limit=2,**updates))

def provider(source, response):
    requests=[]
    def handle(request):
        requests.append(request)
        if isinstance(response,Exception): raise response
        return response
    return PublicAPIProvider(source,client=httpx.Client(transport=httpx.MockTransport(handle))),requests

@pytest.mark.parametrize("url", ["http://example.com", "https://localhost/a", "https://127.0.0.1/a", "https://[::1]/a", "https://10.0.0.1/a", "https://user:pass@example.com/a", "https://example.com:8080/a", "javascript:alert(1)", "https://internal/a", "https://service.local/a", "https://example.com\\@127.0.0.1", "https://2130706433/a"])
def test_unsafe_source_links_rejected(url):
    with pytest.raises(ValueError): public_url(url)

def test_web_normalizes_deduplicates_and_preserves_source_excerpts(configured):
    body={"web":{"results":[{"title":"<b>Acme</b>","url":"https://acme.example.com/a?utm_source=x","description":"Accounting <em>tools</em>"},{"title":"Duplicate","url":"https://acme.example.com/a","description":"same"},{"title":"Internal","url":"https://127.0.0.1/a"}]}}
    p,requests=provider("brave",httpx.Response(200,json=body))
    result=p.search(inputs(country="DE",location="Berlin"))
    assert len(result)==1 and result[0].title=="Acme" and result[0].excerpt=="Accounting tools"
    assert result[0].url=="https://acme.example.com/a"
    assert result[0].signal=="not_evaluated"
    assert len(requests)==1 and requests[0].url.host=="api.search.brave.com"
    assert requests[0].headers["X-Subscription-Token"]=="offline-search-key"
    assert requests[0].url.params["count"]=="2" and requests[0].url.params["country"]=="DE"

@pytest.mark.parametrize("source",["greenhouse","lever"])
def test_public_jobs_are_company_scoped_and_not_purchase_intent(source):
    item=dict(id="1",title="Accounting specialist",text="Accounting specialist",absolute_url="https://jobs.example.com/1",hostedUrl="https://jobs.example.com/1",content="Finance operations",descriptionPlain="Finance operations",location={"name":"Berlin"},categories={"location":"Berlin"})
    p,requests=provider(source,httpx.Response(200,json={"jobs":[item]} if source=="greenhouse" else [item]))
    result=p.search(inputs(source,board_slug="acme",location="Berlin"))
    assert result[0].title.startswith("acme:") and "not evidence of buying intent" in result[0].explanation
    assert len(requests)==1 and "/acme" in requests[0].url.path
    assert "Authorization" not in requests[0].headers

def test_places_requests_and_retains_only_ids(configured):
    p,requests=provider("places",httpx.Response(200,json={"places":[{"id":"ChIJ-example","displayName":{"text":"Private listing name"},"formattedAddress":"Do not retain"}],"nextPageToken":"not-followed"}))
    result=p.search(inputs("places",location="Berlin"))
    assert requests[0].headers["X-Goog-FieldMask"]=="places.id"
    assert json.loads(requests[0].content)["pageSize"]==2
    assert result[0].source_id=="ChIJ-example" and result[0].location==""
    assert "Private listing name" not in result[0].model_dump_json() and "Do not retain" not in result[0].model_dump_json()
    assert len(requests)==1

@pytest.mark.parametrize("source,key",[("brave","BRAVE_SEARCH_API_KEY"),("places","GOOGLE_PLACES_API_KEY")])
def test_missing_credentials_no_http(source,key,monkeypatch):
    monkeypatch.delenv(key,raising=False)
    p,requests=provider(source,httpx.Response(200,json={}))
    with pytest.raises(DiscoveryError) as error: p.search(inputs(source,**({"location":"Berlin"} if source=="places" else {})))
    assert error.value.code=="configuration_required" and error.value.request_count==0 and not requests

@pytest.mark.parametrize("status",[400,401,403,404,429,500])
def test_errors_are_safe_and_never_retried(status,configured):
    p,requests=provider("brave",httpx.Response(status,json={"error":"secret-auth-header offline-search-key"}))
    with pytest.raises(DiscoveryError) as error: p.search(inputs())
    assert "secret-auth" not in str(error.value) and "offline-search-key" not in str(error.value)
    assert error.value.request_count==1 and len(requests)==1

@pytest.mark.parametrize("response,code",[(httpx.ReadTimeout("secret"),"source_timeout"),(httpx.ConnectError("secret"),"source_transport"),(httpx.Response(200,content=b"not JSON"),"source_invalid_output"),(httpx.Response(200,content=b"x"*(MAX_BODY_BYTES+1)),"source_response_too_large")])
def test_timeout_transport_malformed_and_size_budget(response,code,configured):
    p,requests=provider("brave",response)
    with pytest.raises(DiscoveryError) as error: p.search(inputs())
    assert error.value.code==code and len(requests)==1 and "secret" not in str(error.value)
