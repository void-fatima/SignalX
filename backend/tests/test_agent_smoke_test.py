"""Exercise the manual smoke script through production code using fake HTTP only."""
import importlib
import json

import httpx
import pytest

from app.agents import orchestrator, smoke_test
from app.agents import acceptance
from app.agents.providers.mock import MockProvider


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(acceptance, "monotonic", lambda: clock[0])
    monkeypatch.setattr(acceptance, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL", "OPENAI_PRICE_VERSION",
                 "OPENAI_INPUT_USD_PER_MILLION", "OPENAI_OUTPUT_USD_PER_MILLION",
                 "OPENAI_TIMEOUT_SECONDS", "OPENAI_MAX_OUTPUT_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "aa-fake-smoke-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.avalai.ir/v1")


def qualification(**updates):
    result = dict(intent="asking_price", need="Seeks a beginner Python course and its price",
        purchase_intent=.85, product_fit=.9, need_strength=.8, urgency=0.,
        confidence=.9, response_opportunity=.9,
        evidence=[dict(message_id="smoke-target", quote=smoke_test.TARGET_TEXT,
                       reason="The author asks about a beginner course and pricing")],
        limitations=["Price is not supplied by the product owner"])
    result.update(updates)
    return result


def envelope(result=None, **changes):
    body = dict(status="completed", model="gpt-5.6-luna",
        output=[dict(type="message", content=[dict(type="output_text", text=json.dumps(
            qualification() if result is None else result))])],
        usage=dict(input_tokens=100, output_tokens=50, input_tokens_details=dict(cached_tokens=0)))
    body.update(changes)
    return body


@pytest.fixture
def fake_http(monkeypatch):
    clients = []

    def create(responses):
        requests, analyzed_inputs = [], []
        pending = iter(responses)

        def handler(request):
            requests.append(request)
            response = next(pending)
            if isinstance(response, Exception):
                raise response
            return response if isinstance(response, httpx.Response) else httpx.Response(200, json=response)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(client)
        def create_client(**kwargs):
            client.event_hooks = kwargs.get("event_hooks", {})
            return client
        monkeypatch.setattr("app.agents.providers.real.httpx.Client", create_client)

        def analyze(inputs):
            analyzed_inputs.append(inputs)
            return orchestrator.analyze_agent(inputs)

        monkeypatch.setattr(smoke_test, "analyze_agent", analyze)
        monkeypatch.setattr(MockProvider, "qualify_structured", lambda *args: pytest.fail("No Mock path allowed"))
        return requests, analyzed_inputs

    yield create
    for client in clients:
        client.close()


def test_exact_one_message_real_production_flow_and_complete_output(fake_http, capsys):
    requests, analyzed_inputs = fake_http([envelope()])
    assert smoke_test.main([]) == 0
    stdout, stderr = capsys.readouterr()
    report = json.loads(stdout)
    assert not stderr and "aa-fake-smoke-key" not in stdout
    assert len(requests) == len(analyzed_inputs) == 1
    inputs = analyzed_inputs[0]
    assert inputs.metadata.provider_mode == "real" and inputs.context_messages == []
    assert inputs.product.name == "Python Starter Course"
    assert inputs.product.description == "Beginner-friendly Python programming course."
    assert inputs.product.target_customer == "Beginners"
    assert inputs.message.content == "I'm looking for a Python course for beginners. How much does it cost?"
    request = requests[0]
    assert str(request.url) == "https://api.avalai.ir/v1/responses"
    assert request.headers["Authorization"] == "Bearer aa-fake-smoke-key"
    payload = json.loads(request.content)
    assert payload["model"] == "gpt-5.6-luna" and payload["text"]["format"]["strict"] is True
    assert "tools" not in payload and payload["store"] is False
    source = json.loads(payload["input"][-1]["content"])
    assert source["target"]["content"] == inputs.message.content and source["context"] == []
    assert report["status"] == "success" and report["screening"]["is_candidate"] is True
    assert report["intent"] == "asking_price"
    assert report["signals"] == {name: qualification()[name] for name in (
        "purchase_intent", "product_fit", "need_strength", "urgency", "confidence", "response_opportunity")}
    assert report["score"] == 78 and report["decision"] == "RESPOND"
    assert report["evidence"][0]["quote"] == inputs.message.content
    usage = report["usage"][0]
    assert usage["model"] == "gpt-5.6-luna" and usage["provider_mode"] == "real"
    assert usage["input_tokens"] == 100 and usage["output_tokens"] == 50
    assert usage["estimated_cost"] is None and usage["cost_status"] == "unknown"
    assert usage["stage"] == "qualification" and usage["outcome"] == "success"
    assert usage["latency_ms"] >= 0


def test_confidence_guard_is_applied_by_production_scorer(fake_http, capsys):
    fake_http([envelope(qualification(confidence=.4))])
    assert smoke_test.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["score"] == 73 and report["decision"] == "REVIEW"


def test_one_analysis_can_use_existing_single_repair(fake_http, capsys):
    requests, analyzed_inputs = fake_http([envelope({}), envelope()])
    assert smoke_test.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(analyzed_inputs) == 1 and len(requests) == 2
    assert [record["stage"] for record in report["usage"]] == ["qualification", "qualification_repair"]
    assert [record["outcome"] for record in report["usage"]] == ["invalid_output", "success"]


def test_invented_evidence_fails_without_fake_success_or_another_analysis(fake_http, capsys):
    invalid = qualification(evidence=[dict(message_id="unknown", quote="invented", reason="fake")])
    requests, analyzed_inputs = fake_http([envelope(invalid)]*2)
    assert smoke_test.main([]) == 1
    stdout, stderr = capsys.readouterr()
    assert not stdout
    report = json.loads(stderr)
    assert report["status"] == "provider_error" and "one repair" in report["error"]
    assert "score" not in report and "decision" not in report
    assert len(analyzed_inputs) == 1 and len(requests) == 2
    assert [record["outcome"] for record in report["usage"]] == ["invalid_output"]*2


@pytest.mark.parametrize("name,value", [
    ("OPENAI_API_KEY", None), ("OPENAI_MODEL", None), ("OPENAI_MODEL", "other-model"),
    ("OPENAI_BASE_URL", None), ("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    ("OPENAI_BASE_URL", "https://attacker.example/v1"),
])
def test_configuration_failure_prevents_http(name, value, monkeypatch, fake_http, capsys):
    requests, analyzed_inputs = fake_http([])
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)
    assert smoke_test.main([]) in (1, 2)
    stdout, stderr = capsys.readouterr()
    assert not stdout and "aa-fake-smoke-key" not in stderr
    assert requests == analyzed_inputs == []
    assert json.loads(stderr)["status"] in {"provider_error", "configuration_error"}


@pytest.mark.parametrize("status,code,diagnostic", [
    (404, "model_not_found", "selected model unavailable"),
    (400, "unsupported_model", "selected model unavailable"),
    (400, "invalid_json_schema", "incompatible"),
    (400, "unsupported_parameter", "incompatible"),
    (401, None, "authentication failed"), (403, None, "access denied"),
    (429, None, "quota"), (500, "aa-fake-smoke-key", "provider request rejected"),
])
def test_provider_error_has_status_and_fixed_diagnosis_without_raw_secrets(status, code, diagnostic, fake_http, capsys):
    requests, analyzed_inputs = fake_http([httpx.Response(status, json={
        "error": {"code": code, "message": "aa-fake-smoke-key RAW_UNTRUSTED_ERROR"}})])
    assert smoke_test.main([]) == 1
    stdout, stderr = capsys.readouterr()
    assert not stdout and "aa-fake-smoke-key" not in stderr and "RAW_UNTRUSTED_ERROR" not in stderr
    report = json.loads(stderr)
    assert f"HTTP {status}" in report["error"] and diagnostic in report["error"]
    assert report["requested_model"] == "gpt-5.6-luna"
    assert len(requests) == len(analyzed_inputs) == 1
    assert report["usage"][0]["outcome"] == "provider_error"
    assert report["usage"][0]["input_tokens"] is None


@pytest.mark.parametrize("error", [httpx.ReadTimeout("aa-fake-smoke-key"), httpx.ConnectError("aa-fake-smoke-key")])
def test_transport_failure_is_sanitized_and_not_retried(error, fake_http, capsys):
    requests, _ = fake_http([error])
    assert smoke_test.main([]) == 1
    stdout, stderr = capsys.readouterr()
    assert not stdout and "aa-fake-smoke-key" not in stderr
    report = json.loads(stderr)
    assert len(requests) == 1 and report["usage"][0]["estimated_cost"] is None
    assert report["usage"][0]["cost_status"] == "unknown"


def test_missing_measurements_stay_null(fake_http, capsys):
    fake_http([envelope(usage=None)])
    assert smoke_test.main([]) == 0
    record = json.loads(capsys.readouterr().out)["usage"][0]
    assert record["input_tokens"] is None and record["output_tokens"] is None
    assert record["estimated_cost"] is None and record["cost_status"] == "unknown"


def test_explicit_test_rates_use_real_usage_without_fake_prices(monkeypatch, fake_http, capsys):
    for name, value in dict(OPENAI_PRICE_VERSION="offline-test-rates", OPENAI_INPUT_USD_PER_MILLION="2",
                            OPENAI_OUTPUT_USD_PER_MILLION="8").items():
        monkeypatch.setenv(name, value)
    fake_http([envelope()])
    assert smoke_test.main([]) == 0
    record = json.loads(capsys.readouterr().out)["usage"][0]
    assert record["estimated_cost"] == "0.0006" and record["cost_status"] == "known"


def test_returned_secret_is_redacted_before_json_encoding(fake_http, capsys):
    fake_http([envelope(qualification(need="aa-fake-smoke-key"), model="aa-fake-smoke-key")])
    assert smoke_test.main([]) == 0
    stdout, _ = capsys.readouterr()
    assert "aa-fake-smoke-key" not in stdout
    report = json.loads(stdout)
    assert report["need"] == report["usage"][0]["model"] == "[REDACTED]"


def test_unexpected_local_failure_never_prints_traceback_or_exception_text(monkeypatch, capsys):
    def fail(inputs):
        raise RuntimeError("aa-fake-smoke-key RAW_LOCAL_ERROR")
    monkeypatch.setattr(smoke_test, "analyze_agent", fail)
    assert smoke_test.main([]) == 3
    stdout, stderr = capsys.readouterr()
    assert not stdout
    assert all(text not in stderr for text in ("aa-fake-smoke-key", "RAW_LOCAL_ERROR", "Traceback"))
    assert json.loads(stderr)["status"] == "local_error"


def test_help_never_calls_orchestrator(monkeypatch, capsys):
    monkeypatch.setattr(smoke_test, "analyze_agent", lambda inputs: pytest.fail("Help must not analyze"))
    with pytest.raises(SystemExit) as exc:
        smoke_test.main(["--help"])
    assert exc.value.code == 0 and "ONE paid" in capsys.readouterr().out


def test_import_never_calls_provider(monkeypatch):
    monkeypatch.setattr("app.agents.providers.real.httpx.Client", lambda **kwargs: pytest.fail("Import must not create HTTP clients"))
    importlib.reload(smoke_test)
