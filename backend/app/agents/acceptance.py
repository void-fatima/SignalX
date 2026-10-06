"""Manual acceptance helpers: paced real HTTP, reports and explicit test snapshots.

No application persistence, pricing fetch, background work or message sending.
Public Agent contracts and default production provider behavior stay unchanged.
"""
import os
import re
from decimal import Decimal
from pathlib import Path
from time import monotonic, sleep

import httpx
from pydantic import BaseModel, ConfigDict

from app.agents.contracts import AgentInput, AgentOutput, QualificationResult, UsageInfo
from app.agents.orchestrator import _prepare_input
from app.agents.providers.base import ProviderError
from app.agents.qualification import OBJECTION, PRICE, validate_qualification_result
from app.agents.scoring import calculate_score
from app.agents.screening import normalize

TOMAN_PER_USD = Decimal("270000")
MIN_INTERVAL_SECONDS = 65

# Static diagnostic text only. Never include exception text, model text, IDs,
# paths, headers or validation-error input values in a failure explanation.
VALIDATION_FAILURES = {
    "input_validation": ("input_contract", "Input/context failed typed validation, uniqueness or target exclusion."),
    "analysis_output_validation": ("agent_contract", "The production analysis failed local output or score validation."),
    "analysis_acceptance": ("acceptance", "An unexpected local validation failure occurred while checking the completed analysis."),
    "screening_retained": ("screening", "Screening did not retain this acceptance target."),
    "analysis_complete": ("incomplete_analysis", "Qualification, scoring or provider usage is missing."),
    "qualification_schema": ("qualification_contract", "Qualification failed strict public schema validation."),
    "evidence_grounding": ("source_evidence", "An evidence source ID is unknown or its quote is not an exact nonblank source substring."),
    "evidence_present": ("missing_evidence", "Qualification has no grounded evidence items."),
    "intent_and_need": ("qualification_content", "Qualification intent or need is empty."),
    "deterministic_score_and_guards": ("scoring", "Score/decision differs from scoring.py with the validated target-evidence guard."),
    "real_usage": ("provider_usage", "An attempt is labeled with a provider mode other than real."),
    "context_supplied": ("context_input", "The context scenario requires the supplied same-conversation context."),
    "context_price_objection": ("context_interpretation", "Intent/need does not identify a possible price, affordability or cost objection; human interpretation review is required."),
    "unsupported_numeric_claim": ("unsupported_claim", "Need contains a numeric or currency expression although these fixtures supply no monetary amount; inspect the interpretation."),
    "snapshot_path": ("snapshot_io", "Snapshot destination must be new and its parent directory must exist."),
    "snapshot_save": ("snapshot_io", "The explicitly requested analysis snapshot could not be written."),
    "snapshot_secret": ("security", "A secret echoed in the analysis prevents snapshot storage."),
    "snapshot_load": ("snapshot_io", "The requested analysis snapshot could not be read."),
    "snapshot_size": ("snapshot_contract", "Analysis snapshot exceeds the permitted size."),
    "snapshot_contract": ("snapshot_contract", "Analysis snapshot does not match the paired input/output schema."),
    "snapshot_provider_mode": ("snapshot_mismatch", "The snapshot must contain real-mode input."),
    "scenario_match": ("scenario_mismatch", "Stored product/message/context contents do not match the selected acceptance scenario."),
    "reply_eligibility": ("reply_eligibility", "The supplied analysis failed reply eligibility or input/analysis association checks."),
    "analysis_unchanged": ("reply_invariant", "Reply altered the analysis, lost prior usage or returned empty text."),
    "reply_usage_appended": ("provider_usage", "Only real reply-attempt usage may be appended."),
    "language_matches": ("reply_language", "Draft language differs from the target language."),
}


def validation_diagnostic(failed_check: str) -> dict[str, str]:
    category, explanation = VALIDATION_FAILURES[failed_check]
    return {"failed_check": failed_check, "failure_category": category, "explanation": explanation}


class AcceptanceValidationError(ValueError):
    """Named private CLI error; never changes public Agent contracts."""
    def __init__(self, failed_check: str):
        self.diagnostic = validation_diagnostic(failed_check)
        super().__init__(self.diagnostic["explanation"])


class RequestPacer:
    """One sequential invocation; pause BEFORE every HTTP attempt, including repairs.

    Initial delay protects against a recent manual call. It does not coordinate
    other processes/organization traffic. Budgets count paid-capable HTTP attempts,
    not confirmed account charges, which cannot be inferred after network failures.
    """
    def __init__(self, budget: int):
        self.budget = budget
        self.request_count = 0
        self.next_allowed = monotonic() + MIN_INTERVAL_SECONDS

    def before_request(self, request: httpx.Request) -> None:
        if str(request.url) != "https://api.avalai.ir/v1/responses" or request.method != "POST":
            raise RuntimeError("Acceptance transport requires the configured AvalAI Responses endpoint")
        if self.request_count >= self.budget:
            raise RuntimeError("Acceptance HTTP request budget exhausted")
        while (remaining := self.next_allowed - monotonic()) > 0:
            sleep(min(remaining, 30))
        self.request_count += 1
        self.next_allowed = monotonic() + MIN_INTERVAL_SECONDS


class AnalysisSnapshot(BaseModel):
    """Private CLI artifact containing an actual paired input/analysis, never a key."""
    model_config = ConfigDict(extra="forbid")
    agent_input: AgentInput
    analysis: AgentOutput


def save_snapshot(path: Path, inputs: AgentInput, analysis: AgentOutput) -> None:
    snapshot = AnalysisSnapshot(agent_input=inputs, analysis=analysis)
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    def contains_key(value):
        if isinstance(value, str):
            return key in value
        if isinstance(value, dict):
            return any(contains_key(name) or contains_key(item) for name, item in value.items())
        if isinstance(value, list):
            return any(contains_key(item) for item in value)
        return False
    if key and contains_key(snapshot.model_dump(mode="json")):
        raise AcceptanceValidationError("snapshot_secret")
    text = snapshot.model_dump_json(indent=2)
    # Never overwrite an existing file. Backend persistence is not involved.
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)


def load_snapshot(path: Path) -> AnalysisSnapshot:
    if path.stat().st_size > 100_000:
        raise AcceptanceValidationError("snapshot_size")
    try:
        snapshot = AnalysisSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        raise AcceptanceValidationError("snapshot_contract") from None
    if snapshot.agent_input.metadata.provider_mode != "real":
        raise AcceptanceValidationError("snapshot_provider_mode")
    return snapshot


def usage_report(records: list[UsageInfo]) -> list[dict]:
    reports = []
    for record in records:
        report = record.model_dump(mode="json")
        cost = record.estimated_cost
        # Verified base rates cannot price Luna's documented long-context tier.
        if record.input_tokens is not None and record.input_tokens > 272_000:
            cost = None
            report.update(estimated_cost=None, cost_status="unknown")
        report["estimated_toman"] = str(cost * TOMAN_PER_USD) if cost is not None else None
        report["exact_account_charge"] = False
        reports.append(report)
    return reports


def analysis_checks(inputs: AgentInput, output: AgentOutput, *, contextual: bool = False) -> dict[str, bool]:
    try:
        _, _, target, context = _prepare_input(inputs)
    except ValueError:
        raise AcceptanceValidationError("input_validation") from None
    if not output.screening.is_candidate:
        raise AcceptanceValidationError("screening_retained")
    if output.qualification is None or output.scoring is None or not output.usage:
        raise AcceptanceValidationError("analysis_complete")
    try:
        qualification, target_evidence = validate_qualification_result(output.qualification, target, context, output.usage)
    except ProviderError:
        # Determine the safe category by schema validity, never by raw error text.
        try:
            QualificationResult.model_validate(output.qualification.model_dump(), strict=True)
        except ValueError:
            raise AcceptanceValidationError("qualification_schema") from None
        raise AcceptanceValidationError("evidence_grounding") from None
    if not qualification.evidence:
        raise AcceptanceValidationError("evidence_present")
    if not qualification.intent.strip() or not qualification.need.strip():
        raise AcceptanceValidationError("intent_and_need")
    if output.scoring != calculate_score(qualification, valid_purchase_evidence=target_evidence):
        raise AcceptanceValidationError("deterministic_score_and_guards")
    if any(record.provider_mode != "real" for record in output.usage):
        raise AcceptanceValidationError("real_usage")
    context_evidence = any(e.message_id in {m.id for m in context} for e in qualification.evidence)
    if contextual:
        if not context:
            raise AcceptanceValidationError("context_supplied")
        interpretation = normalize(qualification.intent.replace("_", " ") + " " + qualification.need)
        # A supporting context quote is optional under the frozen contract.
        # Retain exact grounding of ALL returned evidence. Check interpretation,
        # not an arbitrary citation pattern or particular score/decision.
        if not (OBJECTION.search(interpretation) or PRICE.search(interpretation)
                or re.search(r"\b(?:objection|affordability|affordable)\b|اعتراض|گرانی", interpretation)):
            raise AcceptanceValidationError("context_price_objection")
    # These fixtures supply no monetary amounts. Do not accept fabricated
    # numeric prices in the need; interpretation still needs human inspection.
    if re.search(r"\d|[$€£]", qualification.need):
        raise AcceptanceValidationError("unsupported_numeric_claim")
    return {"screening_retained": True, "signals_bounded": True, "evidence_grounded": True,
            "deterministic_score_and_guards": True, "real_usage": True,
            "context_evidence_present": context_evidence,
            "context_price_objection": contextual}
