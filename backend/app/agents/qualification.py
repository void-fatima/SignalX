"""Validate provider output independently of HTTP and persistence."""
from pydantic import ValidationError
from app.agents.contracts import Qualification, TargetMessage, UsageEvent
from app.agents.providers.base import ProviderError


def validate_qualification(
    output: Qualification,
    target: TargetMessage,
    context: list[TargetMessage],
    usage: list[UsageEvent],
) -> tuple[Qualification, bool]:
    try:
        # Revalidate serialized models too: model_copy/mutation can bypass validation.
        qualification = Qualification.model_validate(output.model_dump())
    except (ValidationError, AttributeError) as exc:
        raise ProviderError("Provider returned invalid qualification signals", usage) from exc
    allowed = {m.id: m.content for m in [target, *context]}
    if any(e.message_id not in allowed or not e.quote.strip() or e.quote not in allowed[e.message_id]
           for e in qualification.evidence):
        raise ProviderError("Provider evidence is not grounded in supplied messages", usage)
    target_evidence = any(e.message_id == target.id for e in qualification.evidence)
    return qualification, target_evidence
