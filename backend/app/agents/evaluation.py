"""Offline evaluation only; labels never enter Agent/provider input."""
from typing import Literal
from pydantic import BaseModel, Field


class Label(BaseModel):
    external_id: str
    conversation_id: str
    relevant: bool


class Prediction(BaseModel):
    external_id: str
    decision: Literal["ignore", "review", "respond"] | None
    is_candidate: bool | None
    status: Literal["completed", "failed"]


class EvaluationReport(BaseModel):
    n: int
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float | None
    recall: float | None
    screening_recall: float | None
    failed_count: int
    unknown_screening_count: int
    positive_decisions: list[str] = Field(default_factory=lambda: ["respond"])
    confusion_matrix: dict[str, int] = Field(default_factory=dict)
    false_positive_ids: list[str] = Field(default_factory=list)
    false_negative_ids: list[str] = Field(default_factory=list)
    screening_false_negative_ids: list[str] = Field(default_factory=list)
    unknown_positive_screening_count: int = 0
    decision_breakdown: dict[str, int] = Field(default_factory=dict)
    review_coverage: float | None = None
    positive_review_coverage: float | None = None


def validate_split(dev: list[Label], test: list[Label]) -> None:
    if {l.conversation_id for l in dev} & {l.conversation_id for l in test}:
        raise ValueError("Development and test conversations overlap")


def evaluate(labels: list[Label], predictions: list[Prediction], *,
             positive_decisions: tuple[str, ...] = ("respond",)) -> EvaluationReport:
    """Legacy RESPOND metric by default; discovery explicitly counts REVIEW too.

    All labeled rows, including screened-out and failed rows, are required.
    No thresholds are tuned here. Undefined denominators stay null.
    """
    if (not positive_decisions or len(set(positive_decisions)) != len(positive_decisions)
            or set(positive_decisions) - {"review", "respond"}):
        raise ValueError("Positive decisions must be review and/or respond")
    truths = {label.external_id: label for label in labels}
    outputs = {p.external_id: p for p in predictions}
    if len(truths) != len(labels) or len(outputs) != len(predictions):
        raise ValueError("Duplicate evaluation IDs")
    if truths.keys() != outputs.keys():
        raise ValueError("Evaluate all labeled messages, including screened-out and failed messages")
    tp = fp = fn = tn = screened_positive = failed = unknown = 0
    fp_ids, fn_ids, screening_fn_ids = [], [], []
    breakdown = {name: 0 for name in ("ignore", "review", "respond", "failed")}
    positive_reviews = unknown_positive = 0
    for id, label in truths.items():
        output = outputs[id]
        if output.status == "failed" and output.decision is not None:
            raise ValueError("Failed messages cannot have a definitive decision")
        if output.status == "completed" and output.decision is None:
            raise ValueError("Completed messages must have a decision")
        if output.is_candidate is False and output.decision not in (None, "ignore"):
            raise ValueError("Screened-out messages cannot have review/respond decisions")
        positive = output.status == "completed" and output.decision in positive_decisions
        tp += int(label.relevant and positive)
        fp += int(not label.relevant and positive)
        fn += int(label.relevant and not positive)
        tn += int(not label.relevant and not positive)
        screened_positive += int(label.relevant and output.is_candidate is True)
        failed += int(output.status == "failed")
        unknown += int(output.is_candidate is None)
        unknown_positive += int(label.relevant and output.is_candidate is None)
        positive_reviews += int(label.relevant and output.decision == "review")
        breakdown["failed" if output.status == "failed" else output.decision] += 1
        if not label.relevant and positive:
            fp_ids.append(id)
        if label.relevant and not positive:
            fn_ids.append(id)
        if label.relevant and output.is_candidate is False:
            screening_fn_ids.append(id)
    return EvaluationReport(n=len(labels), tp=tp, fp=fp, fn=fn, tn=tn,
        precision=tp / (tp + fp) if tp + fp else None,
        recall=tp / (tp + fn) if tp + fn else None,
        screening_recall=screened_positive / (tp + fn) if tp + fn and not unknown_positive else None,
        failed_count=failed, unknown_screening_count=unknown,
        positive_decisions=list(positive_decisions), confusion_matrix=dict(tp=tp, fp=fp, fn=fn, tn=tn),
        false_positive_ids=sorted(fp_ids), false_negative_ids=sorted(fn_ids),
        screening_false_negative_ids=sorted(screening_fn_ids), unknown_positive_screening_count=unknown_positive,
        decision_breakdown=breakdown, review_coverage=breakdown["review"] / len(labels) if labels else None,
        positive_review_coverage=positive_reviews / (tp + fn) if tp + fn else None)
