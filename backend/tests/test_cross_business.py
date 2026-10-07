"""Synthetic HTTP regressions test acceptance plumbing, not live model quality."""
import json

import httpx
import pytest

from app.agents import acceptance, cross_business as matrix
from app.agents.contracts import ProductInput
from app.agents.orchestrator import analyze_agent
from app.agents.providers import factory
from app.agents.providers.gemini import GeminiProvider
from app.agents.providers.gemini_config import GEMINI_BASE_URL, GEMINI_SMOKE_MODEL
from app.agents.providers.mock import MockProvider
from app.agents.providers.real import RealProvider

KEY = "fake-cross-business-key"
OTHER_KEY = "fake-cross-business-avalai-key"


def qualification(target, fit=.9, **changes):
    return dict(intent="searching_for_product", need=target["content"], purchase_intent=.85,
        product_fit=fit, need_strength=.85, urgency=0., confidence=.9, response_opportunity=.8,
        evidence=[dict(message_id=target["id"], quote=target["content"], reason="Exact supplied target")],
        limitations=[], **changes)


def envelope(value, **changes):
    return dict(model=GEMINI_SMOKE_MODEL, choices=[dict(finish_reason="stop",
        message=dict(role="assistant", content=json.dumps(value, ensure_ascii=False)))],
        usage=dict(prompt_tokens=100, completion_tokens=50), **changes)


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    for name in ("GEMINI_TIMEOUT_SECONDS", "GEMINI_MAX_OUTPUT_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in dict(LLM_PROVIDER="gemini", GEMINI_MODEL=GEMINI_SMOKE_MODEL,
        GEMINI_BASE_URL=GEMINI_BASE_URL, GEMINI_API_KEY=KEY, OPENAI_API_KEY=OTHER_KEY).items():
        monkeypatch.setenv(name, value)
    clock = [0.]
    def sleep(seconds):
        clock[0] += seconds
    monkeypatch.setattr(acceptance, "monotonic", lambda: clock[0])
    monkeypatch.setattr(acceptance, "sleep", sleep)
    monkeypatch.setattr(MockProvider, "qualify_structured", lambda *a: pytest.fail("Mock fallback"))
    monkeypatch.setattr(RealProvider, "qualify_structured", lambda *a: pytest.fail("AvalAI fallback"))
    monkeypatch.setattr(GeminiProvider, "generate_reply_structured", lambda *a: pytest.fail("Automatic reply"))
    return clock


@pytest.fixture
def transport(monkeypatch, environment):
    original_client = httpx.Client
    clients = []
    def setup(handler):
        requests, times = [], []
        def handle(request):
            requests.append(request)
            times.append(environment[0])
            result = handler(request, len(requests))
            if isinstance(result, Exception):
                raise result
            return result if isinstance(result, httpx.Response) else httpx.Response(200, json=result)
        client = original_client(transport=httpx.MockTransport(handle))
        clients.append(client)
        def create(**kwargs):
            assert kwargs["follow_redirects"] is False
            client.event_hooks = kwargs["event_hooks"]
            return client
        monkeypatch.setattr(matrix.httpx, "Client", create)
        return requests, times, client
    yield setup
    for client in clients:
        client.close()


def synthetic_match(request, number):
    # Labels affect fake HTTP responses ONLY, never the runner or real prompts.
    products, _, expected = matrix.load_cases()
    body = json.loads(request.content)
    sources = json.loads(body["messages"][-1]["content"])
    product = next(p for p in products if p.name == sources["product"]["name"])
    fit = .9 if product.id == expected[sources["target"]["id"]] else .1
    return envelope(qualification(sources["target"], fit))


def read_report(capsys, failed=False):
    out = capsys.readouterr()
    assert KEY not in out.out + out.err and OTHER_KEY not in out.out + out.err
    return json.loads(out.err if failed else out.out)


def test_complete_nine_production_runs_change_fit_and_score_with_business(transport, capsys):
    requests, times, _ = transport(synthetic_match)
    assert matrix.main(["--provider", "gemini", "--json-only"]) == 0
    result = read_report(capsys)
    assert result["status"] == "automated_pass" and all(result["genericity_checks"].values())
    assert result["paid_api_request_attempts"] == len(requests) == 9
    assert times == list(range(65, 650, 65))
    assert result["human_review_required"] and not result["automatic_sending"]
    assert all(row["matched_score_higher"] for row in result["comparisons"].values())
    assert factory._real_client.get() is None
    products, messages, expected = matrix.load_cases()
    systems = set()
    for request, row in zip(requests, result["results"]):
        assert request.url == GEMINI_BASE_URL + "chat/completions"
        assert request.headers["Authorization"] == "Bearer " + KEY
        body = json.loads(request.content)
        systems.add(body["messages"][0]["content"])
        sources = json.loads(body["messages"][-1]["content"])
        product = next(p for p in products if p.id == row["business_id"])
        target = next(m for m in messages if m.id == row["message"])
        assert sources["product"]["name"] == product.name
        assert sources["product"]["description"] == product.description
        assert sources["product"]["target_customer"] == product.target_customer
        assert sources["target"]["content"] == target.content and sources["context"] == []
        assert "expected_business_id" not in json.dumps(body)
        for other in products:
            if other.id != product.id:
                assert other.name not in json.dumps(body)
        assert row["provider"] == "gemini" and row["provider_mode"] == "real"
        assert row["prompt_version"] == "qualify_gemini_v1" and row["scoring_version"] == "score_v1"
        assert row["request_count"] == 1 and row["usage"][0]["input_tokens"] == 100
        assert row["usage"][0]["estimated_cost"] is None and row["usage"][0]["cost_status"] == "unknown"
        assert row["evidence"][0]["quote"] == target.content
    # Identical trusted instructions; only supplied business data changes.
    assert len(systems) == 1
    assert all(p.name not in next(iter(systems)) for p in products)
    assert len({r["score"] for r in result["results"] if r["message"] == "message_1"}) == 2
    assert result["rankings"]["message_2"][0]["business"] == "PawCare Veterinary Clinic"


def test_unseen_business_names_are_not_restricted_by_agent_or_matrix(transport):
    _, messages, _ = matrix.load_cases()
    target = messages[2].model_copy(update={"id": "unseen-message", "content": "I need a solar battery. What does it cost?"})
    products = [ProductInput(id="new-a", name="Solstice Batteries", description="Solar batteries for homes.",
                            target_customer="Homeowners seeking solar power storage."),
                ProductInput(id="new-b", name="Orchid Music Studio", description="Music lessons for adults.",
                            target_customer="Adults learning instruments.")]
    cases = matrix.build_matrix(products, [target])
    assert len(cases) == 2 and cases[0].message == cases[1].message
    assert cases[0].product != cases[1].product and cases[0].metadata.run_id != cases[1].metadata.run_id
    def handler(request, number):
        source = json.loads(json.loads(request.content)["messages"][-1]["content"])
        return envelope(qualification(source["target"], .87 if number == 1 else .13))
    requests, _, client = transport(handler)
    with factory.real_provider_client(client):
        outputs = [analyze_agent(case) for case in cases]
    assert outputs[0].qualification.product_fit > outputs[1].qualification.product_fit
    assert outputs[0].scoring.score > outputs[1].scoring.score
    for case, output in zip(cases, outputs):
        assert matrix.validate_run(case, output, products, 1)["evidence_grounded"]
    assert len(requests) == 2
    # Inputs are independent deep copies; mutations cannot leak across runs.
    cases[0].message.content = "changed"
    assert cases[1].message.content == target.content


def ranked_rows(fits=(.9, .2, .1), scores=(81, 70, 60)):
    return [dict(message="new-message", business_id=business, business="Business " + business,
        signals=dict(product_fit=fit, need_strength=.7), score=score, decision="REVIEW",
        checks=dict(no_cross_business_fact_leakage=True, evidence_grounded=True))
        for business, fit, score in zip(("a", "b", "c"), fits, scores)]


@pytest.mark.parametrize("fits,passed", [((.9, .2, .1), True), ((.1, .9, .2), False),
    ((.9, .9, .1), False), ((.5, .5, .5), False), ((.501, .5, .1), True)])
def test_rankings_require_strict_fit_superiority_without_fixed_margin(fits, passed):
    result = matrix.summarize(list(reversed(ranked_rows(fits))), {"new-message": "a"}, ["a", "b", "c"])
    assert result["genericity_checks"]["new-message_correct_business_ranked_highest"] is passed
    assert (result["status"] == "automated_pass") is passed
    if passed:
        assert result["rankings"]["new-message"][0]["business"] == "Business a"


def test_score_and_need_strength_comparisons_are_diagnostic_not_forced():
    result = matrix.summarize(ranked_rows(scores=(29, 81, 60)), {"new-message": "a"}, ["a", "b", "c"])
    assert result["status"] == "automated_pass"
    assert not result["comparisons"]["new-message"]["matched_score_higher"]
    assert not result["comparisons"]["new-message"]["matched_need_strength_higher"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra", "unknown_label"])
def test_incomplete_or_duplicated_matrix_cannot_pass(change):
    rows, expected = ranked_rows(), {"new-message": "a"}
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows.append(rows[0])
    elif change == "extra":
        rows.append({**rows[0], "message": "unexpected"})
    else:
        expected = {"new-message": "unknown"}
    with pytest.raises(matrix.MatrixValidationError, match="Matrix"):
        matrix.summarize(rows, expected, ["a", "b", "c"])


@pytest.mark.parametrize("failure", [httpx.Response(status, json={"error": KEY}) for status in
    (400, 401, 403, 404, 429, 500)] + [httpx.ReadTimeout(KEY), httpx.ConnectError(KEY)])
def test_provider_failures_stop_with_partial_results_and_no_fallback(failure, transport, capsys):
    requests, _, _ = transport(lambda request, number: synthetic_match(request, number) if number == 1 else failure)
    assert matrix.main(["--json-only"]) == 1
    result = read_report(capsys, failed=True)
    assert result["status"] == "provider_error" and result["paid_api_request_attempts"] == len(requests) == 2
    assert len(result["results"]) == 1 and len(result["failed_usage"]) == 1
    assert result["failed_run"] == dict(message="message_2", business_id="python_course")


def test_all_nine_repairs_have_exact_budget_and_attempt_usage(transport, capsys):
    requests, times, _ = transport(lambda r, n: envelope({}) if n % 2 else synthetic_match(r, n))
    assert matrix.main(["--json-only"]) == 0
    result = read_report(capsys)
    assert result["paid_api_request_attempts"] == len(requests) == 18
    assert times == list(range(65, 1235, 65))
    for row in result["results"]:
        assert row["request_count"] == 2
        assert [u["stage"] for u in row["usage"]] == ["qualification", "qualification_repair"]
        assert [u["outcome"] for u in row["usage"]] == ["invalid_output", "success"]


def test_two_invalid_responses_fail_without_continuing_or_fabricating_results(transport, capsys):
    requests, _, _ = transport(lambda *a: envelope({}))
    assert matrix.main(["--json-only"]) == 1
    result = read_report(capsys, failed=True)
    assert result["results"] == [] and result["paid_api_request_attempts"] == len(requests) == 2
    assert len(result["failed_usage"]) == 2


@pytest.mark.parametrize("name", ["LLM_PROVIDER", "GEMINI_API_KEY", "GEMINI_BASE_URL", "GEMINI_MODEL"])
def test_missing_configuration_never_dispatches(name, monkeypatch, transport, capsys):
    monkeypatch.delenv(name)
    requests, _, _ = transport(lambda *a: pytest.fail("Unexpected call"))
    assert matrix.main(["--json-only"]) != 0
    assert read_report(capsys, failed=True)["paid_api_request_attempts"] == 0 and not requests


@pytest.mark.parametrize("selector", ["avalai", "mock", "", KEY])
def test_wrong_selector_fails_closed(selector, monkeypatch, transport, capsys):
    monkeypatch.setenv("LLM_PROVIDER", selector)
    requests, _, _ = transport(lambda *a: pytest.fail("Unexpected call"))
    assert matrix.main(["--json-only"]) != 0
    assert read_report(capsys, failed=True)["paid_api_request_attempts"] == 0 and not requests


@pytest.mark.parametrize("modification,check", [
    ("evidence", "evidence_grounding"), ("score", "scoring"), ("decision", "scoring"),
    ("reason", "scoring"), ("prompt", "provenance"), ("version", "provenance"),
    ("usage_mode", "provenance"), ("missing_evidence", "analysis_complete"),
    ("unknown_source", "evidence_grounding"), ("missing_usage", "analysis_complete"),
    ("suggested_reply", "analysis_complete"), ("attempt", "usage"),
])
def test_validation_guards_reject_bad_analysis(modification, check, transport):
    products, messages, _ = matrix.load_cases()
    inputs = matrix.build_matrix(products, messages)[0]
    _, _, client = transport(synthetic_match)
    with factory.real_provider_client(client):
        output = analyze_agent(inputs)
    if modification == "evidence":
        output.qualification.evidence[0].quote = "not in source"
    elif modification == "unknown_source":
        output.qualification.evidence[0].message_id = "foreign-message"
    elif modification == "missing_evidence":
        output.qualification.evidence.clear()
    elif modification == "score":
        output.scoring.score += 1
    elif modification == "decision":
        from app.agents.contracts import Decision
        output.scoring.decision = Decision.IGNORE
    elif modification == "reason":
        output = output.model_copy(update={"decision_reason": "wrong reason"})
    elif modification == "prompt":
        output = output.model_copy(update={"prompt_version": "qualify_real_v1"})
    elif modification == "version":
        output = output.model_copy(update={"scoring_version": "wrong version"})
    elif modification == "usage_mode":
        output.usage[0].provider_mode = "mock"
    elif modification == "missing_usage":
        output.usage.clear()
    elif modification == "suggested_reply":
        output = output.model_copy(update={"suggested_reply": "unexpected"})
    else:
        output.usage[0].attempt_no = 2
    with pytest.raises(matrix.MatrixValidationError) as exc:
        matrix.validate_run(inputs, output, products, 1)
    assert exc.value.failed_check == check


@pytest.mark.parametrize("need,failed", [("Needs software for a 12-person company", False),
    ("Needs B2B accounting software", False), ("The price is 12 dollars", True),
    ("The fee is $99", True), ("هزینه ۱۰۰ تومان است", True),
    ("نیازمند نرم‌افزار برای شرکتی با ۱۲ نفر", False),
    ("Wants to know the cost of 12-person company invoicing software", False),
    ("The price is USD 12", True), ("The cost is 12", True)])
def test_numeric_checks_allow_supplied_headcount_not_invented_prices(need, failed, transport):
    products, messages, _ = matrix.load_cases()
    inputs = matrix.build_matrix(products, messages)[8]
    _, _, client = transport(synthetic_match)
    with factory.real_provider_client(client):
        output = analyze_agent(inputs)
    output.qualification.need = need
    if failed:
        with pytest.raises(matrix.MatrixValidationError) as exc:
            matrix.validate_run(inputs, output, products, 1)
        assert exc.value.failed_check == "unsupported_amount"
    else:
        assert matrix.validate_run(inputs, output, products, 1)["no_unsupported_numeric_amounts"]


def test_foreign_product_profile_claim_is_detected_but_not_source_text(transport, capsys):
    def bad(request, number):
        response = synthetic_match(request, number)
        q = json.loads(response["choices"][0]["message"]["content"])
        q["need"] = "LedgerFlow offers this course"
        response["choices"][0]["message"]["content"] = json.dumps(q)
        return response
    requests, _, _ = transport(bad)
    assert matrix.main(["--json-only"]) == 2
    result = read_report(capsys, failed=True)
    assert result["failed_check"] == "foreign_profile_text" and len(requests) == 1
    assert result["status"] == "validation_error" and not result["results"]


def test_help_does_not_construct_client_or_call_api(transport, capsys):
    requests, _, _ = transport(lambda *a: pytest.fail("Unexpected call"))
    with pytest.raises(SystemExit) as exc:
        matrix.main(["--help"])
    assert exc.value.code == 0 and not requests
    assert "18 paced requests" in capsys.readouterr().out


def test_default_output_contains_compact_table_and_rankings(transport, capsys):
    transport(synthetic_match)
    assert matrix.main([]) == 0
    output = capsys.readouterr().out
    assert "provider/model | requests" in output and "message_1 ranking:" in output
    assert "message_2 ranking:" in output and "message_3 ranking:" in output
    assert "genericity_checks" in output and KEY not in output


def test_rate_budget_refuses_nineteenth_dispatch(environment):
    pacer = acceptance.RequestPacer(18, endpoint=GEMINI_BASE_URL + "chat/completions")
    request = httpx.Request("POST", pacer.endpoint)
    for _ in range(18):
        pacer.before_request(request)
    with pytest.raises(RuntimeError, match="budget"):
        pacer.before_request(request)
    assert pacer.request_count == 18


@pytest.mark.parametrize("expected,businesses", [({}, ["a", "b"]), ({"new-message": "a"}, []),
    ({"new-message": "a"}, ["a"]), ({"new-message": "a"}, ["a", "a", "b"])])
def test_empty_or_invalid_business_sets_cannot_pass(expected, businesses):
    with pytest.raises(matrix.MatrixValidationError):
        matrix.summarize([], expected, businesses)


def test_bad_fixture_labels_are_rejected_before_any_http_call(monkeypatch, transport, capsys):
    products, messages, _ = matrix.load_cases()
    monkeypatch.setattr(matrix, "load_cases", lambda: (products, messages, {m.id: "foreign" for m in messages}))
    requests, _, _ = transport(lambda *a: pytest.fail("Unexpected call"))
    assert matrix.main(["--json-only"]) == 2
    result = read_report(capsys, failed=True)
    assert result["failed_check"] == "matrix" and result["paid_api_request_attempts"] == 0 and not requests


def test_runner_ranking_failure_returns_nonzero_without_forcing_scores(transport, capsys):
    def identical_fit(request, number):
        source = json.loads(json.loads(request.content)["messages"][-1]["content"])
        return envelope(qualification(source["target"], .2))
    requests, _, _ = transport(identical_fit)
    assert matrix.main(["--json-only"]) == 2
    result = read_report(capsys, failed=True)
    assert result["status"] == "fail" and len(requests) == len(result["results"]) == 9
    assert not any(result["genericity_checks"][key] for key in result["genericity_checks"] if key.endswith("ranked_highest"))
    assert len({row["score"] for row in result["results"]}) == 1


def test_missing_token_usage_remains_null_and_unknown(transport, capsys):
    def no_usage(request, number):
        result = synthetic_match(request, number)
        del result["usage"]
        return result
    transport(no_usage)
    assert matrix.main(["--json-only"]) == 0
    result = read_report(capsys)
    for row in result["results"]:
        assert row["usage"][0]["input_tokens"] is None and row["usage"][0]["output_tokens"] is None
        assert row["usage"][0]["estimated_cost"] is None and row["usage"][0]["cost_status"] == "unknown"


def test_foreign_business_name_is_allowed_if_explicitly_in_target(transport):
    products, messages, _ = matrix.load_cases()
    target = messages[0].model_copy(update={"content": "I need LedgerFlow accounting software. What does it cost?"})
    inputs = matrix.build_matrix(products, [target])[0]
    def response(request, number):
        source = json.loads(json.loads(request.content)["messages"][-1]["content"])
        return envelope(qualification(source["target"], .1))
    _, _, client = transport(response)
    with factory.real_provider_client(client):
        output = analyze_agent(inputs)
    assert matrix.validate_run(inputs, output, products, 1)["no_cross_business_fact_leakage"]


def test_interrupt_stops_remaining_matrix_operations(transport, monkeypatch, capsys):
    requests, _, _ = transport(synthetic_match)
    original = matrix.analyze_agent
    def interrupt(inputs):
        if inputs.message.id == "message_2":
            raise KeyboardInterrupt
        return original(inputs)
    monkeypatch.setattr(matrix, "analyze_agent", interrupt)
    assert matrix.main(["--json-only"]) == 130
    result = read_report(capsys, failed=True)
    assert len(requests) == result["paid_api_request_attempts"] == 1
    assert result["status"] == "interrupted" and len(result["results"]) == 1
