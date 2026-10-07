"""Only error propagation/diagnostic regressions; no live genericity claims."""
import json
import socket
import ssl
import traceback

import httpx
import pytest

from app.agents import acceptance, cross_business, orchestrator, reply, smoke_test
from app.agents.providers import factory, gemini
from app.agents.providers.base import ProviderError
from app.agents.providers.gemini_config import GEMINI_BASE_URL, GEMINI_SMOKE_MODEL
from app.agents.providers.mock import MockProvider
from app.agents.providers.real import RealProvider

KEY = "fake-gemini-diagnostics-key"
OTHER_KEY = "fake-other-provider-diagnostics-key"
PRIVATE = "private-user-project-and-message-data"


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    for name in ("GEMINI_TIMEOUT_SECONDS", "GEMINI_MAX_OUTPUT_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in dict(LLM_PROVIDER="gemini", GEMINI_MODEL=GEMINI_SMOKE_MODEL,
        GEMINI_BASE_URL=GEMINI_BASE_URL, GEMINI_API_KEY=KEY, OPENAI_API_KEY=OTHER_KEY).items():
        monkeypatch.setenv(name, value)
    clock = [0.]
    monkeypatch.setattr(acceptance, "monotonic", lambda: clock[0])
    monkeypatch.setattr(gemini, "perf_counter", lambda: clock[0])
    def sleep(seconds):
        clock[0] += seconds
    monkeypatch.setattr(acceptance, "sleep", sleep)
    monkeypatch.setattr(MockProvider, "qualify_structured", lambda *a: pytest.fail("Mock fallback"))
    monkeypatch.setattr(RealProvider, "qualify_structured", lambda *a: pytest.fail("AvalAI fallback"))
    return clock


@pytest.fixture
def transport(monkeypatch):
    client_class = httpx.Client
    clients = []
    def create(responses):
        requests, options, pending = [], [], iter(responses)
        def handle(request):
            requests.append(request)
            response = next(pending)
            if callable(response):
                response = response(request)
            if isinstance(response, Exception):
                raise response
            return response
        client = client_class(transport=httpx.MockTransport(handle))
        clients.append(client)
        def make_client(**kwargs):
            options.append(kwargs)
            client.event_hooks = kwargs.get("event_hooks", {})
            return client
        monkeypatch.setattr(httpx, "Client", make_client)
        return client, requests, options
    yield create
    for client in clients:
        client.close()


def run_analysis(client):
    with factory.real_provider_client(client):
        return orchestrator.analyze_agent(smoke_test.build_input("persian"))


def parse_error(capsys):
    output = capsys.readouterr()
    assert KEY not in output.out + output.err and OTHER_KEY not in output.out + output.err
    assert PRIVATE not in output.out + output.err and "Authorization" not in output.out + output.err
    return json.loads(output.err)


def google_error(status, message, *, code=None, name=None, **extra):
    return httpx.Response(status, json={"error": {"code": status if code is None else code,
        "status": name, "message": message + " " + KEY + " " + OTHER_KEY + " " + PRIVATE,
        **extra}})


@pytest.mark.parametrize("status,message,name,category", [
    (400, "Invalid JSON schema response_format", "INVALID_ARGUMENT", "schema_validation"),
    (400, "Invalid request argument", "INVALID_ARGUMENT", "request_validation"),
    (400, "API key not valid", "INVALID_ARGUMENT", "authentication"),
    (401, "Authentication failed", "UNAUTHENTICATED", "authentication"),
    (403, "Permission denied", "PERMISSION_DENIED", "permission"),
    (404, "Model unavailable", "NOT_FOUND", "model_or_endpoint"),
    (429, "Quota exceeded for free tier", "RESOURCE_EXHAUSTED", "quota_exceeded"),
    (429, "Requests per minute exceeded", "RESOURCE_EXHAUSTED", "rate_limit"),
    (429, "Resource exhausted", "RESOURCE_EXHAUSTED", "quota_or_rate_limit"),
    (500, "Internal provider failure", "INTERNAL", "server_error"),
])
def test_google_failure_categories_are_safe_and_propagate_without_retry(status, message, name, category, transport):
    client, requests, _ = transport([google_error(status, message, name=name)])
    with pytest.raises(ProviderError) as exc:
        run_analysis(client)
    diagnostic = exc.value.provider_diagnostics[0]
    assert len(requests) == len(exc.value.usage) == 1
    assert diagnostic["http_status"] == status and diagnostic["failure_kind"] == "http"
    assert diagnostic["provider_error_category"] == category and diagnostic["response_body_existed"] is True
    assert diagnostic["google_error_code"] == status and diagnostic["google_error_status"] == name
    assert diagnostic["stage"] == "qualification" and diagnostic["attempt_no"] == 1
    assert diagnostic["google_error_message"] and diagnostic["google_error_message_is_category_summary"]
    text = json.dumps(diagnostic) + "".join(traceback.format_exception(exc.value))
    assert all(secret not in text for secret in (KEY, OTHER_KEY, PRIVATE, "Authorization"))
    assert exc.value.usage[0].outcome == "provider_error" and exc.value.usage[0].input_tokens is None


@pytest.mark.parametrize("cls,kind,category", [
    (httpx.ConnectTimeout, "timeout", "connect_timeout"),
    (httpx.ReadTimeout, "timeout", "read_timeout"),
    (httpx.WriteTimeout, "timeout", "write_timeout"),
    (httpx.PoolTimeout, "timeout", "pool_timeout"),
    (httpx.ProxyError, "transport", "proxy_error"),
    (httpx.ConnectError, "transport", "connection_error"),
    (httpx.ReadError, "transport", "read_error"),
    (httpx.WriteError, "transport", "write_error"),
    (httpx.CloseError, "transport", "close_error"),
    (httpx.RemoteProtocolError, "transport", "remote_protocol_error"),
    (httpx.LocalProtocolError, "transport", "local_protocol_error"),
    (httpx.DecodingError, "transport", "decoding_error"),
    (RuntimeError, "client", "client_runtime_error"),
])
def test_exception_types_and_timeout_categories_survive_sanitization(cls, kind, category, transport):
    client, requests, _ = transport([cls("Authorization: Bearer " + KEY + " " + PRIVATE)])
    with pytest.raises(ProviderError) as exc:
        run_analysis(client)
    diagnostic = exc.value.provider_diagnostics[0]
    assert len(requests) == 1 and diagnostic["failure_kind"] == kind
    assert diagnostic["provider_error_category"] == category and diagnostic["exception_type"] == cls.__name__
    assert category in str(exc.value)
    assert diagnostic["http_status"] is None and diagnostic["response_body_existed"] is False
    assert diagnostic["google_error_code"] is None and diagnostic["google_error_message"] is None
    assert diagnostic["timeout_seconds"] == 30
    assert exc.value.usage[0].outcome == ("timeout" if kind == "timeout" else "provider_error")
    assert KEY not in json.dumps(diagnostic) + "".join(traceback.format_exception(exc.value))


@pytest.mark.parametrize("cause,category", [
    (ssl.SSLCertVerificationError(KEY), "tls_certificate_error"),
    (ssl.SSLError(KEY), "tls_error"), (socket.gaierror(KEY), "dns_resolution_error"),
    (ConnectionRefusedError(KEY), "connection_refused"), (ConnectionResetError(KEY), "connection_reset"),
])
def test_known_network_causes_are_reported_without_causal_messages(cause, category, transport):
    error = httpx.ConnectError(PRIVATE)
    error.__cause__ = cause
    client, _, _ = transport([error])
    with pytest.raises(ProviderError) as exc:
        run_analysis(client)
    assert exc.value.provider_diagnostics[0]["cause_category"] == category
    assert KEY not in json.dumps(exc.value.provider_diagnostics) + "".join(traceback.format_exception(exc.value))


def test_historical_latency_shape_reproduced_offline_does_not_imply_timeout(environment, transport, capsys):
    def failure(request):
        # Synthetic connection failure, not the retained historical exception.
        environment[0] += .595
        return httpx.ConnectError(PRIVATE)
    _, requests, _ = transport([failure])
    assert cross_business.main(["--provider", "gemini", "--json-only"]) == 1
    report = parse_error(capsys)
    assert report["paid_api_request_attempts"] == len(requests) == 1 and report["results"] == []
    assert report["failed_run"] == dict(message="message_1", business_id="python_course")
    assert report["failed_usage"][0]["input_tokens"] is None and report["failed_usage"][0]["output_tokens"] is None
    assert report["failed_usage"][0]["latency_ms"] == 65595
    assert report["failed_usage"][0]["outcome"] == "provider_error" and report["latency_includes_pacing"]
    assert report["provider_diagnostics"][0]["failure_kind"] == "transport"


def test_cross_business_and_smoke_share_request_path_and_transport_settings(transport, capsys):
    captured = []
    for runner, args in ((cross_business.main, ["--provider", "gemini", "--json-only"]),
                         (smoke_test.main, ["--provider", "gemini", "--scenario", "persian"])):
        _, requests, options = transport([httpx.ConnectError(PRIVATE)])
        assert runner(args) == 1
        report = parse_error(capsys)
        assert report["provider_diagnostics"][0]["provider_error_category"] == "connection_error"
        assert len(requests) == 1 and options[0]["timeout"] == 30 and not options[0]["follow_redirects"]
        assert factory._real_client.get() is None
        request = requests[0]
        captured.append((request, json.loads(request.content)))
    (first, one), (second, two) = captured
    assert first.url == second.url == GEMINI_BASE_URL + "chat/completions"
    assert first.method == second.method == "POST"
    assert first.headers["Authorization"] == second.headers["Authorization"] == "Bearer " + KEY
    assert first.extensions["timeout"] == second.extensions["timeout"]
    assert one["model"] == two["model"] == GEMINI_SMOKE_MODEL and one["max_tokens"] == two["max_tokens"]
    assert one["response_format"] == two["response_format"]
    assert one["messages"][0] == two["messages"][0]
    assert set(json.loads(one["messages"][-1]["content"])) == set(json.loads(two["messages"][-1]["content"]))


@pytest.mark.parametrize("failure", [httpx.ConnectError(PRIVATE), httpx.ReadTimeout(PRIVATE),
    google_error(429, "Quota exceeded", name="RESOURCE_EXHAUSTED"), google_error(403, "Permission denied", name="PERMISSION_DENIED")])
def test_first_failure_stops_every_remaining_case(failure, transport, capsys):
    _, requests, _ = transport([failure])
    assert cross_business.main(["--json-only"]) == 1
    report = parse_error(capsys)
    assert report["status"] == "provider_error" and report["results"] == []
    assert report["paid_api_request_attempts"] == len(requests) == 1
    assert len(report["provider_diagnostics"]) == len(report["failed_usage"]) == 1
    assert "genericity_checks" not in report
    assert report["failed_usage"][0]["estimated_cost"] is None


@pytest.mark.parametrize("name", [KEY, ["private-status"], {"status": PRIVATE}, None])
def test_unknown_or_malformed_google_status_and_code_cannot_leak_or_crash(name, transport):
    client, _, _ = transport([google_error(400, PRIVATE, name=name, code=KEY)])
    with pytest.raises(ProviderError) as exc:
        run_analysis(client)
    diagnostic = exc.value.provider_diagnostics[0]
    assert diagnostic["google_error_status"] is None and diagnostic["google_error_code"] is None
    assert KEY not in json.dumps(diagnostic) and PRIVATE not in json.dumps(diagnostic)


@pytest.mark.parametrize("response,present", [(httpx.Response(502, content=b""), False),
    (httpx.Response(502, text="private HTML proxy error " + KEY), True)])
def test_empty_and_non_json_error_bodies_have_safe_presence_metadata(response, present, transport):
    client, _, _ = transport([response])
    with pytest.raises(ProviderError) as exc:
        run_analysis(client)
    diagnostic = exc.value.provider_diagnostics[0]
    assert diagnostic["http_status"] == 502 and diagnostic["response_body_existed"] is present
    assert diagnostic["google_error_message"] is None and KEY not in json.dumps(diagnostic)


def test_http_status_exception_preserves_available_status_and_body(transport):
    response = google_error(429, "Rate limit exceeded", name="RESOURCE_EXHAUSTED")
    failure = httpx.HTTPStatusError(KEY, request=httpx.Request("POST", GEMINI_BASE_URL), response=response)
    client, _, _ = transport([failure])
    with pytest.raises(ProviderError) as exc:
        run_analysis(client)
    diagnostic = exc.value.provider_diagnostics[0]
    assert diagnostic["http_status"] == 429 and diagnostic["response_body_existed"] is True
    assert diagnostic["failure_kind"] == "http" and diagnostic["provider_error_category"] == "rate_limit"


def test_provider_error_in_http_success_body_remains_failure(transport):
    client, requests, _ = transport([google_error(200, "Invalid schema", code=400, name="INVALID_ARGUMENT")])
    with pytest.raises(ProviderError) as exc:
        run_analysis(client)
    diagnostic = exc.value.provider_diagnostics[0]
    assert len(requests) == 1 and diagnostic["http_status"] == 200
    assert diagnostic["failure_kind"] == "provider" and diagnostic["provider_error_category"] == "schema_validation"


def valid_qualification(request):
    # Synthetic success only to reach the second operation/repair/reply failure.
    target = json.loads(json.loads(request.content)["messages"][-1]["content"])["target"]
    q = dict(intent="asking_price", need=target["content"], purchase_intent=.8, product_fit=.9,
        need_strength=.8, urgency=0., confidence=.9, response_opportunity=.8,
        evidence=[dict(message_id=target["id"], quote=target["content"], reason="Supplied target")], limitations=[])
    return httpx.Response(200, json=dict(model=GEMINI_SMOKE_MODEL,
        choices=[dict(finish_reason="stop", message=dict(role="assistant", content=json.dumps(q)))],
        usage=dict(prompt_tokens=10, completion_tokens=20)))


def test_failure_after_completed_operation_retains_results_and_stops_rest(transport, capsys):
    _, requests, _ = transport([valid_qualification, httpx.ProxyError(PRIVATE)])
    assert cross_business.main(["--json-only"]) == 1
    report = parse_error(capsys)
    assert report["paid_api_request_attempts"] == len(requests) == 2 and len(report["results"]) == 1
    assert report["failed_run"] == dict(message="message_2", business_id="python_course")
    assert report["provider_diagnostics"][0]["provider_error_category"] == "proxy_error"


def test_repair_transport_failure_retains_both_attempts_and_reports_attempt_two(transport, capsys):
    invalid = httpx.Response(200, json=dict(choices=[dict(finish_reason="stop", message=dict(role="assistant", content="{}"))]))
    _, requests, _ = transport([invalid, httpx.ConnectError(PRIVATE)])
    assert cross_business.main(["--json-only"]) == 1
    report = parse_error(capsys)
    assert report["paid_api_request_attempts"] == len(requests) == 2 and report["results"] == []
    assert [u["outcome"] for u in report["failed_usage"]] == ["invalid_output", "provider_error"]
    assert report["provider_diagnostics"][0]["attempt_no"] == 2
    assert report["provider_diagnostics"][0]["stage"] == "qualification_repair"


def test_reply_and_legacy_wrappers_preserve_provider_diagnostics(transport):
    client, requests, _ = transport([valid_qualification, httpx.ReadTimeout(PRIVATE)])
    inputs = smoke_test.build_input("persian")
    with factory.real_provider_client(client):
        analysis = orchestrator.analyze_agent(inputs)
        original = analysis.model_dump()
        with pytest.raises(ProviderError) as exc:
            reply.generate_suggested_reply(inputs, analysis)
    assert len(requests) == 2 and analysis.model_dump() == original
    assert exc.value.usage[:1] == analysis.usage
    assert exc.value.provider_diagnostics[0]["stage"] == "suggested_reply"
    assert exc.value.provider_diagnostics[0]["provider_error_category"] == "read_timeout"
    client, _, _ = transport([httpx.ConnectError(PRIVATE)])
    provider = gemini.GeminiProvider(client=client)
    with pytest.raises(ProviderError) as exc:
        provider.qualify(*orchestrator._prepare_input(inputs)[1:])
    assert exc.value.provider_diagnostics[0]["stage"] == "qualification"
