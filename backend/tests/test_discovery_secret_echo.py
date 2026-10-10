"""Credential echo regressions: fake credentials and mocked HTTP only."""
import base64
import json
from urllib.parse import quote
import httpx
import pytest
from sqlalchemy import select
from app.discovery import service
from app.discovery.models import DiscoverySearch
from app.discovery.providers import DiscoveryError, PublicAPIProvider
from app.discovery.schemas import SearchInput
from test_discovery_api import product, search

FAKE_KEY = "fake-discovery-sensitive-key-123"


def encoded(value, kind):
    if kind == "unicode": return "".join("\\u%04x" % ord(c) for c in value)
    if kind == "percent": return "".join("%%%02X" % ord(c) for c in value)
    if kind == "double_percent": return quote(encoded(value,"percent"),safe="")
    if kind == "html": return "".join("&#%d;" % ord(c) for c in value)
    if kind == "base64": return base64.b64encode(value.encode()).decode()
    if kind == "hex": return value.encode().hex()
    raise AssertionError(kind)


@pytest.mark.parametrize("name", ["BRAVE_SEARCH_API_KEY", "GOOGLE_PLACES_API_KEY"])
@pytest.mark.parametrize("kind", ["unicode","percent","double_percent","html","base64","hex"])
@pytest.mark.parametrize("field", ["title","description","url","nested","key"])
def test_encoded_credentials_rejected_before_normalization(monkeypatch,name,kind,field):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY","unrelated-offline-key")
    monkeypatch.setenv(name,FAKE_KEY)
    monkeypatch.setenv("DISCOVERY_BRAVE_STORAGE_ALLOWED","true")
    item={"title":"Company", "description":"Public business", "url":"https://company.example.com/"}
    value=encoded(FAKE_KEY,kind)
    if field == "url": item[field]+="?token="+value
    elif field == "nested": item["unused"]={"nested":[value]}
    elif field == "key": item[value]="unused"
    else: item[field]=value
    calls=[]
    def handle(request):
        calls.append(request)
        return httpx.Response(200,json={"web":{"results":[item]}})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider=PublicAPIProvider("brave",client=client)
        with pytest.raises(DiscoveryError) as caught:
            provider.search(SearchInput(product_id="00000000-0000-0000-0000-000000000001",source="brave",keywords="company"))
    assert caught.value.code=="source_invalid_output" and caught.value.request_count==1
    assert FAKE_KEY not in str(caught.value) and value not in str(caught.value)
    assert len(calls)==1


def test_wire_unicode_escape_is_decoded_and_rejected(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY",FAKE_KEY)
    monkeypatch.setenv("DISCOVERY_BRAVE_STORAGE_ALLOWED","true")
    body=json.dumps({"web":{"results":[{"title":FAKE_KEY,"url":"https://company.example.com/"}]}})
    body=body.replace(FAKE_KEY,encoded(FAKE_KEY,"unicode"))
    assert FAKE_KEY not in body
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=body))) as client:
        with pytest.raises(DiscoveryError,match="unsafe data"):
            PublicAPIProvider("brave",client=client).search(SearchInput(product_id="00000000-0000-0000-0000-000000000001",source="brave",keywords="company"))


def test_normalized_result_is_checked_independently(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY",FAKE_KEY)
    monkeypatch.setenv("DISCOVERY_BRAVE_STORAGE_ALLOWED","true")
    # Isolate the final boundary from the decoded-body guard.
    monkeypatch.setattr("app.discovery.providers.plain",lambda value,limit=800:FAKE_KEY)
    title="Public company"
    body={"web":{"results":[{"title":title,"url":"https://company.example.com/"}]}}
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=body))) as client:
        with pytest.raises(DiscoveryError,match="unsafe data"):
            PublicAPIProvider("brave",client=client).search(SearchInput(product_id="00000000-0000-0000-0000-000000000001",source="brave",keywords="company"))


def test_secret_response_never_persisted_or_returned(client,factory,monkeypatch,caplog):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY",FAKE_KEY)
    monkeypatch.setenv("DISCOVERY_BRAVE_STORAGE_ALLOWED","true")
    body={"web":{"results":[{"title":encoded(FAKE_KEY,"unicode"),"url":"https://company.example.com/"}]}}
    fake=httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=body)))
    monkeypatch.setattr(service,"get_discovery_provider",lambda source:PublicAPIProvider(source,client=fake))
    try: response=search(client,product(client))
    finally: fake.close()
    assert response.status_code==200 and response.json()["status"]=="failed"
    assert response.json()["error_code"]=="source_invalid_output" and response.json()["results"]==[]
    assert FAKE_KEY not in response.text and FAKE_KEY not in caplog.text
    with factory() as session:
        row=session.scalar(select(DiscoverySearch))
        assert row.results==[] and FAKE_KEY not in row.error


def test_service_rejects_credential_from_injected_adapter(client,factory,monkeypatch):
    from app.discovery.schemas import DiscoveryResult
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY",FAKE_KEY)
    monkeypatch.setenv("DISCOVERY_BRAVE_STORAGE_ALLOWED","true")
    class Adapter:
        def search(self,inputs):
            return [DiscoveryResult(source="brave",source_id="one",title=FAKE_KEY,url="https://company.example.com/",excerpt="Public")]
    monkeypatch.setattr(service,"get_discovery_provider",lambda source:Adapter())
    result=search(client,product(client)).json()
    assert result["status"]=="failed" and result["results"]==[] and FAKE_KEY not in str(result)
    with factory() as session:assert session.scalar(select(DiscoverySearch)).results==[]


def test_nonsecret_unicode_content_remains_supported(monkeypatch):
    from app.discovery.providers import validate_no_credentials
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY",FAKE_KEY)
    validate_no_credentials({"title":"\u0645\u0634\u0627\u0648\u0631\u0647", "url":"https://company.example.com/?q=public%20business"})
