from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.agents.cost import PriceRates, calculate_cost, cost_per
from app.agents.evaluation import Label, Prediction, evaluate, validate_split


def rates():
    # Fictional unit-test rates, not a provider pricing claim.
    return PriceRates(model="unit-test", version="test_rates_v1", input_usd_per_million="2", output_usd_per_million="6")


def test_cost_decimal_and_unknown():
    known = calculate_cost("real", 1000, 500, rates())
    assert known.cost_usd == Decimal("0.005")
    assert known.price_version == "test_rates_v1"
    assert cost_per([known], 2) == Decimal("0.0025")
    unknown = calculate_cost("real", None, 500, rates())
    assert unknown.cost_usd is None and unknown.cost_status == "unknown"
    assert calculate_cost("real", 1000, 500, None).cost_usd is None
    assert cost_per([known, unknown], 2) is None
    assert cost_per([known], 0) is None
    mock = calculate_cost("mock", None, None, None)
    assert mock.cost_usd == 0 and mock.cost_status == "mock"
    with pytest.raises(ValueError, match="separately"):
        cost_per([known, mock], 2)


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_invalid_token_counts(value):
    with pytest.raises(ValueError):
        calculate_cost("real", value, 100, rates())


def test_invalid_rates():
    for value in ["-1", "NaN", "Infinity"]:
        with pytest.raises(ValidationError):
            PriceRates(model="test", version="test", input_usd_per_million=value, output_usd_per_million="1")


def label(id, relevant, conversation=None):
    return Label(external_id=str(id), conversation_id=conversation or str(id), relevant=relevant)


def prediction(id, decision, candidate=True, status="completed"):
    return Prediction(external_id=str(id), decision=decision, is_candidate=candidate, status=status)


def test_evaluation_includes_screened_out_and_failed():
    labels = [label(1, True), label(2, False), label(3, True), label(4, True), label(5, False)]
    predictions = [prediction(1, "respond"), prediction(2, "respond"), prediction(3, "ignore", False),
                   prediction(4, None, None, "failed"), prediction(5, "review")]
    report = evaluate(labels, predictions)
    assert (report.n, report.tp, report.fp, report.fn, report.tn) == (5, 1, 1, 2, 1)
    assert report.precision == .5 and report.recall == 1 / 3
    assert report.failed_count == 1 and report.unknown_screening_count == 1
    assert report.screening_recall is None
    assert evaluate([label(1, False)], [prediction(1, "ignore", False)]).precision is None


def test_evaluation_rejects_cherry_picking_and_split_leakage():
    labels = [label(1, True), label(2, False)]
    with pytest.raises(ValueError, match="all labeled"):
        evaluate(labels, [prediction(1, "respond")])
    with pytest.raises(ValueError, match="Duplicate"):
        evaluate(labels, [prediction(1, "respond"), prediction(1, "ignore")])
    with pytest.raises(ValueError, match="overlap"):
        validate_split([label(1, True, "same")], [label(2, False, "same")])


def test_screening_recall_and_invalid_decision():
    report = evaluate([label(1, True), label(2, True)], [prediction(1, "respond"), prediction(2, "ignore", False)])
    assert report.screening_recall == .5
    with pytest.raises(ValueError, match="Failed"):
        evaluate([label(1, True)], [prediction(1, "respond", status="failed")])
