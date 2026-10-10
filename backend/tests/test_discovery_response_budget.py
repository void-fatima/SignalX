"""Offline bounded Greenhouse response regressions."""
import httpx
import pytest
from app.discovery.providers import PublicAPIProvider,DiscoveryError,MAX_BODY_BYTES
from app.discovery.schemas import SearchInput

def test_greenhouse_lightweight_listing_filters_entire_bounded_board():
    calls=[]
    jobs=[dict(id=i,title="Engineer",absolute_url=f"https://jobs.example.com/{i}") for i in range(501)]
    jobs += [dict(id=i,title="Accounting specialist",location={"name":"Berlin"},absolute_url=f"https://jobs.example.com/{i}") for i in range(501,508)]
    def handle(request):
        calls.append(request)
        assert request.url.params["content"]=="false"
        return httpx.Response(200,json={"jobs":jobs})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        results=PublicAPIProvider("greenhouse",client=client).search(SearchInput(product_id="00000000-0000-0000-0000-000000000001",source="greenhouse",board_slug="anthropic",keywords="accounting",limit=5))
    assert len(calls)==1 and len(results)==5
    assert [r.source_id for r in results]==[str(i) for i in range(501,506)]
    assert all(r.excerpt=="Accounting specialist" and r.source=="greenhouse" for r in results)
    assert results[0].url=="https://jobs.example.com/501"


def test_greenhouse_large_lightweight_board_fails_actionably_without_retry():
    calls=[]
    def handle(request):
        calls.append(request);return httpx.Response(200,content=b"x"*(MAX_BODY_BYTES+1))
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(DiscoveryError) as caught:
            PublicAPIProvider("greenhouse",client=client).search(SearchInput(product_id="00000000-0000-0000-0000-000000000001",source="greenhouse",board_slug="acme",keywords="accounting"))
    assert caught.value.code=="source_response_too_large" and caught.value.request_count==1
    assert "smaller job board" in str(caught.value) and len(calls)==1
