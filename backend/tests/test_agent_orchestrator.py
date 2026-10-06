"""Offline integration of the frozen Agent boundary and actual provider adapters."""
import json
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from app.agents import orchestrator
from app.agents.contracts import (
    AgentInput, AgentMetadata, AgentOutput, ContextMessage, Decision, EvidenceItem,
    MessageInput, ProductInput, ProductSnapshot, RunConfig, Signals, TargetMessage,
)
from app.agents.cost import PriceRates
from app.agents.pipeline import analyze as analyze_legacy
from app.agents.providers import factory
from app.agents.providers.base import ProviderError
from app.agents.providers.config import RealProviderConfig
from app.agents.providers.mock import MockProvider
from app.agents.providers.real import RealProvider
from app.agents.scoring import calculate_score, calculate_score_with_reason


@pytest.fixture(autouse=True)
def no_real_credentials(monkeypatch):
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL", "OPENAI_PRICE_VERSION",
                 "OPENAI_INPUT_USD_PER_MILLION", "OPENAI_OUTPUT_USD_PER_MILLION"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def inputs():
    timestamp = datetime(2026, 10, 6, tzinfo=timezone.utc)
    return AgentInput(product=ProductInput(id="product", name="Python course",
        description="Practical Python training", target_customer="Beginners"),
        message=MessageInput(id="target", content="I want to buy a Python course today.",
            author="Buyer", timestamp=timestamp, conversation_id="conversation",
            reply_to_message_id="context"),
        context_messages=[ContextMessage(id="context", content="This Python course is for beginners.",
            author="Another person", timestamp=timestamp)],
        metadata=AgentMetadata(run_id="run", provider_mode="real"))


@pytest.fixture
def qualification(inputs):
    return dict(intent="searching_for_course", need="Wants a Python course",
        purchase_intent=.9, product_fit=.9, need_strength=.8, urgency=.5,
        confidence=.9, response_opportunity=.8,
        evidence=[dict(message_id=inputs.message.id, quote=inputs.message.content,
                       reason="Explicit target request")], limitations=["Budget is unknown"])


def response(value, *, tokens=(101, 52)):
    body = dict(status="completed", model="offline-model", output=[dict(type="message",
        content=[dict(type="output_text", text=value if isinstance(value, str) else json.dumps(value))])])
    if tokens is not None:
        body["usage"] = dict(input_tokens=tokens[0], output_tokens=tokens[1],
                             input_tokens_details=dict(cached_tokens=0))
    return body


@pytest.fixture
def real_provider(monkeypatch):
    clients = []

    def create(responses, *, rates=None):
        pending = iter(responses)
        requests = []

        def transport(request):
            requests.append(request)
            value = next(pending)
            if isinstance(value, Exception):
                raise value
            return httpx.Response(200, json=value)

        client = httpx.Client(transport=httpx.MockTransport(transport))
        clients.append(client)
        monkeypatch.setenv("OPENAI_API_KEY", "fake-offline-key")
        provider = RealProvider(RealProviderConfig(model="offline-model", rates=rates), client=client)
        # Exercise the actual get_provider("real") branch with an injected client.
        monkeypatch.setattr(factory, "RealProvider", lambda: provider)
        return provider, requests

    yield create
    for client in clients:
        client.close()


def test_complete_real_flow_selects_real_provider_and_preserves_input(inputs, qualification, real_provider, monkeypatch):
    provider, requests = real_provider([response(qualification)])
    calls = []
    original_factory = orchestrator.get_provider

    def select(mode):
        calls.append(mode)
        return original_factory(mode)

    monkeypatch.setattr(orchestrator, "get_provider", select)
    before = inputs.model_dump(mode="json")
    output = orchestrator.analyze_agent(inputs)
    assert calls == ["real"] and len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer fake-offline-key"
    supplied = json.loads(json.loads(requests[0].content)["input"][-1]["content"])
    assert supplied["target"]["conversation_id"] == inputs.message.conversation_id
    assert supplied["target"]["reply_to_external_id"] == "context"
    assert [m["id"] for m in supplied["context"]] == ["context"]
    assert output.screening.is_candidate and output.qualification.model_dump() == qualification
    assert output.scoring.score == 84 and output.scoring.decision == Decision.RESPOND
    assert output.suggested_reply is None
    usage = output.usage[0]
    assert (usage.stage, usage.attempt_no, usage.provider_mode, usage.model, usage.outcome) == (
        "qualification", 1, "real", "offline-model", "success")
    assert (usage.input_tokens, usage.output_tokens) == (101, 52)
    assert usage.estimated_cost is None and usage.cost_status == "unknown"
    assert inputs.model_dump(mode="json") == before
    assert AgentOutput.model_validate_json(output.model_dump_json()) == output


def test_mock_selection_scores_once_and_keeps_mock_labels(inputs, monkeypatch):
    inputs.metadata.provider_mode = "mock"
    selected, scores = [], []
    original_factory = orchestrator.get_provider

    def select(mode):
        selected.append(mode)
        return original_factory(mode)

    def score_once(*args, **kwargs):
        scores.append((args, kwargs))
        return calculate_score_with_reason(*args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("The qualification-only flow must not call provider.analyze or construct RealProvider")

    monkeypatch.setattr(orchestrator, "get_provider", select)
    monkeypatch.setattr(orchestrator, "calculate_score_with_reason", score_once)
    monkeypatch.setattr(MockProvider, "analyze", forbidden)
    monkeypatch.setattr(factory, "RealProvider", forbidden)
    output = orchestrator.analyze_agent(inputs)
    assert selected == ["mock"] and len(scores) == 1
    assert output.scoring.score == 84 and output.scoring.decision == Decision.RESPOND
    assert output.usage[0].provider_mode == "mock" and output.usage[0].cost_status == "mock"
    assert output.usage[0].estimated_cost == Decimal("0")
    assert output.usage[0].input_tokens is None and output.usage[0].output_tokens is None
    assert any("Mock" in limitation for limitation in output.qualification.limitations)
    assert output.suggested_reply is None


@pytest.mark.parametrize("mode", ["real", "mock"])
def test_rejected_screening_does_not_construct_any_provider(inputs, mode, monkeypatch):
    inputs.metadata.provider_mode = mode
    inputs.message.content = "Hello!"
    inputs.context_messages = []
    monkeypatch.setattr(orchestrator, "get_provider", lambda mode: pytest.fail("No provider call for noise"))
    output = orchestrator.analyze_agent(inputs)
    assert not output.screening.is_candidate
    assert output.qualification is None and output.scoring is None and output.usage == []
    assert output.suggested_reply is None


def test_ambiguous_reply_uses_supplied_context(inputs, qualification, real_provider):
    inputs.message.content = "Yeah, but it's too expensive."
    qualification.update(intent="objection", need="Raises a price objection",
        evidence=[dict(message_id=inputs.message.id, quote=inputs.message.content, reason="Price objection"),
                  dict(message_id="context", quote=inputs.context_messages[0].content, reason="Product context")])
    _, requests = real_provider([response(qualification)])
    output = orchestrator.analyze_agent(inputs)
    assert output.screening.reason == "conversation_dependency"
    assert output.qualification.intent == "objection" and len(requests) == 1
    assert {e.message_id for e in output.qualification.evidence} == {"target", "context"}


@pytest.mark.parametrize("value,score,decision", [(0, 0, Decision.IGNORE),
    (.39, 39, Decision.IGNORE), (.4, 40, Decision.REVIEW), (.69, 69, Decision.REVIEW),
    (.7, 70, Decision.RESPOND), (1, 100, Decision.RESPOND)])
def test_real_signal_thresholds_are_scored_by_existing_engine(value, score, decision, inputs, qualification, real_provider):
    qualification.update({name: value for name in Signals.model_fields})
    real_provider([response(qualification)])
    output = orchestrator.analyze_agent(inputs)
    assert output.scoring.score == score and output.scoring.decision == decision


@pytest.mark.parametrize("kind", ["low_confidence", "low_fit", "missing_evidence", "context_only", "guard_boundaries"])
def test_scoring_guards(kind, inputs, qualification, real_provider):
    qualification.update({name: 1 for name in Signals.model_fields})
    if kind == "low_confidence":
        qualification["confidence"] = .59
    elif kind == "low_fit":
        qualification["product_fit"] = .49
    elif kind == "missing_evidence":
        qualification["evidence"] = []
    elif kind == "context_only":
        qualification["evidence"] = [dict(message_id="context", quote=inputs.context_messages[0].content, reason="Context")]
    else:
        qualification.update(confidence=.60, product_fit=.50)
    real_provider([response(qualification)])
    output = orchestrator.analyze_agent(inputs)
    assert 70 <= output.scoring.score <= 100
    assert output.scoring.decision == (Decision.RESPOND if kind == "guard_boundaries" else Decision.REVIEW)


@pytest.mark.parametrize("kind", ["invented_quote", "unknown_id", "wrong_source", "whitespace"])
def test_orchestrator_revalidates_evidence_even_after_provider_validation(kind, inputs, qualification, real_provider, monkeypatch):
    provider, _ = real_provider([response(qualification)])
    original = provider.qualify_structured

    def corrupt(*args):
        result, usage = original(*args)
        source = result.evidence[0]
        changes = {"invented_quote": {"quote": "Fabricated purchase"}, "unknown_id": {"message_id": "foreign"},
                   "wrong_source": {"message_id": "context"}, "whitespace": {"quote": " "}}[kind]
        return result.model_copy(update={"evidence": [source.model_copy(update=changes)]}), usage

    monkeypatch.setattr(provider, "qualify_structured", corrupt)
    monkeypatch.setattr(orchestrator, "calculate_score_with_reason", lambda *args, **kwargs: pytest.fail("Invalid evidence must not be scored"))
    with pytest.raises(ProviderError, match="not grounded") as exc:
        orchestrator.analyze_agent(inputs)
    assert len(exc.value.usage) == 1 and exc.value.usage[0].input_tokens == 101


@pytest.mark.parametrize("kind", ["duplicate", "target"])
@pytest.mark.parametrize("noise", [False, True])
def test_invalid_context_rejected_before_screening_or_provider(kind, noise, inputs, monkeypatch):
    if noise:
        inputs.message.content = "Hello!"
    if kind == "duplicate":
        inputs.context_messages.append(inputs.context_messages[0])
    else:
        inputs.context_messages[0].id = inputs.message.id
    monkeypatch.setattr(orchestrator, "get_provider", lambda mode: pytest.fail("Invalid context must not reach provider"))
    with pytest.raises(ValueError, match="unique" if kind == "duplicate" else "exclude"):
        orchestrator.analyze_agent(inputs)


@pytest.mark.parametrize("kind", ["empty_content", "naive_timestamp", "unsupported_mode", "too_much_context"])
def test_input_models_are_revalidated_before_any_provider_call(kind, inputs, monkeypatch):
    if kind == "empty_content":
        inputs.message.content = ""
    elif kind == "naive_timestamp":
        inputs.message.timestamp = inputs.message.timestamp.replace(tzinfo=None)
    elif kind == "unsupported_mode":
        inputs.metadata.provider_mode = "unsupported"
    else:
        inputs.context_messages *= 6
    monkeypatch.setattr(orchestrator, "get_provider", lambda mode: pytest.fail("Invalid input must not reach provider"))
    with pytest.raises(ValidationError):
        orchestrator.analyze_agent(inputs)


def test_missing_real_configuration_never_falls_back_to_mock(inputs, monkeypatch):
    monkeypatch.setattr(factory, "MockProvider", lambda: pytest.fail("No fallback to Mock"))
    with pytest.raises(ProviderError, match="not configured") as exc:
        orchestrator.analyze_agent(inputs)
    assert exc.value.usage == []


def test_orchestrator_checks_factory_mode(inputs, monkeypatch):
    monkeypatch.setattr(orchestrator, "get_provider", lambda mode: MockProvider())
    with pytest.raises(ProviderError, match="does not match") as exc:
        orchestrator.analyze_agent(inputs)
    assert exc.value.usage == []


def test_repair_history_is_preserved_in_complete_output(inputs, qualification, real_provider):
    real_provider([response("malformed"), response(qualification, tokens=(203, 81))])
    output = orchestrator.analyze_agent(inputs)
    assert [(r.stage, r.attempt_no, r.outcome, r.input_tokens, r.output_tokens) for r in output.usage] == [
        ("qualification", 1, "invalid_output", 101, 52),
        ("qualification_repair", 2, "success", 203, 81)]
    assert output.scoring.score == 84


def test_failed_repair_propagates_actual_usage_without_result(inputs, real_provider):
    _, requests = real_provider([response("bad"), response("still bad", tokens=(203, 81))])
    with pytest.raises(ProviderError, match="after one repair") as exc:
        orchestrator.analyze_agent(inputs)
    assert len(requests) == len(exc.value.usage) == 2
    assert [r.input_tokens for r in exc.value.usage] == [101, 203]
    assert all(r.provider_mode == "real" and r.estimated_cost is None for r in exc.value.usage)


def test_timeout_propagates_with_preserved_history_and_no_fake_success(inputs, real_provider):
    real_provider([response("bad"), httpx.ReadTimeout("fake-offline-key")])
    with pytest.raises(ProviderError, match="timed out") as exc:
        orchestrator.analyze_agent(inputs)
    assert [r.outcome for r in exc.value.usage] == ["invalid_output", "timeout"]
    assert exc.value.usage[1].input_tokens is None and exc.value.usage[1].estimated_cost is None
    assert "fake-offline-key" not in str(exc.value)


@pytest.mark.parametrize("field,value", [("score", 100), ("decision", "RESPOND")])
def test_llm_score_and_decision_are_rejected(inputs, qualification, field, value, real_provider):
    qualification[field] = value
    _, requests = real_provider([response(qualification)] * 2)
    with pytest.raises(ProviderError):
        orchestrator.analyze_agent(inputs)
    assert len(requests) == 2


def test_unknown_tokens_and_cost_remain_unknown(inputs, qualification, real_provider):
    real_provider([response(qualification, tokens=None)])
    record = orchestrator.analyze_agent(inputs).usage[0]
    assert record.input_tokens is None and record.output_tokens is None
    assert record.estimated_cost is None and record.cost_status == "unknown"


def test_orchestrator_preserves_provider_cost_estimates_for_each_attempt(inputs, qualification, real_provider):
    rates = PriceRates(model="offline-model", version="offline-prices-v1",
        input_usd_per_million=Decimal("2"), output_usd_per_million=Decimal("8"))
    real_provider([response("bad"), response(qualification, tokens=(203, 81))], rates=rates)
    records = orchestrator.analyze_agent(inputs).usage
    assert [r.estimated_cost for r in records] == [Decimal(".000618"), Decimal(".001054")]
    assert all(r.cost_status == "known" and r.price_version == "offline-prices-v1" for r in records)


def test_mutated_qualification_cannot_bypass_validation(inputs, qualification, real_provider, monkeypatch):
    provider, _ = real_provider([response(qualification)])
    original = provider.qualify_structured

    def corrupt(*args):
        result, records = original(*args)
        return result.model_copy(update={"purchase_intent": 2}), records

    monkeypatch.setattr(provider, "qualify_structured", corrupt)
    with pytest.raises(ProviderError, match="invalid structured qualification") as exc:
        orchestrator.analyze_agent(inputs)
    assert len(exc.value.usage) == 1


def test_usage_mode_cannot_be_relabeled_as_real(inputs, qualification, real_provider, monkeypatch):
    provider, _ = real_provider([response(qualification)])
    original = provider.qualify_structured

    def corrupt(*args):
        result, records = original(*args)
        return result, [records[0].model_copy(update={"provider_mode": "mock"})]

    monkeypatch.setattr(provider, "qualify_structured", corrupt)
    with pytest.raises(ProviderError, match="usage mode"):
        orchestrator.analyze_agent(inputs)


def test_legacy_pipeline_and_public_orchestrator_agree_for_mock(inputs):
    inputs.metadata.provider_mode = "mock"
    output = orchestrator.analyze_agent(inputs)
    product = ProductSnapshot(**inputs.product.model_dump(exclude={"id"}))
    m = inputs.message
    target = TargetMessage(id=m.id, external_id=m.id, content=m.content, author=m.author,
        timestamp=m.timestamp, conversation_id=m.conversation_id, reply_to_external_id=m.reply_to_message_id)
    context = [TargetMessage(id=c.id, external_id=c.id, content=c.content, author=c.author,
        timestamp=c.timestamp, conversation_id=m.conversation_id) for c in inputs.context_messages]
    legacy, usage = analyze_legacy(product, target, [*context, target], RunConfig(), MockProvider())
    assert legacy.lead_score == output.scoring.score
    assert legacy.decision == output.scoring.decision.value.lower()
    assert legacy.signals.model_dump() == {name: getattr(output.qualification, name) for name in Signals.model_fields}
    assert usage[0].cost_status == output.usage[0].cost_status == "mock"
    assert usage[0].input_tokens == output.usage[0].input_tokens is None
    assert output == orchestrator.analyze_agent(inputs)


def test_frozen_schema_and_output_fields_are_preserved(inputs, qualification, real_provider):
    input_schema = AgentInput.model_json_schema()
    output_schema = AgentOutput.model_json_schema()
    assert set(input_schema["properties"]) == {"product", "message", "context_messages", "metadata"}
    assert set(output_schema["properties"]) == {"screening", "qualification", "scoring", "usage", "suggested_reply",
                                               "decision_reason", "prompt_version", "scoring_version"}
    assert input_schema["properties"]["context_messages"]["maxItems"] == 5
    assert output_schema["properties"]["usage"]["type"] == "array"
    assert all(schema.get("additionalProperties") is False for schema in [
        input_schema, output_schema, *input_schema["$defs"].values(), *output_schema["$defs"].values()]
        if schema.get("type") == "object")
    real_provider([response(qualification)])
    output = orchestrator.analyze_agent(inputs)
    assert AgentInput.model_json_schema() == input_schema and AgentOutput.model_json_schema() == output_schema
    assert set(output.model_dump()) == set(output_schema["properties"])
    assert output.suggested_reply is None
    payload = deepcopy(inputs.model_dump())
    payload["unexpected"] = "forbidden"
    with pytest.raises(ValidationError):
        orchestrator.analyze_agent(payload)
