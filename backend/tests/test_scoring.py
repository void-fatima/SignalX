from itertools import product

import pytest
from pydantic import ValidationError

from app.agents.contracts import Decision, QualificationResult, Signals
from app.agents.scoring import SCORING_VERSION, calculate_score, score


def signals(value=1.0, **overrides):
    return Signals(**{**dict.fromkeys(Signals.model_fields, value), **overrides})


@pytest.mark.parametrize("value, expected_score, decision", [
    (0.0, 0, Decision.IGNORE),
    (.001, 0, Decision.IGNORE),
    (.01, 1, Decision.IGNORE),
    (.39, 39, Decision.IGNORE),
    (.40, 40, Decision.REVIEW),
    (.69, 69, Decision.REVIEW),
    (.70, 70, Decision.RESPOND),
    (.999, 100, Decision.RESPOND),
    (1.0, 100, Decision.RESPOND),
])
def test_extremes_and_thresholds(value, expected_score, decision):
    result = calculate_score(signals(value), valid_purchase_evidence=True)
    assert result.score == expected_score
    assert result.decision == decision


@pytest.mark.parametrize("purchase_intent,expected_score,decision", [
    (.0, 39, Decision.IGNORE),   # Fixed other contributions total 39.
    (.02, 40, Decision.REVIEW), # 39.6 rounds up before threshold selection.
])
def test_rounding_before_threshold(purchase_intent, expected_score, decision):
    result = calculate_score(signals(0, purchase_intent=purchase_intent,
        product_fit=1, confidence=.9), valid_purchase_evidence=True)
    assert result.score == expected_score and result.decision == decision


def test_exact_half_ties_use_python_round_not_half_up():
    # 30 + 15 + 10 + 10 + 5 + 7.5 = 77.5 -> 78.
    assert calculate_score(signals(product_fit=.25), True).score == 78
    # 30 + 15 + 10 + 10 + 5 + 22.5 = 92.5 -> 92, not 93.
    assert calculate_score(signals(product_fit=.75), True).score == 92
    assert calculate_score(signals(0, confidence=1, response_opportunity=.5), True).score == 12


def test_formula_uses_each_signal_with_its_exact_weight():
    expected_weights = {"purchase_intent": 30, "product_fit": 30, "need_strength": 15,
                        "urgency": 10, "confidence": 10, "response_opportunity": 5}
    for name, weight in expected_weights.items():
        assert calculate_score(signals(0, **{name: 1}), True).score == weight
    sample = signals(0, purchase_intent=.9, product_fit=.9, need_strength=.8,
                     urgency=.5, confidence=.9, response_opportunity=.8)
    assert calculate_score(sample, True).score == 84
    assert SCORING_VERSION == "score_v1"


@pytest.mark.parametrize("overrides,evidence,reason", [
    ({"confidence": .59}, True, "low_confidence"),
    ({"product_fit": .49}, True, "low_product_fit"),
    ({}, False, "invalid_purchase_evidence"),
    ({}, None, "invalid_purchase_evidence"),
])
def test_guards_preserve_numeric_score_and_downgrade(overrides, evidence, reason):
    data = signals(**overrides)
    result = calculate_score(data, evidence)
    assert result.score >= 70 and result.decision == Decision.REVIEW
    assert score(data, evidence) == (result.score, "review", reason)


def test_missing_evidence_defaults_to_review_and_guard_boundaries_are_inclusive():
    assert calculate_score(signals()).decision == Decision.REVIEW
    assert calculate_score(signals(confidence=.60), True).decision == Decision.RESPOND
    assert calculate_score(signals(product_fit=.50), True).decision == Decision.RESPOND
    assert calculate_score(signals(0), None).decision == Decision.IGNORE
    assert calculate_score(signals(.5), False).decision == Decision.REVIEW
    assert calculate_score(signals(), True, needs_human_review=True).decision == Decision.REVIEW


def test_frozen_qualification_contract_and_legacy_interface_are_supported():
    qualification = QualificationResult(intent="demo", need="demo", **signals().model_dump())
    assert calculate_score(qualification, True) == calculate_score(signals(), True)
    assert score(signals(), True) == (100, "respond", "score_threshold_met")
    # Preserve the legacy trusted-evidence default without using it in new code.
    assert score(signals()) == (100, "respond", "score_threshold_met")


def test_repeated_execution_is_identical_and_does_not_mutate_input():
    data = signals(purchase_intent=.9, product_fit=.8, need_strength=.7, urgency=.2)
    before = data.model_dump()
    expected = calculate_score(data, True)
    for _ in range(100):
        assert calculate_score(data, True) == expected
    assert data.model_dump() == before


def test_scores_always_within_range_across_signal_combinations():
    # Exhaust all 3^6 combinations at endpoints/midpoints, rather than random data.
    for values in product((0.0, .5, 1.0), repeat=6):
        data = Signals(**dict(zip(Signals.model_fields, values)))
        result = calculate_score(data, True)
        assert type(result.score) is int and 0 <= result.score <= 100
        if result.decision == Decision.RESPOND:
            assert result.score >= 70 and data.confidence >= .60 and data.product_fit >= .50


@pytest.mark.parametrize("invalid", [-.01, 1.01, float("nan"), float("inf")])
def test_invalid_mutated_signals_are_rejected(invalid):
    with pytest.raises(ValidationError):
        calculate_score(signals().model_copy(update={"purchase_intent": invalid}), True)
