"""Acceptance scenarios through production Agent entry points, fake HTTP only."""
import json
from decimal import Decimal

import httpx
import pytest

from app.agents import acceptance, smoke_test
from app.agents.contracts import UsageInfo
from app.agents.providers import factory
from app.agents.providers.mock import MockProvider
from app.agents.contracts import AgentOutput, QualificationResult, ScreeningResult
from app.agents.scoring import calculate_score


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    for name in ("OPENAI_TIMEOUT_SECONDS", "OPENAI_MAX_OUTPUT_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in dict(OPENAI_API_KEY="fake-acceptance-key", OPENAI_MODEL="gpt-5.6-luna",
        OPENAI_BASE_URL="https://api.avalai.ir/v1", OPENAI_PRICE_VERSION="verified-offline-test",
        OPENAI_INPUT_USD_PER_MILLION="0.20", OPENAI_OUTPUT_USD_PER_MILLION="1.20").items():
        monkeypatch.setenv(name, value)
    clock, sleeps = [0.0], []
    def pause(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
    monkeypatch.setattr(acceptance, "monotonic", lambda: clock[0])
    monkeypatch.setattr(acceptance, "sleep", pause)
    monkeypatch.setattr(MockProvider, "qualify_structured", lambda *args: pytest.fail("No Mock fallback"))
    return clock, sleeps


def qualification(scenario="persian", **updates):
    inputs = smoke_test.build_input(scenario)
    evidence = [dict(message_id=inputs.message.id, quote=inputs.message.content,
                     reason="The supplied target expresses a course need or objection")]
    if scenario == "context":
        evidence.append(dict(message_id=inputs.context_messages[0].id,
            quote=inputs.context_messages[0].content, reason="Context supplies the beginner course topic"))
    result = dict(intent="objection" if scenario == "context" else "asking_price",
        need="اعتراض به هزینه دوره مناسب مبتدی‌ها" if scenario == "context" else "یادگیری پایتون با دوره مبتدی و اطلاع از هزینه",
        purchase_intent=.65 if scenario == "context" else .85, product_fit=.9,
        need_strength=.8, urgency=0., confidence=.7 if scenario == "context" else .9,
        response_opportunity=.9, evidence=evidence, limitations=["Actual product price is unavailable"])
    result.update(updates)
    return result


def draft(text="دوست دارید با پایتون چه کاری انجام بدهید؟"):
    return dict(parts=[dict(kind="question", text=text, product_field=None)])


def envelope(result, **updates):
    body = dict(status="completed", model="gpt-5.6-luna",
        output=[dict(type="message", content=[dict(type="output_text", text=json.dumps(result, ensure_ascii=False))])],
        usage=dict(input_tokens=100, output_tokens=50, input_tokens_details=dict(cached_tokens=0)))
    body.update(updates)
    return body


@pytest.fixture
def transport(monkeypatch, environment):
    clock, _ = environment
    clients = []
    client_class = httpx.Client
    def create(responses):
        requests, times = [], []
        pending = iter(responses)
        def handler(request):
            requests.append(request)
            times.append(clock[0])
            response = next(pending)
            if isinstance(response, Exception):
                raise response
            return response if isinstance(response, httpx.Response) else httpx.Response(200, json=response)
        client = client_class(transport=httpx.MockTransport(handler))
        clients.append(client)
        def make_client(**kwargs):
            assert kwargs["follow_redirects"] is False
            client.event_hooks = kwargs["event_hooks"]
            return client
        monkeypatch.setattr(smoke_test.httpx, "Client", make_client)
        return requests, times
    yield create
    for client in clients:
        client.close()


def read_report(capsys, failed=False):
    out, err = capsys.readouterr()
    assert "fake-acceptance-key" not in out + err
    return json.loads(err if failed else out)


def test_persian_real_flow_rates_signals_evidence(transport, capsys):
    requests, times = transport([envelope(qualification())])
    assert smoke_test.main(["--scenario", "persian"]) == 0
    report = read_report(capsys)
    assert report["screening"]["is_candidate"]
    assert all(report["checks"][name] for name in (
        "screening_retained", "signals_bounded", "evidence_grounded", "deterministic_score_and_guards", "real_usage"))
    assert report["need"] == qualification()["need"]
    assert all(0 <= value <= 1 for value in report["signals"].values())
    assert len(report["signals"]) == 6 and report["evidence"][0]["quote"] == smoke_test.PERSIAN_TEXT
    assert report["paid_api_request_attempts"] == 1 and times == [65]
    assert requests[0].headers["Authorization"] == "Bearer fake-acceptance-key"
    usage = report["usage"][0]
    assert (usage["input_tokens"], usage["output_tokens"]) == (100, 50)
    assert Decimal(usage["estimated_cost"]) == Decimal("0.00008")
    assert Decimal(usage["estimated_toman"]) == Decimal("21.6")
    assert usage["price_version"] == "verified-offline-test" and usage["cost_status"] == "known"
    assert usage["exact_account_charge"] is False and report["human_review_required"] is True


def test_context_supplied_correctly_and_changes_interpretation(transport, capsys):
    requests, _ = transport([envelope(qualification("context"))])
    assert smoke_test.main(["--scenario", "context"]) == 0
    report = read_report(capsys)
    payload = json.loads(requests[0].content)
    sources = json.loads(payload["input"][-1]["content"])
    assert sources["target"]["content"] == smoke_test.CONTEXT_TARGET
    assert sources["context"][0]["content"] == smoke_test.CONTEXT_TEXT
    assert sources["context"][0]["conversation_id"] == sources["target"]["conversation_id"]
    assert sources["context"][0]["id"] != sources["target"]["id"]
    assert sources["target"]["timestamp"].endswith("Z") or "+00:00" in sources["target"]["timestamp"]
    assert report["intent"] == "objection" and report["checks"]["context_evidence_present"]
    assert {e["message_id"] for e in report["evidence"]} == {"smoke-context", "smoke-context-target"}
    assert report["human_review_required"] is True


def test_acceptance_three_requests_no_duplicate_qualification(transport, environment, capsys):
    requests, times = transport([envelope(qualification()), envelope(qualification("context")), envelope(draft())])
    assert smoke_test.main(["--scenario", "acceptance"]) == 0
    report = read_report(capsys)
    assert report["paid_api_request_attempts"] == 3 and times == [65, 130, 195]
    assert [json.loads(r.content)["text"]["format"]["name"] for r in requests] == ["qualification", "qualification", "suggested_reply"]
    persian, contextual, reply = report["results"]
    assert [r["scenario"] for r in report["results"]] == ["persian", "context", "reply"]
    assert reply["score"] == persian["score"] and reply["decision"] == persian["decision"]
    assert reply["prior_usage"] == persian["usage"]
    assert reply["usage"][0]["stage"] == "suggested_reply" and reply["automatic_sending"] is False
    assert reply["suggested_reply"] == draft()["parts"][0]["text"]
    assert all(0 < pause <= 30 for pause in environment[1])
    assert factory._real_client.get() is None


def test_repairs_paced_and_budget_bounded_at_six(transport, capsys):
    requests, times = transport([envelope({}), envelope(qualification()), envelope({}),
        envelope(qualification("context")), envelope({}), envelope(draft())])
    assert smoke_test.main(["--scenario", "acceptance"]) == 0
    report = read_report(capsys)
    assert report["paid_api_request_attempts"] == 6 and times == [65, 130, 195, 260, 325, 390]
    assert len(requests) == 6
    for scenario in report["results"]:
        assert [r["attempt_no"] for r in scenario["usage"]] == [1, 2]
        assert [r["outcome"] for r in scenario["usage"]] == ["invalid_output", "success"]


@pytest.mark.parametrize("status", [401, 402, 403, 429])
def test_account_failure_stops_without_http_retry(status, transport, capsys):
    requests, _ = transport([httpx.Response(status, json={"error": {"message": "fake-acceptance-key RAW_ERROR"}})])
    assert smoke_test.main(["--scenario", "acceptance"]) == 1
    report = read_report(capsys, failed=True)
    assert len(requests) == report["paid_api_request_attempts"] == 1
    assert f"HTTP {status}" in report["error"] and "RAW_ERROR" not in report["error"]
    assert report["usage"][0]["cost_status"] == "unknown" and report["completed_scenarios"] == []


@pytest.mark.parametrize("failure_stage", ["context", "reply"])
def test_partial_success_and_failed_usage_preserved(failure_stage, transport, capsys):
    responses = [envelope(qualification())]
    if failure_stage == "reply":
        responses.append(envelope(qualification("context")))
    responses.append(httpx.Response(429, json={}))
    requests, _ = transport(responses)
    assert smoke_test.main(["--scenario", "acceptance"]) == 1
    report = read_report(capsys, failed=True)
    assert len(report["completed_scenarios"]) == len(requests) - 1
    assert len(report["usage"]) == 1
    assert report["usage"][0]["stage"] == ("suggested_reply" if failure_stage == "reply" else "qualification")
    assert report["usage"][0]["outcome"] == "provider_error"


@pytest.mark.parametrize("usage,model", [
    (None, "gpt-5.6-luna"),
    (dict(input_tokens=100, output_tokens=50), "gpt-5.6-luna"),
    (dict(input_tokens=100, output_tokens=50, input_tokens_details=dict(cached_tokens=10)), "gpt-5.6-luna"),
    (dict(input_tokens=100, output_tokens=50, input_tokens_details=dict(cached_tokens=0)), "model-alias"),
])
def test_unknown_usage_cache_or_model_never_false_cost(usage, model, transport, capsys):
    transport([envelope(qualification(), usage=usage, model=model)])
    assert smoke_test.main(["--scenario", "persian"]) == 0
    record = read_report(capsys)["usage"][0]
    assert record["estimated_cost"] is record["estimated_toman"] is None
    assert record["cost_status"] == "unknown"


@pytest.mark.parametrize("name,value", [
    ("OPENAI_INPUT_USD_PER_MILLION", "0.40"), ("OPENAI_OUTPUT_USD_PER_MILLION", "1.80"),
    ("OPENAI_PRICE_VERSION", ""), ("OPENAI_API_KEY", ""),
])
def test_unverified_configuration_prevents_paid_attempts(name, value, monkeypatch, transport, capsys):
    requests, _ = transport([])
    monkeypatch.setenv(name, value)
    assert smoke_test.main(["--scenario", "persian"]) in (1, 2)
    assert read_report(capsys, failed=True)["paid_api_request_attempts"] == 0 and requests == []


def test_explicit_snapshot_reply_reuses_analysis_no_new_qualification(transport, tmp_path, capsys):
    path = tmp_path / "analysis.json"
    requests, _ = transport([envelope(qualification())])
    assert smoke_test.main(["--scenario", "persian", "--save-analysis", str(path)]) == 0
    first = read_report(capsys)
    assert len(requests) == 1 and "fake-acceptance-key" not in path.read_text(encoding="utf-8")
    second_requests, _ = transport([envelope(draft())])
    assert smoke_test.main(["--scenario", "reply", "--analysis-file", str(path)]) == 0
    second = read_report(capsys)
    assert len(second_requests) == 1
    assert json.loads(second_requests[0].content)["text"]["format"]["name"] == "suggested_reply"
    assert second["prior_usage"] == first["usage"] and second["score"] == first["score"]


def test_existing_snapshot_not_overwritten_no_http(transport, tmp_path, capsys):
    path = tmp_path / "analysis.json"
    path.write_text("existing", encoding="utf-8")
    requests, _ = transport([])
    assert smoke_test.main(["--scenario", "persian", "--save-analysis", str(path)]) == 2
    assert read_report(capsys, failed=True)["paid_api_request_attempts"] == 0
    assert requests == [] and path.read_text() == "existing"


def test_invalid_snapshot_no_http(transport, tmp_path, capsys):
    path = tmp_path / "analysis.json"
    path.write_text("{}", encoding="utf-8")
    requests, _ = transport([])
    assert smoke_test.main(["--scenario", "reply", "--analysis-file", str(path)]) == 2
    assert read_report(capsys, failed=True)["paid_api_request_attempts"] == 0 and requests == []


def test_snapshot_refuses_secret_before_json_escaping(monkeypatch, tmp_path):
    key = 'fake-"escaped-key'
    monkeypatch.setenv("OPENAI_API_KEY", key)
    inputs = smoke_test.build_input("persian")
    qualified = QualificationResult(**qualification(need=key))
    output = AgentOutput(screening=ScreeningResult(is_candidate=True, reason="Need"),
        qualification=qualified, scoring=calculate_score(qualified, valid_purchase_evidence=True))
    path = tmp_path / "analysis.json"
    with pytest.raises(ValueError, match="secret"):
        acceptance.save_snapshot(path, inputs, output)
    assert not path.exists()


@pytest.mark.parametrize("scenario,result,failed_check", [
    ("persian", qualification(need="A course costs $100"), "unsupported_numeric_claim"),
    ("context", qualification("context", intent="technical_help", need="Wants to debug a Python error"), "context_price_objection"),
])
def test_unsupported_claim_or_incorrect_context_interpretation_stops(scenario, result, failed_check, transport, capsys):
    requests, _ = transport([envelope(result)])
    assert smoke_test.main(["--scenario", scenario]) == 2
    report = read_report(capsys, failed=True)
    assert len(requests) == report["paid_api_request_attempts"] == 1
    assert report["usage"][0]["outcome"] == "success"  # Provider succeeded; acceptance assertion failed.
    assert report["failed_check"] == failed_check


def test_valid_context_target_only_evidence_reproduces_old_failure_shape(transport, capsys):
    # Synthetic offline qualification, NOT a recovered live response. This valid
    # citation pattern failed the old mandatory-context-quote assertion.
    result = qualification("context", evidence=[dict(message_id="smoke-context-target",
        quote=smoke_test.CONTEXT_TARGET, reason="A possible contextual price objection")])
    requests, _ = transport([envelope(result, usage=dict(input_tokens=1170, output_tokens=438,
        input_tokens_details=dict(cached_tokens=0)))])
    assert smoke_test.main(["--scenario", "context"]) == 0
    report = read_report(capsys)
    assert len(requests) == report["paid_api_request_attempts"] == 1
    assert report["checks"]["context_evidence_present"] is False
    assert report["checks"]["context_price_objection"] is True and report["checks"]["evidence_grounded"] is True
    assert (report["usage"][0]["input_tokens"], report["usage"][0]["output_tokens"]) == (1170, 438)
    assert report["usage"][0]["outcome"] == "success"


@pytest.mark.parametrize("updates,failed_check", [
    (dict(evidence=[]), "evidence_present"),
    (dict(intent=""), "intent_and_need"),
    (dict(need=" "), "intent_and_need"),
    (dict(need="اعتراض به قیمت ۱۰۰ تومان برای دوره"), "unsupported_numeric_claim"),
])
def test_post_provider_checks_have_safe_named_diagnostics(updates, failed_check, transport, capsys):
    requests, _ = transport([envelope(qualification("context", **updates))])
    assert smoke_test.main(["--scenario", "context"]) == 2
    report = read_report(capsys, failed=True)
    assert report["failed_check"] == failed_check and report["failure_category"]
    assert report["explanation"] == acceptance.validation_diagnostic(failed_check)["explanation"]
    assert "output" not in report and "intent" not in report and "evidence" not in report
    assert len(requests) == 1 and report["usage"][0]["outcome"] == "success"


def test_failed_acceptance_snapshot_retained_and_replayed_offline(transport, tmp_path, capsys, monkeypatch):
    path = tmp_path / "context.json"
    requests, _ = transport([envelope(qualification("context", need="The course costs $100"))])
    assert smoke_test.main(["--scenario", "context", "--save-analysis", str(path)]) == 2
    failed = read_report(capsys, failed=True)
    assert failed["failed_check"] == "unsupported_numeric_claim" and len(requests) == 1
    assert path.exists()
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setattr(smoke_test, "analyze_agent", lambda *args: pytest.fail("Replay must not analyze"))
    monkeypatch.setattr(smoke_test.httpx, "Client", lambda **kwargs: pytest.fail("Replay must not construct HTTP client"))
    assert smoke_test.main(["--scenario", "context", "--replay-analysis", str(path)]) == 2
    replay = read_report(capsys, failed=True)
    assert replay["failed_check"] == failed["failed_check"] and replay["usage"] == failed["usage"]
    assert replay["paid_api_request_attempts"] == 0 and replay["execution_mode"] == "offline_replay"


def test_valid_replay_requires_no_credentials_or_new_usage(transport, tmp_path, capsys, monkeypatch):
    path = tmp_path / "context.json"
    transport([envelope(qualification("context"))])
    assert smoke_test.main(["--scenario", "context", "--save-analysis", str(path)]) == 0
    recorded = read_report(capsys)
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL", "OPENAI_PRICE_VERSION",
        "OPENAI_INPUT_USD_PER_MILLION", "OPENAI_OUTPUT_USD_PER_MILLION"):
        monkeypatch.delenv(name)
    monkeypatch.setattr(smoke_test.httpx, "Client", lambda **kwargs: pytest.fail("Replay must not use HTTP"))
    assert smoke_test.main(["--scenario", "context", "--replay-analysis", str(path)]) == 0
    replay = read_report(capsys)
    assert replay["usage"] == recorded["usage"] and replay["score"] == recorded["score"]
    assert replay["decision"] == recorded["decision"] and replay["usage_from_recording"] is True
    assert replay["paid_api_request_attempts"] == 0 and replay["execution_mode"] == "offline_replay"
    assert smoke_test.main(["--scenario", "persian", "--replay-analysis", str(path)]) == 2
    assert read_report(capsys, failed=True)["failed_check"] == "scenario_match"


def test_raw_local_validation_exception_never_exposed(monkeypatch, capsys):
    def fail(*args):
        raise ValueError("fake-acceptance-key Authorization Bearer RAW_DETAIL")
    monkeypatch.setattr(smoke_test, "analyze_agent", fail)
    assert smoke_test.main(["--scenario", "context"]) == 2
    report = read_report(capsys, failed=True)
    assert report["failed_check"] == "analysis_output_validation"
    assert "RAW_DETAIL" not in json.dumps(report) and "Authorization" not in json.dumps(report)


def helper_output(updates=None):
    q = QualificationResult(**qualification("context", **(updates or {})))
    output = AgentOutput(screening=ScreeningResult(is_candidate=True, reason="Context"), qualification=q,
        scoring=calculate_score(q, valid_purchase_evidence=any(e.message_id == "smoke-context-target" for e in q.evidence)),
        usage=[UsageInfo(stage="qualification", provider_mode="real", outcome="success")])
    return smoke_test.build_input("context"), output


@pytest.mark.parametrize("evidence", [
    [dict(message_id="unknown", quote=smoke_test.CONTEXT_TEXT, reason="Unknown source")],
    [dict(message_id="smoke-context", quote="Invented course price", reason="Fabricated quote")],
    [dict(message_id="smoke-context", quote=smoke_test.CONTEXT_TARGET, reason="Wrong source")],
])
def test_acceptance_still_rejects_all_ungrounded_context_evidence(evidence):
    inputs, output = helper_output(dict(evidence=evidence))
    with pytest.raises(acceptance.AcceptanceValidationError) as exc:
        acceptance.analysis_checks(inputs, output, contextual=True)
    assert exc.value.diagnostic["failed_check"] == "evidence_grounding"
    assert exc.value.diagnostic["failure_category"] == "source_evidence"


@pytest.mark.parametrize("mutation,failed_check", [
    (lambda inputs, output: setattr(output.scoring, "score", output.scoring.score + 1), "deterministic_score_and_guards"),
    (lambda inputs, output: setattr(output.usage[0], "provider_mode", "mock"), "real_usage"),
    (lambda inputs, output: setattr(output.qualification, "confidence", 2.), "qualification_schema"),
    (lambda inputs, output: setattr(output.screening, "is_candidate", False), "screening_retained"),
    (lambda inputs, output: output.model_copy(update={"scoring": None}), "analysis_complete"),
    (lambda inputs, output: inputs.context_messages.append(inputs.context_messages[0]), "input_validation"),
])
def test_other_acceptance_checks_are_not_silently_skipped(mutation, failed_check):
    inputs, output = helper_output()
    replacement = mutation(inputs, output)
    if replacement is not None:
        output = replacement
    with pytest.raises(acceptance.AcceptanceValidationError) as exc:
        acceptance.analysis_checks(inputs, output, contextual=True)
    assert exc.value.diagnostic["failed_check"] == failed_check


def test_missing_context_is_a_context_input_failure():
    inputs, output = helper_output(dict(evidence=[dict(message_id="smoke-context-target", quote=smoke_test.CONTEXT_TARGET, reason="Target")]))
    inputs.context_messages = []
    with pytest.raises(acceptance.AcceptanceValidationError) as exc:
        acceptance.analysis_checks(inputs, output, contextual=True)
    assert exc.value.diagnostic["failed_check"] == "context_supplied"


def test_invalid_grounding_uses_only_one_repair(transport, capsys):
    invalid = qualification(evidence=[dict(message_id="invented", quote="invented", reason="Invalid")])
    requests, _ = transport([envelope(invalid)] * 2)
    assert smoke_test.main(["--scenario", "acceptance"]) == 1
    assert read_report(capsys, failed=True)["paid_api_request_attempts"] == len(requests) == 2


def test_ignore_never_forced_into_reply(transport, capsys):
    low = qualification(purchase_intent=0., product_fit=0., need_strength=0., confidence=.2, response_opportunity=.1)
    requests, _ = transport([envelope(low), envelope(qualification("context"))])
    assert smoke_test.main(["--scenario", "acceptance"]) == 2
    report = read_report(capsys, failed=True)
    assert report["completed_scenarios"][0]["decision"] == "IGNORE"
    assert len(requests) == report["paid_api_request_attempts"] == 2


def test_review_draft_keeps_review(transport, capsys):
    requests, _ = transport([envelope(qualification(confidence=.4)), envelope(qualification("context")), envelope(draft())])
    assert smoke_test.main(["--scenario", "acceptance"]) == 0
    report = read_report(capsys)
    assert report["results"][0]["decision"] == report["results"][2]["decision"] == "REVIEW"
    data = json.loads(json.loads(requests[-1].content)["input"][-1]["content"])
    assert data["human_review_required"] is True


def test_timeout_is_one_attempt_no_retry(transport, capsys):
    requests, _ = transport([httpx.ReadTimeout("fake-acceptance-key")])
    assert smoke_test.main(["--scenario", "acceptance"]) == 1
    report = read_report(capsys, failed=True)
    assert len(requests) == 1 and report["usage"][0]["outcome"] == "timeout"


def test_long_context_cannot_use_base_rate_in_report():
    usage = UsageInfo(stage="qualification", provider_mode="real", input_tokens=272001,
        output_tokens=10, estimated_cost=Decimal("1"), cost_status="known", outcome="success")
    report = acceptance.usage_report([usage])[0]
    assert report["estimated_cost"] is report["estimated_toman"] is None and report["cost_status"] == "unknown"
    assert usage.estimated_cost == Decimal("1")  # Reporting does not mutate the frozen contract.


def test_pacer_budget_and_endpoint_guard(environment):
    pacer = acceptance.RequestPacer(1)
    with pytest.raises(RuntimeError):
        pacer.before_request(httpx.Request("POST", "https://untrusted.example/responses"))
    assert pacer.request_count == 0
    request = httpx.Request("POST", "https://api.avalai.ir/v1/responses")
    pacer.before_request(request)
    with pytest.raises(RuntimeError):
        pacer.before_request(request)
    assert pacer.request_count == 1 and environment[0][0] == 65


def test_scoped_client_reset_on_exception():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
        with pytest.raises(RuntimeError), factory.real_provider_client(client):
            assert factory.get_provider("real")._client is client
            raise RuntimeError("Exit scoped client")
    assert factory._real_client.get() is None
    assert factory.get_provider("real")._client is None
