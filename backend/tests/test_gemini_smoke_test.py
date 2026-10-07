"""Manual Gemini tooling tested entirely offline through real Agent entry points."""
import json

import httpx
import pytest

from app.agents import acceptance, smoke_test
from app.agents.providers import factory
from app.agents.providers.gemini_config import GEMINI_BASE_URL, GEMINI_SMOKE_MODEL
from app.agents.providers.mock import MockProvider
from app.agents.providers.real import RealProvider

KEY = "fake-gemini-smoke-key"
ENDPOINT = GEMINI_BASE_URL + "chat/completions"


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    for name in ("GEMINI_TIMEOUT_SECONDS", "GEMINI_MAX_OUTPUT_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in dict(LLM_PROVIDER="gemini", GEMINI_API_KEY=KEY,
        GEMINI_BASE_URL=GEMINI_BASE_URL, GEMINI_MODEL=GEMINI_SMOKE_MODEL,
        OPENAI_API_KEY="fake-avalai-smoke-key").items():
        monkeypatch.setenv(name, value)
    clock, sleeps = [0.], []
    def pause(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
    monkeypatch.setattr(acceptance, "monotonic", lambda: clock[0])
    monkeypatch.setattr(acceptance, "sleep", pause)
    monkeypatch.setattr(MockProvider, "qualify_structured", lambda *args: pytest.fail("Mock fallback"))
    monkeypatch.setattr(RealProvider, "qualify_structured", lambda *args: pytest.fail("AvalAI fallback"))
    return clock, sleeps


def qualification(scenario):
    inputs = smoke_test.build_input(scenario)
    result = dict(intent="objection" if scenario == "context" else "asking_price",
        need="اعتراض احتمالی به هزینه دوره" if scenario == "context" else
             "دوره مناسب مبتدی پایتون" if scenario == "persian" else "Beginner Python course and price information",
        purchase_intent=.85, product_fit=.9, need_strength=.8, urgency=0., confidence=.9,
        response_opportunity=.9, evidence=[dict(message_id=inputs.message.id, quote=inputs.message.content,
                                               reason="Supplied target")], limitations=["Price unavailable"])
    if scenario == "context":
        result["evidence"].append(dict(message_id=inputs.context_messages[0].id,
            quote=inputs.context_messages[0].content, reason="Supplied context"))
    return result


def envelope(payload):
    return dict(model=GEMINI_SMOKE_MODEL,
        choices=[dict(finish_reason="stop", message=dict(role="assistant", content=json.dumps(payload, ensure_ascii=False)))],
        usage=dict(prompt_tokens=100, completion_tokens=50))


def draft():
    return dict(parts=[dict(kind="question", text="دوست دارید با پایتون چه کاری انجام بدهید؟", product_field=None)])


@pytest.fixture
def transport(monkeypatch, environment):
    clock, _ = environment
    clients = []
    client_type = httpx.Client
    def create(responses):
        requests, times = [], []
        pending = iter(responses)
        def handle(request):
            requests.append(request)
            times.append(clock[0])
            value = next(pending)
            if isinstance(value, Exception):
                raise value
            return value if isinstance(value, httpx.Response) else httpx.Response(200, json=value)
        client = client_type(transport=httpx.MockTransport(handle))
        clients.append(client)
        def create_client(**kwargs):
            assert kwargs["follow_redirects"] is False
            client.event_hooks = kwargs["event_hooks"]
            return client
        monkeypatch.setattr(smoke_test.httpx, "Client", create_client)
        return requests, times
    yield create
    for client in clients:
        client.close()


def report(capsys, failed=False):
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err and "fake-avalai-smoke-key" not in captured.out + captured.err
    return json.loads(captured.err if failed else captured.out)


@pytest.mark.parametrize("scenario", ["english", "persian", "context"])
def test_each_scenario_uses_actual_production_flow(scenario, transport, capsys):
    requests, times = transport([envelope(qualification(scenario))])
    assert smoke_test.main(["--provider", "gemini", "--scenario", scenario]) == 0
    output = report(capsys)
    assert output["status"] == "success" and output["provider"] == "gemini"
    assert output["requested_model"] == GEMINI_SMOKE_MODEL and output["endpoint"] == ENDPOINT
    assert output["paid_api_request_attempts"] == 1 and times == [65]
    assert output["prompt_version"] == "qualify_gemini_v1" and output["scoring_version"] == "score_v1"
    assert output["checks"]["evidence_grounded"] and output["checks"]["deterministic_score_and_guards"]
    assert output["usage"][0]["model"] == GEMINI_SMOKE_MODEL
    assert (output["usage"][0]["input_tokens"], output["usage"][0]["output_tokens"]) == (100, 50)
    assert output["usage"][0]["cost_status"] == "unknown" and output["usage"][0]["estimated_cost"] is None
    assert output["usage"][0]["estimated_toman"] is None and output["exact_account_charge"] is False
    assert requests[0].headers["Authorization"] == "Bearer " + KEY
    if scenario == "context":
        sources = json.loads(json.loads(requests[0].content)["messages"][-1]["content"])
        assert sources["target"]["conversation_id"] == sources["context"][0]["conversation_id"]
        assert output["checks"]["context_evidence_present"]


def test_default_scenario_is_one_english_analysis(transport, capsys):
    requests, _ = transport([envelope(qualification("english"))])
    assert smoke_test.main(["--provider", "gemini"]) == 0
    assert report(capsys)["scenario"] == "english" and len(requests) == 1


def test_bounded_repair_is_paced(transport, capsys):
    requests, times = transport([envelope({}), envelope(qualification("english"))])
    assert smoke_test.main(["--provider", "gemini"]) == 0
    output = report(capsys)
    assert len(requests) == output["paid_api_request_attempts"] == 2 and times == [65, 130]
    assert [r["outcome"] for r in output["usage"]] == ["invalid_output", "success"]
    assert [r["stage"] for r in output["usage"]] == ["qualification", "qualification_repair"]
    assert factory._real_client.get() is None


def test_saved_analysis_reply_only_no_duplicate_qualification(transport, tmp_path, capsys):
    snapshot = tmp_path / "gemini.json"
    requests, _ = transport([envelope(qualification("persian"))])
    assert smoke_test.main(["--provider", "gemini", "--scenario", "persian", "--save-analysis", str(snapshot)]) == 0
    previous = report(capsys)
    assert len(requests) == 1
    requests, times = transport([envelope(draft())])
    assert smoke_test.main(["--provider", "gemini", "--scenario", "reply", "--analysis-file", str(snapshot)]) == 0
    output = report(capsys)
    assert output["paid_api_request_attempts"] == len(requests) == 1
    assert times == [130] and output["automatic_sending"] is False
    assert output["prior_usage"] == previous["usage"]
    assert (output["score"], output["decision"]) == (previous["score"], previous["decision"])
    assert output["usage"][0]["stage"] == "suggested_reply" and output["checks"]["no_duplicate_qualification"]
    assert KEY not in snapshot.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["LLM_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_BASE_URL"])
def test_live_gemini_requires_explicit_config(name, monkeypatch, transport, capsys):
    monkeypatch.delenv(name)
    requests, _ = transport([])
    assert smoke_test.main(["--provider", "gemini"]) == 1
    output = report(capsys, failed=True)
    assert output["status"] == "provider_error" and output["paid_api_request_attempts"] == 0
    assert not requests


@pytest.mark.parametrize("name,value", [("GEMINI_MODEL", "unverified-model"),
    ("GEMINI_BASE_URL", "https://evil.example"), ("LLM_PROVIDER", "avalai")])
def test_live_provider_or_config_mismatch_fails_closed(name, value, monkeypatch, transport, capsys):
    monkeypatch.setenv(name, value)
    requests, _ = transport([])
    assert smoke_test.main(["--provider", "gemini"]) == 1
    assert report(capsys, failed=True)["paid_api_request_attempts"] == 0 and not requests


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500])
def test_live_errors_report_actual_attempt_and_stop(status, transport, capsys):
    requests, _ = transport([httpx.Response(status, json={"error": {"message": KEY}})])
    assert smoke_test.main(["--provider", "gemini"]) == 1
    output = report(capsys, failed=True)
    assert output["status"] == "provider_error" and output["paid_api_request_attempts"] == len(requests) == 1
    assert f"HTTP {status}" in output["error"]


def test_unknown_usage_not_fabricated(transport, capsys):
    body = envelope(qualification("english"))
    del body["usage"]
    transport([body])
    assert smoke_test.main(["--provider", "gemini"]) == 0
    usage = report(capsys)["usage"][0]
    assert usage["input_tokens"] is None and usage["output_tokens"] is None
    assert usage["estimated_cost"] is None and usage["cost_status"] == "unknown"


def test_help_makes_no_requests(transport, capsys):
    requests, _ = transport([])
    with pytest.raises(SystemExit) as exc:
        smoke_test.main(["--help"])
    assert exc.value.code == 0 and not requests
    assert "--provider" in capsys.readouterr().out


def test_offline_replay_needs_no_credentials(transport, tmp_path, monkeypatch, capsys):
    snapshot = tmp_path / "gemini.json"
    requests, _ = transport([envelope(qualification("context"))])
    assert smoke_test.main(["--provider", "gemini", "--scenario", "context", "--save-analysis", str(snapshot)]) == 0
    report(capsys)
    for name in ("LLM_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_BASE_URL"):
        monkeypatch.delenv(name)
    # Current selector defaults to AvalAI; historical Gemini provenance must
    # come from the recording, never from today's environment or CLI.
    assert smoke_test.main(["--scenario", "context", "--replay-analysis", str(snapshot)]) == 0
    output = report(capsys)
    assert output["execution_mode"] == "offline_replay" and output["paid_api_request_attempts"] == 0
    assert len(requests) == 1 and output["usage_from_recording"] is True
    assert output["provider"] == "gemini" and output["requested_model"] is None and output["endpoint"] is None


def test_report_and_snapshot_reject_gemini_secret_echo(capsys, tmp_path):
    smoke_test._print_report({"text": KEY, "other": "fake-avalai-smoke-key"})
    output = report(capsys)
    assert output == dict(text="[REDACTED]", other="[REDACTED]")
    # Save the real typed analysis but reject a secret introduced into a field.
    from app.agents.contracts import AgentOutput, ScreeningResult
    analysis = AgentOutput(screening=ScreeningResult(is_candidate=False, reason=KEY))
    with pytest.raises(acceptance.AcceptanceValidationError) as exc:
        acceptance.save_snapshot(tmp_path / "secret.json", smoke_test.build_input(), analysis)
    assert exc.value.diagnostic["failed_check"] == "snapshot_secret"
    assert not (tmp_path / "secret.json").exists()


def test_pacer_rejects_other_provider_endpoint_without_dispatch():
    pacer = acceptance.RequestPacer(2, endpoint=ENDPOINT)
    with pytest.raises(RuntimeError):
        pacer.before_request(httpx.Request("POST", "https://api.avalai.ir/v1/responses"))
    assert pacer.request_count == 0


@pytest.mark.parametrize("value,check", [
    ("not JSON", "reply_json"),
    ({"suggested_reply": "private-rejected-reply"}, "reply_pydantic_schema"),
    (dict(parts=[dict(kind="question", text="What would you like to learn?", product_field=None)]), "reply_question_language"),
])
def test_reply_runner_reports_safe_checks_without_rerunning_qualification(value, check, transport, tmp_path, capsys):
    path = tmp_path / "gemini-persian.json"
    requests, _ = transport([envelope(qualification("persian"))])
    assert smoke_test.main(["--provider", "gemini", "--scenario", "persian", "--save-analysis", str(path)]) == 0
    previous = report(capsys)
    original_bytes = path.read_bytes()
    response = envelope(value)
    if isinstance(value, str):
        response["choices"][0]["message"]["content"] = value
    requests, times = transport([response] * 2)
    assert smoke_test.main(["--provider", "gemini", "--scenario", "reply", "--analysis-file", str(path)]) == 1
    output = report(capsys, failed=True)
    assert len(requests) == output["paid_api_request_attempts"] == 2 and times == [130, 195]
    assert output["failed_check"] == check and len(output["validation_diagnostics"]) == 2
    assert [d["attempt_no"] for d in output["validation_diagnostics"]] == [1, 2]
    assert [r["stage"] for r in output["usage"]] == ["suggested_reply", "suggested_reply_repair"]
    assert all(d["failed_check"] == check for d in output["validation_diagnostics"])
    assert "private-rejected-reply" not in json.dumps(output)
    assert path.read_bytes() == original_bytes and previous["status"] == "success"
    assert all(json.loads(r.content)["response_format"]["json_schema"]["name"] == "suggested_reply" for r in requests)
