"""Dual-provider acceptance regressions. Synthetic HTTP is not model evaluation."""
import json
from decimal import Decimal

import httpx
import pytest

from app.agents import acceptance, cross_business as matrix, orchestrator
from app.agents.providers import factory
from app.agents.providers.gemini import GeminiProvider
from app.agents.providers.gemini_config import GEMINI_BASE_URL
from app.agents.providers.mock import MockProvider
from app.agents.providers.real import RealProvider

FAKE_KEY = "fake-dual-provider-acceptance-key"


@pytest.fixture(params=["gemini", "avalai"])
def provider(request, monkeypatch):
    selected = request.param
    # Isolate both providers from credentials/pricing in the invoking terminal.
    for prefix in ("GEMINI", "OPENAI"):
        for suffix in ("API_KEY", "MODEL", "BASE_URL", "TIMEOUT_SECONDS", "MAX_OUTPUT_TOKENS",
                       "PRICE_VERSION", "INPUT_USD_PER_MILLION", "OUTPUT_USD_PER_MILLION"):
            monkeypatch.delenv(f"{prefix}_{suffix}", raising=False)
    prefix = "GEMINI" if selected == "gemini" else "OPENAI"
    monkeypatch.setenv("LLM_PROVIDER", selected)
    monkeypatch.setenv(f"{prefix}_API_KEY", FAKE_KEY)
    monkeypatch.setenv(f"{prefix}_MODEL", "gemini-3.5-flash-lite" if selected == "gemini" else "gpt-5.6-luna")
    monkeypatch.setenv(f"{prefix}_BASE_URL", GEMINI_BASE_URL if selected == "gemini" else "https://api.avalai.ir/v1")
    clock = [0.]
    monkeypatch.setattr(acceptance, "monotonic", lambda: clock[0])
    monkeypatch.setattr(acceptance, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(MockProvider, "qualify_structured", lambda *a: pytest.fail("Mock fallback"))
    other = RealProvider if selected == "gemini" else GeminiProvider
    monkeypatch.setattr(other, "qualify_structured", lambda *a: pytest.fail("Provider fallback"))
    for cls in (RealProvider, GeminiProvider):
        monkeypatch.setattr(cls, "generate_reply_structured", lambda *a: pytest.fail("Automatic reply"))
    return selected, prefix, clock


def envelope(provider, requested_model, value, **changes):
    text = json.dumps(value, ensure_ascii=False)
    if provider == "gemini":
        body = dict(model=requested_model, choices=[dict(finish_reason="stop", message=dict(role="assistant", content=text))],
                    usage=dict(prompt_tokens=100, completion_tokens=50))
    else:
        body = dict(model=requested_model, status="completed", output=[dict(type="message",
                    content=[dict(type="output_text", text=text)])],
                    usage=dict(input_tokens=100, output_tokens=50, input_tokens_details=dict(cached_tokens=0)))
    return {**body, **changes}


def payload(target, fit):
    return dict(intent="searching_for_product", need=target["content"], purchase_intent=.85,
                product_fit=fit, need_strength=.85, urgency=0., confidence=.9, response_opportunity=.8,
                evidence=[dict(message_id=target["id"], quote=target["content"], reason="Exact supplied target")],
                limitations=[])


@pytest.fixture
def transport(provider, monkeypatch):
    selected, _, clock = provider
    original_client = httpx.Client
    clients = []
    def setup(transform=None, *, fit_mode="matched", repairs=False, body_changes=None):
        requests, times = [], []
        products, _, labels = matrix.load_cases()
        def handle(request):
            requests.append(request)
            times.append(clock[0])
            body = json.loads(request.content)
            messages = body["messages"] if selected == "gemini" else body["input"]
            source = json.loads(messages[-1]["content"])
            # Labels choose synthetic HTTP outputs only; not live Agent inputs.
            product = next(p for p in products if p.name == source["product"]["name"])
            matched = product.id == labels[source["target"]["id"]]
            fit = .9 if matched else .1
            if fit_mode == "tie":
                fit = .2
            elif fit_mode == "reversed":
                fit = .1 if matched else .9
            q = {} if repairs and len(requests) % 2 else payload(source["target"], fit)
            result = envelope(selected, body["model"], q, **(body_changes or {}))
            if transform:
                result = transform(result, request, len(requests))
            if isinstance(result, Exception):
                raise result
            return result if isinstance(result, httpx.Response) else httpx.Response(200, json=result)
        client = original_client(transport=httpx.MockTransport(handle))
        clients.append(client)
        def create(**kwargs):
            assert kwargs["timeout"] == 30 and kwargs["follow_redirects"] is False
            client.event_hooks = kwargs["event_hooks"]
            return client
        monkeypatch.setattr(matrix.httpx, "Client", create)
        return requests, times
    yield setup
    for client in clients:
        client.close()


def report(capsys, failed=False):
    output = capsys.readouterr()
    assert FAKE_KEY not in output.out + output.err
    return json.loads(output.err if failed else output.out)


def test_both_cli_choices_use_nine_production_analyses(provider, transport, monkeypatch, capsys):
    selected, _, _ = provider
    requests, times = transport()
    actual_get_provider = orchestrator.get_provider
    providers = []
    def tracked_get_provider(mode):
        assert mode == "real"
        result = actual_get_provider(mode)
        providers.append(type(result))
        return result
    monkeypatch.setattr(orchestrator, "get_provider", tracked_get_provider)
    assert matrix.main(["--provider", selected, "--json-only"]) == 0
    result = report(capsys)
    assert len(requests) == result["paid_api_request_attempts"] == 9
    assert times == list(range(65, 650, 65))
    assert providers == [GeminiProvider if selected == "gemini" else RealProvider] * 9
    assert factory._real_client.get() is None
    assert all(result["genericity_checks"].values()) and result["human_review_required"]
    assert not result["automatic_sending"]
    endpoint = GEMINI_BASE_URL + "chat/completions" if selected == "gemini" else "https://api.avalai.ir/v1/responses"
    assert result["provider"] == selected and result["endpoint"] == endpoint
    products, targets, _ = matrix.load_cases()
    for request, row in zip(requests, result["results"]):
        assert str(request.url) == row["endpoint"] == endpoint
        assert request.headers["Authorization"] == "Bearer " + FAKE_KEY
        assert row["provider"] == selected and row["provider_mode"] == "real"
        assert row["prompt_version"] == matrix.PROVIDER_PROMPT_VERSIONS[selected]
        assert row["scoring_version"] == "score_v1" and row["request_count"] == 1
        body = json.loads(request.content)
        assert row["model"] == body["model"] == result["requested_model"]
        messages = body["messages"] if selected == "gemini" else body["input"]
        sources = json.loads(messages[-1]["content"])
        profile = next(p for p in products if p.id == row["business_id"])
        target = next(m for m in targets if m.id == row["message"])
        for field in ("name", "description", "target_customer"):
            assert sources["product"][field] == getattr(profile, field)
        assert sources["target"]["content"] == target.content and sources["context"] == []
        assert "expected_business_id" not in request.content.decode()
        assert all(p.name not in request.content.decode() for p in products if p.id != profile.id)
        schema = body["response_format"]["json_schema"] if selected == "gemini" else body["text"]["format"]
        assert schema["strict"] and schema["schema"]["additionalProperties"] is False
        assert "score" not in schema["schema"]["properties"] and "decision" not in schema["schema"]["properties"]
        assert row["evidence"][0]["quote"] == target.content
        assert row["usage"][0]["input_tokens"] == 100 and row["usage"][0]["output_tokens"] == 50
        assert row["usage"][0]["cost_status"] == "unknown" and row["usage"][0]["estimated_cost"] is None
    assert len({r["score"] for r in result["results"] if r["message"] == "message_1"}) == 2


@pytest.mark.parametrize("mode", ["tie", "reversed"])
def test_neither_provider_can_pass_ties_or_wrong_business_ranking(provider, transport, capsys, mode):
    requests, _ = transport(fit_mode=mode)
    assert matrix.main(["--provider", provider[0], "--json-only"]) == 2
    result = report(capsys, failed=True)
    assert result["status"] == "fail" and len(requests) == 9
    assert all(not value for key, value in result["genericity_checks"].items() if key.endswith("ranked_highest"))


@pytest.mark.parametrize("suffix", ["API_KEY", "MODEL", "BASE_URL", "selector"])
def test_selected_provider_configuration_is_required(provider, transport, monkeypatch, capsys, suffix):
    selected, prefix, _ = provider
    monkeypatch.delenv("LLM_PROVIDER" if suffix == "selector" else f"{prefix}_{suffix}")
    requests, _ = transport()
    assert matrix.main(["--provider", selected, "--json-only"]) != 0
    result = report(capsys, failed=True)
    assert not requests and result["paid_api_request_attempts"] == 0


def test_invalid_inactive_provider_settings_do_not_affect_selection(provider, transport, monkeypatch, capsys):
    selected, prefix, _ = provider
    inactive = "OPENAI" if prefix == "GEMINI" else "GEMINI"
    for suffix in ("API_KEY", "MODEL", "BASE_URL", "TIMEOUT_SECONDS", "PRICE_VERSION"):
        monkeypatch.setenv(f"{inactive}_{suffix}", "invalid-inactive-setting")
    requests, _ = transport()
    assert matrix.main(["--provider", selected, "--json-only"]) == 0
    assert len(requests) == 9 and report(capsys)["provider"] == selected


def test_cli_selector_must_match_factory_selection(provider, transport, monkeypatch, capsys):
    monkeypatch.setenv("LLM_PROVIDER", "avalai" if provider[0] == "gemini" else "gemini")
    requests, _ = transport()
    assert matrix.main(["--provider", provider[0], "--json-only"]) == 2
    assert report(capsys, failed=True)["failed_check"] == "configuration" and not requests


@pytest.mark.parametrize("invalid", ["mock", "openai", "invalid"])
def test_cli_rejects_invalid_provider_without_constructing_client(monkeypatch, invalid):
    monkeypatch.setattr(matrix.httpx, "Client", lambda **kw: pytest.fail("Unexpected client"))
    with pytest.raises(SystemExit) as error:
        matrix.main(["--provider", invalid])
    assert error.value.code == 2


@pytest.mark.parametrize("failure", [401, 403, 429, 500, "timeout", "network"])
def test_both_providers_stop_on_first_failed_attempt_without_fallback(provider, transport, capsys, failure):
    def fail(body, request, number):
        if number == 1:
            return body
        if failure == "timeout":
            return httpx.ReadTimeout(FAKE_KEY)
        if failure == "network":
            return httpx.ConnectError(FAKE_KEY)
        return httpx.Response(failure, json={"error": {"message": FAKE_KEY}})
    requests, _ = transport(fail)
    assert matrix.main(["--provider", provider[0], "--json-only"]) == 1
    result = report(capsys, failed=True)
    assert result["status"] == "provider_error" and len(requests) == result["paid_api_request_attempts"] == 2
    assert len(result["results"]) == 1 and len(result["failed_usage"]) == 1


def test_both_providers_have_one_repair_per_analysis_and_same_budget(provider, transport, capsys):
    requests, times = transport(repairs=True)
    assert matrix.main(["--provider", provider[0], "--json-only"]) == 0
    result = report(capsys)
    assert len(requests) == result["paid_api_request_attempts"] == 18
    assert times == list(range(65, 1235, 65))
    for row in result["results"]:
        assert row["request_count"] == 2
        assert [u["stage"] for u in row["usage"]] == ["qualification", "qualification_repair"]
        assert [u["outcome"] for u in row["usage"]] == ["invalid_output", "success"]


@pytest.mark.parametrize("change,check", [("grounding", "evidence_grounding"), ("scoring", "scoring"),
    ("foreign", "foreign_profile_text"), ("price", "unsupported_amount"), ("prompt", "provenance")])
def test_same_acceptance_guards_apply_to_both_providers(provider, transport, monkeypatch, capsys, change, check):
    requests, _ = transport()
    production_analyze = matrix.analyze_agent
    def corrupted(inputs):
        result = production_analyze(inputs)
        if change == "grounding":
            result.qualification.evidence[0].quote = "invented source text"
        elif change == "scoring":
            result.scoring.score += 1
        elif change == "foreign":
            result.qualification.need = "LedgerFlow offers this course"
        elif change == "price":
            result.qualification.need = "The fee is $99"
        else:
            wrong = "qualify_real_v1" if provider[0] == "gemini" else "qualify_gemini_v1"
            result = result.model_copy(update={"prompt_version": wrong})
        return result
    monkeypatch.setattr(matrix, "analyze_agent", corrupted)
    assert matrix.main(["--provider", provider[0], "--json-only"]) == 2
    result = report(capsys, failed=True)
    assert result["failed_check"] == check and len(requests) == 1 and not result["results"]


@pytest.mark.parametrize("usage_case", ["known", "cached", "model_mismatch", "missing_tokens"])
@pytest.mark.parametrize("provider", ["avalai"], indirect=True)
def test_avalai_preserves_production_cost_and_usage(provider, transport, monkeypatch, capsys, usage_case):
    monkeypatch.setenv("OPENAI_INPUT_USD_PER_MILLION", "0.20")
    monkeypatch.setenv("OPENAI_OUTPUT_USD_PER_MILLION", "1.20")
    monkeypatch.setenv("OPENAI_PRICE_VERSION", "offline-test-rates")
    changes = {}
    if usage_case == "cached":
        changes["usage"] = dict(input_tokens=100, output_tokens=50, input_tokens_details=dict(cached_tokens=25))
    elif usage_case == "model_mismatch":
        changes["model"] = "another-reported-model"
    elif usage_case == "missing_tokens":
        changes["usage"] = None
    transport(body_changes=changes)
    assert matrix.main(["--provider", "avalai", "--json-only"]) == 0
    for row in report(capsys)["results"]:
        usage = row["usage"][0]
        if usage_case == "known":
            assert usage["cost_status"] == "known"
            assert Decimal(usage["estimated_cost"]) == Decimal("0.00008")
            assert usage["price_version"] == "offline-test-rates"
        else:
            assert usage["cost_status"] == "unknown" and usage["estimated_cost"] is None
        if usage_case == "model_mismatch":
            assert row["model"] == "another-reported-model"
        if usage_case == "missing_tokens":
            assert usage["input_tokens"] is None and usage["output_tokens"] is None
        assert usage["exact_account_charge"] is False


@pytest.mark.parametrize("provider", ["avalai"], indirect=True)
def test_avalai_cannot_be_mislabeled_openai_endpoint(provider, transport, monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    requests, _ = transport()
    assert matrix.main(["--provider", "avalai", "--json-only"]) == 2
    assert report(capsys, failed=True)["failed_check"] == "configuration" and not requests
