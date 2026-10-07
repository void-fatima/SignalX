"""Setayesh's reply boundary; adapters must generate only grounded drafts."""
from typing import Protocol, Literal
from pydantic import BaseModel, Field, ValidationError
from app.agents.contracts import (
    AgentInput, AgentOutput, AnalysisResult, Decision, ProductSnapshot,
    TargetMessage, UsageEvent, UsageInfo,
)
from app.agents.orchestrator import _prepare_input
from app.agents.providers.base import ProviderError
from app.agents.providers.factory import get_provider
from app.agents.qualification import validate_qualification_result
from app.agents.scoring import calculate_score
from app.agents.screening import screen


class ReplyInput(BaseModel):
    product: ProductSnapshot
    target: TargetMessage
    context: list[TargetMessage] = Field(default_factory=list)
    analysis: AnalysisResult


class ReplyResult(BaseModel):
    response_text: str = Field(min_length=1, max_length=4000)
    provider_mode: Literal["mock", "real"]
    prompt_version: str
    limitations: list[str] = Field(default_factory=list)


class ReplyProvider(Protocol):
    def generate_reply(self, payload: ReplyInput) -> tuple[ReplyResult, list[UsageEvent]]: ...


def generate_suggested_reply(agent_input: AgentInput, analysis: AgentOutput) -> AgentOutput:
    """Generate a draft only on this explicit call; never send or approve it.

    The frozen output has no input identity. Backend must load the exact stored
    product snapshot, target, context and analysis from the authorized run.
    We verify all observable invariants without changing the existing analysis.
    ProviderError.usage includes prior analysis plus failed draft attempts.
    """
    inputs, product, target, context = _prepare_input(agent_input)
    # A new nested instance protects the caller's analysis from mutation.
    analysis = AgentOutput.model_validate(analysis.model_dump(), strict=True)
    if analysis.scoring is not None and analysis.scoring.decision == Decision.IGNORE:
        raise ValueError("Suggested replies are not allowed for IGNORE")
    if (not analysis.screening.is_candidate or not screen(product, target, context).is_candidate
            or analysis.qualification is None or analysis.scoring is None):
        raise ValueError("Suggested reply requires successful candidate qualification and scoring")
    mode = inputs.metadata.provider_mode
    if any(record.provider_mode != mode for record in analysis.usage):
        raise ValueError("Analysis usage does not match the supplied provider mode")
    qualification_usage = [record for record in analysis.usage
                           if record.stage in {"qualification", "qualification_repair"}]
    if not qualification_usage or qualification_usage[-1].outcome != "success":
        raise ValueError("Analysis must include a successful qualification provider attempt")
    qualification, target_evidence = validate_qualification_result(
        analysis.qualification, target, context, analysis.usage)
    if not qualification.evidence:
        raise ValueError("Suggested reply requires grounded qualification evidence")
    expected = calculate_score(qualification, valid_purchase_evidence=target_evidence)
    # Preserve an existing conservative human REVIEW, but never let a stale or
    # forged RESPOND bypass score_v1 guards. This verifies; it does not rescore output.
    if (analysis.scoring.score != expected.score or expected.decision == Decision.IGNORE
            or (analysis.scoring.decision == Decision.RESPOND and expected.decision != Decision.RESPOND)):
        raise ValueError("Analysis score or decision is inconsistent with grounded qualification")
    try:
        provider = get_provider(mode)
    except ProviderError as exc:
        raise ProviderError(str(exc), [*analysis.usage, *exc.usage], diagnostics=exc.diagnostics) from None
    if provider.provider_mode != mode:
        raise ProviderError("Reply provider mode does not match the supplied mode", analysis.usage)
    try:
        text, records = provider.generate_reply_structured(inputs, qualification, analysis.scoring.decision)
    except ProviderError as exc:
        raise ProviderError(str(exc), [*analysis.usage, *exc.usage], diagnostics=exc.diagnostics) from None
    try:
        records = [UsageInfo.model_validate(record.model_dump(), strict=True) for record in records]
        if (not records or len(records) > 2 or records[-1].outcome != "success"
                or any(record.provider_mode != mode or record.stage != (
                    "suggested_reply" if index == 1 else "suggested_reply_repair")
                    or record.attempt_no != index for index, record in enumerate(records, 1))):
            raise ValueError("Invalid reply usage")
        if not isinstance(text, str) or not text.strip() or len(text) > 1802:
            raise ValueError("Invalid reply text")
    except (ValidationError, ValueError, AttributeError, TypeError):
        raise ProviderError("Provider returned invalid reply data or usage", [*analysis.usage, *records]) from None
    return analysis.model_copy(update={"suggested_reply": text, "usage": [*analysis.usage, *records]})
