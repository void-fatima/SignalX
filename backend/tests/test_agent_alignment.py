"""Step 9 contract/metadata regressions through production entry points, offline."""
import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from app.agents import orchestrator, reply, scoring
from app.agents.contracts import AgentInput, AgentOutput, Decision, Signals
from app.agents.cost import PriceRates
from app.agents.prompts.qualification import PROMPT_VERSION, output_schema
from app.agents.providers import factory
from app.agents.providers.config import RealProviderConfig
from app.agents.providers.mock import MockProvider
from app.agents.providers.real import RealProvider
from app.agents.qualification import validate_qualification_result
from app.agents.screening import screen


FIXTURE_PATH = Path(__file__).parents[1] / "app/agents/fixtures/backend_integration.json"


@pytest.fixture
def examples():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["examples"]


@pytest.fixture
def run_real(monkeypatch):
    """No external requests are possible through these injected HTTP clients."""
    clients = []
    monkeypatch.setenv("OPENAI_API_KEY", "fake-offline-alignment-key")
    rates = PriceRates(model="gpt-5.6-luna", version="fixture-rates-v1",
        input_usd_per_million=Decimal("0.20"), output_usd_per_million=Decimal("1.20"))

    def create(payloads):
        pending = iter(payloads)
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(200, json=next(pending))

        client = httpx.Client(transport=httpx.MockTransport(handle))
        clients.append(client)
        provider = RealProvider(RealProviderConfig(model="gpt-5.6-luna", rates=rates), client=client)
        monkeypatch.setattr(factory, "RealProvider", lambda: provider)
        monkeypatch.setattr(factory, "MockProvider", lambda: pytest.fail("No real-to-Mock fallback"))
        return provider, requests

    yield create
    for client in clients:
        client.close()


def envelope(payload, usage):
    return dict(status="completed", model="gpt-5.6-luna", usage=usage,
        output=[dict(type="message", content=[dict(type="output_text", text=json.dumps(payload))])])


def test_shared_fixture_has_persistable_ids_and_distinct_analysis_runs(examples):
    run_ids = []
    for example in examples:
        inputs = AgentInput.model_validate(example["agent_input"])
        run_ids.append(inputs.metadata.run_id)
        ids = [inputs.product.id, inputs.message.id, inputs.metadata.run_id,
               *[message.id for message in inputs.context_messages]]
        assert all(str(UUID(value)) == value for value in ids)
        if inputs.message.reply_to_message_id is not None:
            assert inputs.message.reply_to_message_id in {m.id for m in inputs.context_messages}
    assert len(set(run_ids)) == len(run_ids)


def test_old_outputs_and_input_shape_remain_compatible(examples):
    for example in examples:
        original = deepcopy(example["analysis"])
        for name in ("decision_reason", "prompt_version", "scoring_version"):
            original.pop(name)
        output = AgentOutput.model_validate(original)
        assert output.decision_reason is output.prompt_version is output.scoring_version is None
        assert AgentOutput.model_validate_json(output.model_dump_json()) == output
    assert set(AgentInput.model_fields) == {"product", "message", "context_messages", "metadata"}
    schema = AgentOutput.model_json_schema()
    assert schema["required"] == ["screening"]
    assert schema["additionalProperties"] is False
    for name in ("decision_reason", "prompt_version", "scoring_version"):
        assert schema["properties"][name]["default"] is None


@pytest.mark.parametrize("field", ["screening", "qualification", "scoring", "usage", "suggested_reply",
                                  "decision_reason", "prompt_version", "scoring_version"])
def test_agent_output_fields_are_frozen(field, examples):
    output = AgentOutput.model_validate(examples[0]["analysis"])
    assert output.model_config["frozen"] is True
    with pytest.raises(ValidationError) as error:
        setattr(output, field, getattr(output, field))
    assert error.value.errors()[0]["type"] == "frozen_instance"


@pytest.mark.parametrize("field", ["decision_reason", "prompt_version", "scoring_version"])
def test_new_optional_string_fields_roundtrip_and_reject_wrong_types(field, examples):
    payload = deepcopy(examples[0]["analysis"])
    payload[field] = "explicit-metadata"
    output = AgentOutput.model_validate(payload)
    assert getattr(output, field) == "explicit-metadata"
    assert AgentOutput.model_validate_json(output.model_dump_json()) == output
    payload[field] = 100
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(payload)


@pytest.mark.parametrize("value,overrides,evidence,human_review,decision,fragment", [
    (.39, {}, True, False, Decision.IGNORE, "below 40"),
    (.4, {}, True, False, Decision.REVIEW, "REVIEW band"),
    (.69, {}, True, False, Decision.REVIEW, "REVIEW band"),
    (.7, {}, True, False, Decision.RESPOND, "qualifies for RESPOND"),
    (1., {"confidence": .59}, True, False, Decision.REVIEW, "Confidence guard"),
    (1., {"product_fit": .49}, True, False, Decision.REVIEW, "Product-fit guard"),
    (1., {}, False, False, Decision.REVIEW, "Purchase-evidence guard"),
    (1., {}, None, False, Decision.REVIEW, "Purchase-evidence guard"),
    (1., {}, True, True, Decision.REVIEW, "Human-review guard"),
    (1., {"confidence": .59, "product_fit": .49}, False, True, Decision.REVIEW, "Confidence guard"),
    (.1, {"confidence": .1}, False, True, Decision.IGNORE, "below 40"),
])
def test_reason_uses_actual_threshold_and_first_applicable_guard(
        value, overrides, evidence, human_review, decision, fragment):
    signals = Signals(**(dict.fromkeys(Signals.model_fields, value) | overrides))
    result, reason = scoring.calculate_score_with_reason(signals, evidence, human_review)
    assert result.decision == decision and fragment in reason
    assert (result.score, decision.value.lower()) == scoring.score(signals, evidence, human_review)[:2]
    assert result == scoring.calculate_score(signals, evidence, human_review)
    for _ in range(5):
        assert (result, reason) == scoring.calculate_score_with_reason(signals, evidence, human_review)


@pytest.mark.parametrize("index", [0, 1, 2])
def test_shared_fixture_matches_production_flow(index, examples, run_real, monkeypatch):
    example = examples[index]
    inputs = AgentInput.model_validate(example["agent_input"])
    expected = AgentOutput.model_validate(example["analysis"])
    before = inputs.model_dump(mode="json")
    if expected.scoring is None:
        monkeypatch.setattr(orchestrator, "get_provider", lambda _: pytest.fail("No prompt for screening-only"))
        output = orchestrator.analyze_agent(inputs)
        assert output == expected and output.prompt_version is output.scoring_version is None
        assert "Screening rejected" in output.decision_reason
    else:
        body = envelope(example["analysis"]["qualification"], example["provider_usage_inputs"][0])
        provider, requests = run_real([body])
        executions = []
        original_score = scoring._score

        def execute(*args):
            executions.append(args)
            return original_score(*args)

        monkeypatch.setattr(scoring, "_score", execute)
        output = orchestrator.analyze_agent(inputs)
        assert len(requests) == len(executions) == 1
        assert output.scoring == expected.scoring and output.decision_reason == expected.decision_reason
        assert output.prompt_version == provider.prompt_version == PROMPT_VERSION
        assert output.scoring_version == scoring.SCORING_VERSION == "score_v1"
        assert output.qualification == expected.qualification
        assert output.usage[0].model_dump(exclude={"latency_ms"}) == expected.usage[0].model_dump(exclude={"latency_ms"})
        assert output.usage[0].latency_ms >= 0
        assert output.usage[0].estimated_cost is None and output.usage[0].cost_status == "unknown"
        _, product, target, context = orchestrator._prepare_input(inputs)
        _, valid = validate_qualification_result(output.qualification, target, context, output.usage)
        assert scoring.calculate_score(output.qualification, valid) == output.scoring
        assert output.screening == screen(product, target, context)
    assert inputs.model_dump(mode="json") == before
    assert output.suggested_reply is None
    assert AgentOutput.model_validate_json(output.model_dump_json()) == output


@pytest.mark.parametrize("kind", ["product_fit", "context_only", "empty_evidence"])
def test_real_orchestration_reports_guard_instead_of_threshold(kind, examples, run_real):
    example = examples[0]
    payload = deepcopy(example["analysis"]["qualification"])
    payload.update(dict.fromkeys(Signals.model_fields, 1.))
    if kind == "product_fit":
        payload["product_fit"] = .49
        fragment = "Product-fit guard"
    else:
        context = example["agent_input"]["context_messages"][0]
        payload["evidence"] = [] if kind == "empty_evidence" else [dict(
            message_id=context["id"], quote=context["content"], reason="Product conversation context")]
        fragment = "Purchase-evidence guard"
    _, requests = run_real([envelope(payload, example["provider_usage_inputs"][0])])
    output = orchestrator.analyze_agent(AgentInput.model_validate(example["agent_input"]))
    assert output.scoring.score >= 70 and output.scoring.decision == Decision.REVIEW
    assert fragment in output.decision_reason and len(requests) == 1


def test_mock_scored_outputs_have_no_real_prompt_claim(examples, monkeypatch):
    inputs = AgentInput.model_validate(examples[0]["agent_input"])
    inputs.metadata.provider_mode = "mock"
    monkeypatch.setattr(MockProvider, "prompt_version", "not-used", raising=False)
    for output in (orchestrator.analyze_agent(inputs), MockProvider().analyze(inputs)):
        assert output.prompt_version is None
        assert output.scoring_version == "score_v1" and output.decision_reason
        assert output.usage[0].provider_mode == "mock"


def test_real_provider_unscored_boundary_only_claims_prompt(examples, run_real):
    example = examples[0]
    provider, _ = run_real([envelope(example["analysis"]["qualification"], example["provider_usage_inputs"][0])])
    output = provider.analyze(AgentInput.model_validate(example["agent_input"]))
    assert output.prompt_version == PROMPT_VERSION
    assert output.scoring is output.scoring_version is output.decision_reason is None
    assert {"decision_reason", "prompt_version", "scoring_version"}.isdisjoint(output_schema()["properties"])


@pytest.mark.parametrize("details", ["absent", None, {}, {"cached_tokens": None}, {"cached_tokens": 10},
                                    {"cached_tokens": False}, {"cached_tokens": "0"}, {"cached_tokens": 0}])
@pytest.mark.parametrize("stage", ["qualification", "suggested_reply"])
def test_cache_metadata_controls_pricing_without_changing_tokens(details, stage, run_real):
    provider, requests = run_real([])
    usage = dict(input_tokens=100, output_tokens=50)
    if details != "absent":
        usage["input_tokens_details"] = details
    record = provider._usage(dict(model="gpt-5.6-luna", usage=usage), 1, 0, stage)
    assert record.input_tokens == 100 and record.output_tokens == 50 and record.stage == stage
    if details == {"cached_tokens": 0} and type(details["cached_tokens"]) is int:
        assert record.cost_status == "known" and record.estimated_cost == Decimal("0.00008")
    else:
        assert record.cost_status == "unknown" and record.estimated_cost is None
    assert requests == []


def test_repair_and_reply_preserve_qualification_metadata_and_all_usage(examples, run_real):
    example = examples[0]
    usage = example["provider_usage_inputs"][0]
    qualification = example["analysis"]["qualification"]
    provider, requests = run_real([
        envelope({"score": 100, "decision_reason": "LLM cannot decide"}, usage),
        envelope(qualification, usage),
        envelope(dict(parts=[dict(kind="question", text="What would you like to learn?", product_field=None)]), usage),
    ])
    inputs = AgentInput.model_validate(example["agent_input"])
    analysis = orchestrator.analyze_agent(inputs)
    assert len(requests) == 2 and len(analysis.usage) == 2
    assert analysis.prompt_version == provider.prompt_version
    before = analysis.model_dump(mode="json")
    updated = reply.generate_suggested_reply(inputs, analysis)
    assert len(requests) == 3 and updated.usage[:2] == analysis.usage
    assert updated.usage[-1].stage == "suggested_reply"
    for name in ("qualification", "scoring", "decision_reason", "prompt_version", "scoring_version"):
        assert getattr(updated, name) == getattr(analysis, name)
    assert analysis.model_dump(mode="json") == before and analysis.suggested_reply is None
