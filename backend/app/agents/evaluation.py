"""Offline evaluation only; labels never enter Agent/provider input."""
from typing import Literal
from pydantic import BaseModel


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


def validate_split(dev: list[Label], test: list[Label]) -> None:
    if {l.conversation_id for l in dev} & {l.conversation_id for l in test}:
        raise ValueError("Development and test conversations overlap")


def evaluate(labels: list[Label], predictions: list[Prediction]) -> EvaluationReport:
    truths = {label.external_id: label for label in labels}
    outputs = {p.external_id: p for p in predictions}
    if len(truths) != len(labels) or len(outputs) != len(predictions):
        raise ValueError("Duplicate evaluation IDs")
    if truths.keys() != outputs.keys():
        raise ValueError("Evaluate all labeled messages, including screened-out and failed messages")
    tp = fp = fn = tn = screened_positive = failed = unknown = 0
    for id, label in truths.items():
        output = outputs[id]
        if output.status == "failed" and output.decision is not None:
            raise ValueError("Failed messages cannot have a definitive decision")
        if output.status == "completed" and output.decision is None:
            raise ValueError("Completed messages must have a decision")
        positive = output.status == "completed" and output.decision == "respond"
        tp += int(label.relevant and positive)
        fp += int(not label.relevant and positive)
        fn += int(label.relevant and not positive)
        tn += int(not label.relevant and not positive)
        screened_positive += int(label.relevant and output.is_candidate is True)
        failed += int(output.status == "failed")
        unknown += int(output.is_candidate is None)
    return EvaluationReport(n=len(labels), tp=tp, fp=fp, fn=fn, tn=tn,
        precision=tp / (tp + fp) if tp + fp else None,
        recall=tp / (tp + fn) if tp + fn else None,
        screening_recall=screened_positive / (tp + fn) if tp + fn and not unknown else None,
        failed_count=failed, unknown_screening_count=unknown)
