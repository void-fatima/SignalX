"""Public Agent orchestration; persistence and context retrieval belong to Backend."""
from app.agents.contracts import AgentInput, AgentOutput, ProductSnapshot, TargetMessage, UsageInfo
from app.agents.providers.base import ProviderError
from app.agents.providers.factory import get_provider
from app.agents.qualification import validate_qualification_result
from app.agents.scoring import SCORING_VERSION, calculate_score_with_reason, screening_decision_reason
from app.agents.screening import screen
from pydantic import ValidationError


def _prepare_input(inputs: AgentInput) -> tuple[AgentInput, ProductSnapshot, TargetMessage, list[TargetMessage]]:
    """Shared input validation for analysis and explicitly requested drafts."""
    # Revalidate nested models as mutation/model_copy can bypass frozen field rules.
    inputs = AgentInput.model_validate(inputs.model_dump() if isinstance(inputs, AgentInput) else inputs)
    context_ids = [message.id for message in inputs.context_messages]
    if len(set(context_ids)) != len(context_ids):
        raise ValueError("Context message IDs must be unique")
    if inputs.message.id in context_ids:
        raise ValueError("Context must exclude the target message")

    product = ProductSnapshot(**inputs.product.model_dump(exclude={"id"}))
    message = inputs.message
    target = TargetMessage(id=message.id, external_id=message.id, content=message.content,
        author=message.author, timestamp=message.timestamp, conversation_id=message.conversation_id,
        reply_to_external_id=message.reply_to_message_id)
    # The caller's selected context is preserved without new queries or selection.
    context = [TargetMessage(id=m.id, external_id=m.id, content=m.content,
        author=m.author, timestamp=m.timestamp, conversation_id=target.conversation_id)
        for m in inputs.context_messages]
    return inputs, product, target, context


def analyze_agent(inputs: AgentInput) -> AgentOutput:
    """Screen, qualify, ground and score; never generate or send replies.

    Backend supplies selected context from the target conversation. ContextMessage
    has no conversation_id, so this function cannot independently verify its scope.
    Validation failures raise ValidationError/ValueError; provider failures raise
    ProviderError with their attempt history.
    """
    inputs, product, target, context = _prepare_input(inputs)

    screening = screen(product, target, context)
    if not screening.is_candidate:
        return AgentOutput(screening=screening, decision_reason=screening_decision_reason(screening))

    mode = inputs.metadata.provider_mode
    provider = get_provider(mode)
    if provider.provider_mode != mode:
        raise ProviderError("Configured provider mode does not match the supplied provider", [])
    qualification, usage = provider.qualify_structured(product, target, context)
    try:
        usage = [UsageInfo.model_validate(record.model_dump(), strict=True) for record in usage]
    except (ValidationError, AttributeError, TypeError):
        raise ProviderError("Provider returned invalid usage metadata", usage) from None
    if any(record.provider_mode != mode for record in usage):
        raise ProviderError("Provider usage mode does not match the configured mode", usage)
    qualification, target_evidence = validate_qualification_result(qualification, target, context, usage)
    scoring, decision_reason = calculate_score_with_reason(qualification, valid_purchase_evidence=target_evidence)
    # Only the real qualification provider can attest to its executed prompt.
    prompt_version = getattr(provider, "prompt_version", None) if mode == "real" else None
    return AgentOutput(screening=screening, qualification=qualification, scoring=scoring, usage=usage,
        decision_reason=decision_reason, scoring_version=SCORING_VERSION, prompt_version=prompt_version)
