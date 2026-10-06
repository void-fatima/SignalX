"""Offline heuristic or recorded-real evaluation. No HTTP/provider construction."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from app.agents.acceptance import AnalysisSnapshot
from app.agents.contracts import AgentInput, AgentOutput, ScreeningResult, UsageInfo
from app.agents.evaluation import Label, Prediction, evaluate
from app.agents.evaluation_dataset import (
    DATA_DIRECTORY, EvaluationCase, EvaluationLabel, EvaluationModel, input_digest, load_dataset, validate_dataset,
)
from app.agents.orchestrator import _prepare_input
from app.agents.providers.base import ProviderError
from app.agents.qualification import qualify, validate_qualification_result
from app.agents.scoring import SCORING_VERSION, calculate_score, calculate_score_with_reason, screening_decision_reason
from app.agents.screening import screen


class RecordedAnalysis(EvaluationModel):
    case_id: str
    source: Literal["user_run_recorded_real"]
    origin: str
    original_snapshot_sha256: str
    status: Literal["completed", "failed"] = "completed"
    snapshot: AnalysisSnapshot | None = None
    failed_input: AgentInput | None = None
    failed_usage: list[UsageInfo] = Field(default_factory=list)
    failed_screening: ScreeningResult | None = None
    # Old snapshots omit version fields; never backfill their historical versions.
    recorded_prompt_version: str | None = None
    recorded_score_version: str | None = None

    @model_validator(mode="after")
    def distinct_outcomes(self):
        if self.status == "completed":
            if self.snapshot is None or self.failed_input is not None or self.failed_usage or self.failed_screening is not None:
                raise ValueError("Completed recording requires only its paired snapshot")
        elif self.snapshot is not None or self.failed_input is None:
            raise ValueError("Failed recording requires original input, not a fabricated successful AgentOutput")
        return self


class EvaluationRow(EvaluationModel):
    case_id: str
    prediction: Prediction
    analysis: AgentOutput | None = None
    error_category: str | None = None
    failed_usage: list[UsageInfo] = Field(default_factory=list)
    input_surface: Literal["public_contract", "extended_legacy_profile"]


def run_heuristic(case: EvaluationCase) -> EvaluationRow:
    """Labels cannot enter this function. No provider or invented usage/cost."""
    inputs, product, target, context = _prepare_input(case.agent_input)
    if case.legacy_profile is not None:
        product = case.legacy_profile.model_copy(deep=True)
    surface = "public_contract" if case.legacy_profile is None else "extended_legacy_profile"
    candidate = None
    try:
        screening = screen(product, target, context)
        candidate = screening.is_candidate
        if not candidate:
            analysis = AgentOutput(screening=screening, decision_reason=screening_decision_reason(screening))
            decision = "ignore"
        else:
            qualification = qualify(product, target, context)
            qualification, valid = validate_qualification_result(qualification, target, context, [])
            scoring, decision_reason = calculate_score_with_reason(qualification, valid_purchase_evidence=valid)
            analysis = AgentOutput(screening=screening, qualification=qualification, scoring=scoring,
                decision_reason=decision_reason, scoring_version=SCORING_VERSION)
            decision = scoring.decision.value.lower()
        return EvaluationRow(case_id=case.case_id, input_surface=surface, analysis=analysis,
            prediction=Prediction(external_id=case.case_id, decision=decision,
                                  is_candidate=candidate, status="completed"))
    except (ProviderError, ValueError):
        # Failed rows remain in denominators; never replace a failure with success.
        return EvaluationRow(case_id=case.case_id, input_surface=surface, error_category="heuristic_validation_failure",
            prediction=Prediction(external_id=case.case_id, decision=None,
                                  is_candidate=candidate, status="failed"))


def replay_record(case: EvaluationCase, record: RecordedAnalysis) -> EvaluationRow:
    recorded_input = record.snapshot.agent_input if record.snapshot is not None else record.failed_input
    if (record.case_id != case.case_id or input_digest(recorded_input) != input_digest(case.agent_input)
            or case.legacy_profile is not None):
        raise ValueError("Recorded result/input association or input-surface mismatch")
    inputs, product, target, context = _prepare_input(recorded_input)
    if inputs.metadata.provider_mode != "real":
        raise ValueError("Recorded input must use real mode")
    if record.status == "failed":
        if any(r.provider_mode != "real" for r in record.failed_usage):
            raise ValueError("Failed real recordings cannot contain Mock usage")
        if record.failed_screening is not None and record.failed_screening != screen(product, target, context):
            raise ValueError("Recorded screening differs from current screening.py")
        return EvaluationRow(case_id=case.case_id, input_surface="public_contract",
            failed_usage=[r.model_copy(deep=True) for r in record.failed_usage], error_category="recorded_delivery_failure",
            prediction=Prediction(external_id=case.case_id, decision=None, status="failed",
                is_candidate=record.failed_screening.is_candidate if record.failed_screening is not None else None))
    output = AgentOutput.model_validate(record.snapshot.analysis.model_dump(), strict=True)
    if any(r.provider_mode != "real" for r in output.usage):
        raise ValueError("Recorded real output cannot contain Mock usage")
    if output.screening != screen(product, target, context):
        raise ValueError("Recorded screening differs from current screening.py")
    if not output.screening.is_candidate:
        if output.qualification is not None or output.scoring is not None or output.usage or output.suggested_reply is not None:
            raise ValueError("Screened-out recording must not invent qualification, scoring, usage or reply")
        return EvaluationRow(case_id=case.case_id, analysis=output, input_surface="public_contract",
            prediction=Prediction(external_id=case.case_id, decision="ignore", is_candidate=False, status="completed"))
    qualification_calls = [r for r in output.usage if r.stage in {"qualification", "qualification_repair"}]
    if not qualification_calls or qualification_calls[-1].outcome != "success":
        raise ValueError("Recorded replay requires successful qualification provenance")
    if output.qualification is None or output.scoring is None:
        raise ValueError("Recorded analysis is incomplete")
    qualification, valid = validate_qualification_result(output.qualification, target, context, output.usage)
    if output.scoring != calculate_score(qualification, valid_purchase_evidence=valid):
        raise ValueError("Recorded decision/score fails verification against current scoring.py")
    return EvaluationRow(case_id=case.case_id, analysis=output, input_surface="public_contract",
        prediction=Prediction(external_id=case.case_id, decision=output.scoring.decision.value.lower(),
                              is_candidate=output.screening.is_candidate, status="completed"))


def report_rows(labels: list[EvaluationLabel], rows: list[EvaluationRow]) -> dict:
    truths = [Label(external_id=l.case_id, conversation_id=l.conversation_id, relevant=l.relevant) for l in labels]
    predictions = [row.prediction for row in rows]
    discovery = evaluate(truths, predictions, positive_decisions=("review", "respond"))
    response = evaluate(truths, predictions)  # legacy definition preserved
    by_row = {row.case_id: row for row in rows}
    mismatches = [label.case_id for label in labels if (by_row[label.case_id].prediction.status == "failed"
        or by_row[label.case_id].prediction.decision.upper() not in label.acceptable_decisions)]
    return dict(discovery=discovery.model_dump(), respond_only=response.model_dump(),
        acceptable_decision_mismatch_ids=sorted(mismatches),
        acceptable_decision_coverage=(len(labels) - len(mismatches)) / len(labels) if labels else None)


def build_report(cases: list[EvaluationCase], labels: list[EvaluationLabel], *, split: str,
                 records: list[RecordedAnalysis] | None = None) -> dict:
    if split not in {"dev", "test"}:
        raise ValueError("Evaluation split must be dev or test")
    validate_dataset(cases, labels)
    by_label = {label.case_id: label for label in labels}
    selected = [case for case in cases if by_label[case.case_id].split == split]
    selected_labels = [by_label[case.case_id] for case in selected]
    population = len(selected)
    if records is None:
        rows = [run_heuristic(case) for case in selected]
        mode = "offline_heuristic"
    else:
        by_record = {record.case_id: record for record in records}
        if len(by_record) != len(records) or not records:
            raise ValueError("Recorded results must be nonempty with unique IDs")
        if by_record.keys() - {case.case_id for case in selected}:
            raise ValueError("Recorded results do not belong to the selected split")
        if split == "test" and by_record.keys() != {case.case_id for case in selected}:
            raise ValueError("Independent test reporting requires every held-out recorded prediction")
        selected = [case for case in selected if case.case_id in by_record]
        selected_labels = [by_label[case.case_id] for case in selected]
        rows = [replay_record(case, by_record[case.case_id]) for case in selected]
        mode = "recorded_real_provider"
    report = dict(mode=mode, split=split, paid_requests_this_evaluation=0, live_llm_evaluation_performed=False,
        split_population=population, evaluated_count=len(rows),
        coverage=len(rows) / population if population else None,
        score_verification_version=SCORING_VERSION, thresholds_tuned=False,
        metric_meaning="lead discovery counts REVIEW or RESPOND; RESPOND-only is also reported",
        limitations=["Synthetic provisional labels; no independent human adjudication",
            "Conversation-held-out test is a synthetic holdout, not a representative production sample",
            "Offline heuristics do not measure real LLM performance" if mode == "offline_heuristic" else
            "Recorded subset is observational and selected; historical prompt/score versions may be unknown; no population accuracy claim"],
        **report_rows(selected_labels, rows), predictions=[row.model_dump(mode="json") for row in rows])
    report["code_fingerprints"] = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ("screening.py", "qualification.py", "scoring.py")}
    # Do not hide errors by computing metrics only on successful rows.
    report["breakdowns"] = {}
    for key in ("language", "category", "input_surface"):
        report["breakdowns"][key] = {}
        by_surface = {row.case_id: row.input_surface for row in rows}
        def attribute(case):
            return by_surface[case.case_id] if key == "input_surface" else getattr(case, key)
        for value in sorted({attribute(case) for case in selected}):
            ids = {case.case_id for case in selected if attribute(case) == value}
            report["breakdowns"][key][value] = report_rows(
                [label for label in selected_labels if label.case_id in ids], [row for row in rows if row.case_id in ids])
    if records is not None:
        report["record_provenance"] = [record.model_dump(mode="json",
            exclude={"snapshot", "failed_input", "failed_usage", "failed_screening"}) for record in records]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline evaluation only: no HTTP, LLM calls or threshold tuning")
    parser.add_argument("--mode", choices=("heuristic", "recorded"), default="heuristic")
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    parser.add_argument("--dataset", type=Path, default=DATA_DIRECTORY)
    parser.add_argument("--records", type=Path)
    parser.add_argument("--output", type=Path, help="Explicit new report artifact; never overwrite")
    args = parser.parse_args(argv)
    if (args.mode == "recorded") != (args.records is not None):
        parser.error("--records is required only for recorded mode")
    try:
        manifest, cases, labels = load_dataset(args.dataset)
        records = ([RecordedAnalysis.model_validate(row) for row in json.loads(args.records.read_text(encoding="utf-8"))]
                   if args.records is not None else None)
        report = build_report(cases, labels, split=args.split, records=records)
        report["dataset"] = manifest.model_dump()
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        def redact(value):
            if isinstance(value, str):
                return value.replace(key, "[REDACTED]") if key else value
            if isinstance(value, dict):
                return {redact(name): redact(item) for name, item in value.items()}
            if isinstance(value, list):
                return [redact(item) for item in value]
            return value
        report = redact(report)
        text = json.dumps(report, indent=2, ensure_ascii=False)
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(text + "\n")
        else:
            try:
                text.encode(sys.stdout.encoding or "utf-8")
            except UnicodeEncodeError:
                text = json.dumps(report, indent=2, ensure_ascii=True)
            print(text)
        return 0
    except (ValueError, OSError, TypeError, KeyError, AttributeError, ProviderError):
        print(json.dumps(dict(status="evaluation_error", error="Dataset, record association, grounding, scoring or output artifact validation failed; raw details suppressed.")), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
