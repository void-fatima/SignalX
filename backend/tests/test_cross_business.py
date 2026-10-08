"""Acceptance plumbing with synthetic HTTP; these tests do not measure LLM quality.

Adapted from Setayesh Samani's cross-business tests in commit 3a84276.
Labels condition fake HTTP only, never production requests or scoring.
"""
import copy
import json
from decimal import Decimal

import httpx
import pytest

from app.agents import acceptance, cross_business as matrix, orchestrator
from app.agents.contracts import Decision
from app.agents.providers import factory
from app.agents.providers.real import RealProvider

FAKE_KEY = "offline-http-fixture-not-a-credential"
MODEL = "gpt-5.6-luna"
BASE_URL = "https://api.avalai.ir/v1"


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    for name in tuple(matrix.os.environ):
        if name.startswith("OPENAI_") or name == "LLM_PROVIDER":
            monkeypatch.delenv(name)
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENAI_MODEL", MODEL)
    monkeypatch.setenv("OPENAI_BASE_URL", BASE_URL)
    clock = [0.0]
    monkeypatch.setattr(acceptance, "monotonic", lambda: clock[0])
    monkeypatch.setattr(acceptance, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    return clock


def qualification(sources, matched):
    target = sources["target"]
    return dict(intent="searching_for_product", need=target["content"],
        purchase_intent=.90, product_fit=.95 if matched else .10,
        need_strength=.85, urgency=.10, confidence=.85, response_opportunity=.90,
        evidence=[dict(message_id=target["id"], quote=target["content"], reason="Explicit request in the supplied target.")],
        limitations=[])


def envelope(payload):
    return dict(status="completed", model=MODEL,
        usage=dict(input_tokens=100, output_tokens=50, input_tokens_details=dict(cached_tokens=0)),
        output=[dict(type="message", content=[dict(type="output_text", text=json.dumps(payload))])])


@pytest.fixture
def transport(monkeypatch, environment):
    actual_client = httpx.Client

    def install(transform=None, *, repairs=False, fit_mode="normal"):
        requests, times, attempts = [], [], {}

        def handle(request):
            requests.append(request)
            times.append(environment[0])
            body = json.loads(request.content)
            sources = json.loads(body["input"][-1]["content"])
            products, _, expected = matrix.load_cases()
            product_id = next(p.id for p in products if p.name == sources["product"]["name"])
            pair = (product_id, sources["target"]["id"])
            attempts[pair] = attempts.get(pair, 0) + 1
            matched = expected[pair[1]] == pair[0]
            payload = qualification(sources, matched)
            if fit_mode == "tie":
                payload["product_fit"] = .5
            elif fit_mode == "reversed":
                payload["product_fit"] = .1 if matched else .9
            response = envelope({"unexpected": True} if repairs and attempts[pair] == 1 else payload)
            if transform is not None:
                response = transform(response, request, len(requests))
            if isinstance(response, Exception):
                raise response
            return response if isinstance(response, httpx.Response) else httpx.Response(200, json=response)

        monkeypatch.setattr(matrix.httpx, "Client", lambda **kwargs:
            actual_client(transport=httpx.MockTransport(handle), **kwargs))
        return requests, times

    return install


def report(capsys, *, failed=False):
    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.out + captured.err
    return json.loads(captured.err if failed else captured.out)


def test_nine_analyses_use_real_production_path_and_isolated_profiles(transport, monkeypatch, capsys):
    requests, times = transport()
    actual_provider = orchestrator.get_provider
    providers = []

    def tracked(mode):
        assert mode == "real"
        provider = actual_provider(mode)
        providers.append(type(provider))
        return provider

    monkeypatch.setattr(orchestrator, "get_provider", tracked)
    assert matrix.main(["--provider", "avalai", "--json-only"]) == 0
    result = report(capsys)
    assert result["status"] == "automated_pass"
    assert len(requests) == result["paid_api_request_attempts"] == 9
    assert providers == [RealProvider] * 9 and factory._real_client.get() is None
    assert times == list(range(65, 650, 65))
    assert all(result["genericity_checks"].values())
    assert result["human_review_required"] and not result["automatic_sending"]
    products, targets, _ = matrix.load_cases()
    assert len({row["score"] for row in result["results"] if row["message"] == "message_1"}) == 2
    for request, row in zip(requests, result["results"]):
        assert str(request.url) == BASE_URL + "/responses"
        assert request.headers["Authorization"] == "Bearer " + FAKE_KEY
        body = json.loads(request.content)
        sources = json.loads(body["input"][-1]["content"])
        profile = next(p for p in products if p.id == row["business_id"])
        target = next(m for m in targets if m.id == row["message"])
        for field in ("name", "description", "target_customer"):
            assert sources["product"][field] == getattr(profile, field)
        assert sources["target"]["content"] == target.content and sources["context"] == []
        assert "expected_business_id" not in request.content.decode()
        assert all(p.name not in request.content.decode() for p in products if p.id != profile.id)
        schema = body["text"]["format"]
        assert schema["strict"] and schema["schema"]["additionalProperties"] is False
        assert not {"score", "decision"} & schema["schema"]["properties"].keys()
        assert row["provider"] == "avalai" and row["model"] == MODEL
        assert row["prompt_version"] == "qualify_real_v1" and row["scoring_version"] == "score_v1"
        assert row["request_count"] == 1 and row["evidence"][0]["quote"] == target.content


def test_unseen_business_profiles_need_no_production_special_cases(transport, monkeypatch, capsys):
    products, messages, expected = matrix.load_cases()
    names = ["Boreal", "Cedar", "Delta"]
    for index, product in enumerate(products):
        product.name = names[index]
        product.description = "Independent consulting service " + names[index]
        product.target_customer = "Customers seeking " + names[index]
    for message in messages:
        product = next(p for p in products if p.id == expected[message.id])
        message.content = "I am looking for " + product.name + ". How much does it cost?"
    monkeypatch.setattr(matrix, "load_cases", lambda: (products, messages, expected))
    requests, _ = transport()
    assert matrix.main(["--json-only"]) == 0
    result = report(capsys)
    assert len(requests) == 9 and {row["business"] for row in result["results"]} == set(names)


@pytest.mark.parametrize("mode", ["tie", "reversed"])
def test_ties_and_incorrect_rankings_fail(transport, capsys, mode):
    requests, _ = transport(fit_mode=mode)
    assert matrix.main(["--json-only"]) == 2
    result = report(capsys, failed=True)
    assert len(requests) == 9 and result["status"] == "fail"
    assert all(not value for key, value in result["genericity_checks"].items() if key.endswith("ranked_highest"))


def test_missing_duplicate_or_foreign_results_cannot_pass(transport, capsys):
    transport()
    assert matrix.main(["--json-only"]) == 0
    rows = report(capsys)["results"]
    products, _, expected = matrix.load_cases()
    bad = copy.deepcopy(rows)
    bad[0]["business_id"] = "unknown-business"
    for invalid in ([], rows[:-1], rows + [rows[0]], bad):
        with pytest.raises(matrix.MatrixValidationError, match=matrix.CHECKS["matrix"]):
            matrix.summarize(invalid, expected, [p.id for p in products])


def test_score_and_need_comparisons_do_not_force_decisions(transport, capsys):
    transport()
    assert matrix.main(["--json-only"]) == 0
    rows = report(capsys)["results"]
    products, _, expected = matrix.load_cases()
    for row in rows:
        row["score"] = 1 if row["business_id"] == expected[row["message"]] else 99
        row["signals"]["need_strength"] = .2
    result = matrix.summarize(rows, expected, [p.id for p in products])
    assert result["status"] == "automated_pass"
    assert all(not comparison["matched_score_higher"] for comparison in result["comparisons"].values())


@pytest.mark.parametrize("failure", [400, 401, 403, 404, 429, 500, "timeout", "network"])
def test_provider_failure_stops_remaining_cases_and_sanitizes_errors(transport, capsys, failure):
    def fail(body, request, number):
        if number == 1:
            return body
        if failure == "timeout":
            return httpx.ReadTimeout(FAKE_KEY)
        if failure == "network":
            return httpx.ConnectError(FAKE_KEY)
        return httpx.Response(failure, json={"error": {"message": FAKE_KEY}})

    requests, _ = transport(fail)
    assert matrix.main(["--json-only"]) == 1
    result = report(capsys, failed=True)
    assert result["status"] == "provider_error" and len(requests) == result["paid_api_request_attempts"] == 2
    assert len(result["results"]) == 1 and len(result["failed_usage"]) == 1
    assert factory._real_client.get() is None


def test_one_repair_per_analysis_is_paced_and_recorded(transport, capsys):
    requests, times = transport(repairs=True)
    assert matrix.main(["--json-only"]) == 0
    result = report(capsys)
    assert len(requests) == result["paid_api_request_attempts"] == 18
    assert times == list(range(65, 1235, 65))
    for row in result["results"]:
        assert row["request_count"] == 2
        assert [u["stage"] for u in row["usage"]] == ["qualification", "qualification_repair"]
        assert [u["outcome"] for u in row["usage"]] == ["invalid_output", "success"]


@pytest.mark.parametrize("bad_evidence", ["unknown_id", "invented_quote", "malformed"])
def test_invalid_provider_output_fails_after_single_repair(transport, capsys, bad_evidence):
    def corrupt(body, request, number):
        payload = json.loads(body["output"][0]["content"][0]["text"])
        if bad_evidence == "unknown_id":
            payload["evidence"][0]["message_id"] = "unavailable-message"
        elif bad_evidence == "invented_quote":
            payload["evidence"][0]["quote"] = "Not in supplied sources"
        body["output"][0]["content"][0]["text"] = "{" if bad_evidence == "malformed" else json.dumps(payload)
        return body

    requests, _ = transport(corrupt)
    assert matrix.main(["--json-only"]) == 1
    result = report(capsys, failed=True)
    assert len(requests) == 2 and not result["results"]
    assert [u["outcome"] for u in result["failed_usage"]] == ["invalid_output", "invalid_output"]


@pytest.mark.parametrize("change,check", [("quote", "evidence_grounding"), ("score", "scoring"),
    ("decision", "scoring"), ("reason", "scoring"), ("foreign", "foreign_profile_text"),
    ("price", "unsupported_amount"), ("prompt", "provenance"), ("mock_usage", "provenance"),
    ("missing_qualification", "analysis_complete"), ("missing_evidence", "analysis_complete"),
    ("missing_usage", "analysis_complete"), ("usage_stage", "usage")])
def test_local_acceptance_guards_remain_strict(transport, monkeypatch, capsys, change, check):
    requests, _ = transport()
    actual = matrix.analyze_agent

    def corrupted(inputs):
        output = actual(inputs)
        if change == "quote":
            output.qualification.evidence[0].quote = "Invented quote"
        elif change == "score":
            output.scoring.score += 1
        elif change == "decision":
            output.scoring.decision = Decision.IGNORE
        elif change == "reason":
            output = output.model_copy(update={"decision_reason": "Invented scoring reason"})
        elif change == "foreign":
            output.qualification.need = "LedgerFlow offers this course"
        elif change == "price":
            output.qualification.need = "The fee is $99"
        elif change == "prompt":
            output = output.model_copy(update={"prompt_version": "wrong_prompt"})
        elif change == "mock_usage":
            output.usage[0].provider_mode = "mock"
            output.usage[0].cost_status = "mock"
            output.usage[0].estimated_cost = Decimal("0")
        elif change == "missing_qualification":
            output = output.model_copy(update={"qualification": None})
        elif change == "missing_evidence":
            output.qualification.evidence = []
        elif change == "missing_usage":
            output = output.model_copy(update={"usage": []})
        elif change == "usage_stage":
            output.usage[0].stage = "suggested_reply"
        return output

    monkeypatch.setattr(matrix, "analyze_agent", corrupted)
    assert matrix.main(["--json-only"]) == 2
    result = report(capsys, failed=True)
    assert result["failed_check"] == check and len(requests) == 1 and not result["results"]


@pytest.mark.parametrize("case", ["known", "cached", "model_mismatch", "missing_tokens", "unknown_cache"])
def test_usage_and_cost_preserve_actual_provider_metadata(transport, monkeypatch, capsys, case):
    monkeypatch.setenv("OPENAI_INPUT_USD_PER_MILLION", "0.20")
    monkeypatch.setenv("OPENAI_OUTPUT_USD_PER_MILLION", "1.20")
    monkeypatch.setenv("OPENAI_PRICE_VERSION", "offline-test-rates")

    def change(body, request, number):
        if case == "cached":
            body["usage"]["input_tokens_details"]["cached_tokens"] = 25
        elif case == "model_mismatch":
            body["model"] = "different-reported-model"
        elif case == "missing_tokens":
            body["usage"] = None
        elif case == "unknown_cache":
            body["usage"].pop("input_tokens_details")
        return body

    transport(change)
    assert matrix.main(["--json-only"]) == 0
    for row in report(capsys)["results"]:
        usage = row["usage"][0]
        if case == "known":
            assert usage["cost_status"] == "known"
            assert Decimal(usage["estimated_cost"]) == Decimal("0.00008")
            assert Decimal(usage["estimated_toman"]) == Decimal("21.6")
            assert usage["price_version"] == "offline-test-rates"
        else:
            assert usage["cost_status"] == "unknown" and usage["estimated_cost"] is None
        if case == "missing_tokens":
            assert usage["input_tokens"] is usage["output_tokens"] is None
        if case == "model_mismatch":
            assert row["model"] == "different-reported-model"
        assert usage["exact_account_charge"] is False


@pytest.mark.parametrize("missing", ["OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL"])
def test_missing_configuration_never_dispatches(transport, monkeypatch, capsys, missing):
    monkeypatch.delenv(missing)
    requests, _ = transport()
    assert matrix.main(["--json-only"]) == 2
    result = report(capsys, failed=True)
    assert result["failed_check"] == "configuration" and not requests


@pytest.mark.parametrize("selection", ["gemini", "mock", "invalid", ""])
def test_other_provider_selection_is_rejected(transport, monkeypatch, capsys, selection):
    monkeypatch.setenv("LLM_PROVIDER", selection)
    requests, _ = transport()
    assert matrix.main(["--json-only"]) == 2
    assert report(capsys, failed=True)["failed_check"] == "configuration" and not requests


def test_openai_endpoint_cannot_be_mislabeled_avalai(transport, monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    requests, _ = transport()
    assert matrix.main(["--json-only"]) == 2
    assert report(capsys, failed=True)["failed_check"] == "configuration" and not requests


@pytest.mark.parametrize("provider", ["gemini", "mock", "openai", "invalid"])
def test_unsupported_cli_provider_is_rejected(monkeypatch, provider):
    monkeypatch.setattr(matrix.httpx, "Client", lambda **kwargs: pytest.fail("Unexpected HTTP client"))
    with pytest.raises(SystemExit) as error:
        matrix.main(["--provider", provider])
    assert error.value.code == 2


def test_help_never_constructs_http_client(monkeypatch):
    monkeypatch.setattr(matrix.httpx, "Client", lambda **kwargs: pytest.fail("Unexpected HTTP client"))
    with pytest.raises(SystemExit) as error:
        matrix.main(["--help"])
    assert error.value.code == 0


def test_invalid_fixture_labels_fail_before_http(transport, monkeypatch, capsys):
    products, messages, expected = matrix.load_cases()
    expected[messages[0].id] = "unknown-product"
    monkeypatch.setattr(matrix, "load_cases", lambda: (products, messages, expected))
    requests, _ = transport()
    assert matrix.main(["--json-only"]) == 2
    assert report(capsys, failed=True)["failed_check"] == "matrix" and not requests


def test_request_budget_blocks_nineteenth_attempt():
    pacer = acceptance.RequestPacer(matrix.REQUEST_BUDGET)
    request = httpx.Request("POST", BASE_URL + "/responses")
    for _ in range(18):
        pacer.before_request(request)
    with pytest.raises(RuntimeError, match="budget exhausted"):
        pacer.before_request(request)
    assert pacer.request_count == 18


def test_default_output_contains_comparison_table_and_rankings(transport, capsys):
    transport()
    assert matrix.main([]) == 0
    text = capsys.readouterr().out
    assert "provider/model" in text and "message_1 ranking:" in text
    assert "message_2 ranking:" in text and "message_3 ranking:" in text
    assert FAKE_KEY not in text


def test_interruption_stops_remaining_cases(transport, capsys):
    def interrupt(body, request, number):
        if number == 2:
            raise KeyboardInterrupt
        return body

    requests, _ = transport(interrupt)
    assert matrix.main(["--json-only"]) == 130
    result = report(capsys, failed=True)
    assert len(requests) == 2 and len(result["results"]) == 1
    assert result["paid_api_request_attempts"] == 2
