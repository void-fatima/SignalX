from datetime import datetime, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.agents.contracts import (
    AgentInput, AgentMetadata, AgentOutput, MessageInput, ProductInput,
    QualificationResult, ScreeningResult, Signals, UsageInfo,
)
from app.agents.providers.mock import MockProvider
from app.agents.scoring import score


SIGNAL_NAMES = tuple(Signals.model_fields)


@pytest.mark.parametrize("field", SIGNAL_NAMES)
@pytest.mark.parametrize("invalid", [-.1, 1.1, float("nan"), float("inf")])
def test_all_public_scoring_signals_are_bounded_and_finite(field, invalid):
    values = dict.fromkeys(SIGNAL_NAMES, .5)
    values[field] = invalid
    with pytest.raises(ValidationError):
        QualificationResult(intent="demo", need="demo", **values)


def test_unknown_usage_and_per_attempt_history_roundtrip():
    unknown = UsageInfo(stage="qualification", provider_mode="real", outcome="error")
    assert unknown.estimated_cost is None and unknown.cost_status == "unknown"
    assert unknown.model is None and unknown.latency_ms is None
    records = [unknown, unknown.model_copy(update={"attempt_no": 2}),
               UsageInfo(stage="repair", provider_mode="real"),
               UsageInfo(stage="suggested_reply", provider_mode="real")]
    output = AgentOutput(screening=ScreeningResult(is_candidate=True, reason="demo"), usage=records)
    assert AgentOutput.model_validate_json(output.model_dump_json()) == output
    first = AgentOutput(screening=output.screening)
    second = AgentOutput(screening=output.screening)
    first.usage.append(unknown)
    assert second.usage == []


def test_cost_status_does_not_misrepresent_unknown_or_mock_cost():
    for values in [{"estimated_cost": "0"}, {"cost_status": "known"},
                   {"cost_status": "mock", "estimated_cost": "0"}]:
        with pytest.raises(ValidationError):
            UsageInfo(stage="qualification", provider_mode="real", **values)
    for values in [{"attempt_no": 0}, {"latency_ms": -1}, {"input_tokens": -1}]:
        with pytest.raises(ValidationError):
            UsageInfo(stage="qualification", provider_mode="real", **values)


def test_screening_result_rejects_extra_fields():
    with pytest.raises(ValidationError):
        ScreeningResult(is_candidate=True, reason="demo", unexpected="ignored?")


def test_mock_maps_all_signals_and_usage_without_changing_deterministic_score():
    inputs = AgentInput(product=ProductInput(id="p1", name="Backend course",
        description="Project-based backend course", target_customer="Developers"),
        message=MessageInput(id="m1", content="Looking for a backend course", author="Demo",
            timestamp=datetime(2026, 10, 5, tzinfo=timezone.utc), conversation_id="c1"),
        metadata=AgentMetadata(run_id="r1", provider_mode="mock"))
    provider = MockProvider()
    output = provider.analyze(inputs)
    assert output == provider.analyze(inputs)
    assert output.qualification is not None and output.scoring is not None
    signals = Signals(**{name: getattr(output.qualification, name) for name in SIGNAL_NAMES})
    assert output.scoring.score == score(signals)[0] == 84
    assert "score" not in QualificationResult.model_fields
    assert len(output.usage) == 1
    usage = output.usage[0]
    assert usage.stage == "qualification" and usage.attempt_no == 1
    assert usage.provider_mode == "mock" and usage.model == "deterministic-mock-v1"
    assert usage.input_tokens is None and usage.output_tokens is None
    assert usage.estimated_cost == Decimal("0") and usage.cost_status == "mock"
    assert usage.price_version == "mock_v1" and usage.outcome == "success"
    noise = inputs.model_copy(update={"message": inputs.message.model_copy(update={"content": "Coffee today?"})})
    assert provider.analyze(noise).usage == []
