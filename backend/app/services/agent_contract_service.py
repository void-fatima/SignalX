"""Backend mapping, validation and persistence for the shared Agent contract."""
from sqlalchemy.orm import Session

from app.agents.contracts import (
    AgentInput,
    AgentMetadata,
    AgentOutput,
    ContextMessage,
    MessageInput,
    ProductInput,
    RunConfig,
    TargetMessage,
)
from app.agents.context import select_context
from app.models import Analysis, Usage


def build_agent_input(
    *,
    product_snapshot: dict,
    run_id: str,
    provider_mode: str,
    target: TargetMessage,
    messages: list[TargetMessage],
    config: RunConfig,
) -> AgentInput:
    """Build a contract input from the immutable run snapshot and batch data.

    `Message.id` is the internal database ID. External IDs are used only for
    resolving CSV parent references, and only within the target conversation.
    Context selection is delegated to the shared, pure Agent selector.
    """
    by_external_id = {
        item.external_id: item
        for item in messages
        if item.conversation_id == target.conversation_id
    }
    parent = by_external_id.get(target.reply_to_external_id) if target.reply_to_external_id else None
    if parent is not None and parent.id == target.id:
        parent = None

    selected_context = select_context(target, messages, config)
    return AgentInput(
        product=ProductInput(
            id=str(product_snapshot["id"]),
            name=product_snapshot["name"],
            description=product_snapshot["description"],
            target_customer=product_snapshot["target_customer"],
        ),
        message=MessageInput(
            id=target.id,
            content=target.content,
            author=target.author,
            timestamp=target.timestamp,
            conversation_id=target.conversation_id,
            reply_to_message_id=parent.id if parent else None,
        ),
        context_messages=[
            ContextMessage(
                id=item.id,
                content=item.content,
                author=item.author,
                timestamp=item.timestamp,
            )
            for item in selected_context
        ],
        metadata=AgentMetadata(run_id=run_id, provider_mode=provider_mode),
    )


def validate_agent_output(inputs: AgentInput, raw_output: AgentOutput | dict) -> AgentOutput:
    """Validate shape and cross-reference output against the supplied input."""
    output = AgentOutput.model_validate(raw_output)
    allowed_messages = {inputs.message.id: inputs.message.content}
    allowed_messages.update({item.id: item.content for item in inputs.context_messages})
    qualification = output.qualification
    if output.screening.is_candidate and (qualification is None or output.scoring is None):
        raise ValueError("Candidate AgentOutput requires qualification and scoring")
    if qualification is not None:
        for evidence in qualification.evidence:
            content = allowed_messages.get(evidence.message_id)
            if content is None:
                raise ValueError("Agent evidence references a message outside AgentInput")
            if evidence.quote not in content:
                raise ValueError("Agent evidence quote must occur in the referenced input message")
    if any(event.provider_mode != inputs.metadata.provider_mode for event in output.usage):
        raise ValueError("Agent usage provider_mode must match AgentInput metadata")
    return output


def persist_agent_output(
    session: Session,
    *,
    run_id: str,
    target_message_id: str,
    inputs: AgentInput,
    raw_output: AgentOutput | dict,
) -> Analysis:
    """Validate and persist the complete contract output plus API projection."""
    output = validate_agent_output(inputs, raw_output)
    qualification = output.qualification
    scoring = output.scoring
    decision = scoring.decision.value.lower() if scoring else ("ignore" if not output.screening.is_candidate else None)
    analysis = Analysis(
        run_id=run_id,
        message_id=target_message_id,
        status="completed",
        is_candidate=output.screening.is_candidate,
        screening_reason=output.screening.reason,
        signals=(
            {
                "purchase_intent": qualification.purchase_intent,
                "product_fit": qualification.product_fit,
                "need_strength": qualification.need_strength,
                "urgency": qualification.urgency,
                "confidence": qualification.confidence,
                "response_opportunity": qualification.response_opportunity,
            }
            if qualification
            else None
        ),
        intent=qualification.intent if qualification else None,
        need=qualification.need if qualification else None,
        # The Agent contract has no budget field; preserve the legacy API's
        # explicit unknown sentinel for qualified leads.
        budget_signal="unknown" if qualification else None,
        lead_score=scoring.score if scoring else None,
        decision=decision,
        decision_reason=None,
        reason=qualification.need if qualification else output.screening.reason,
        evidence=[item.model_dump(mode="json") for item in qualification.evidence] if qualification else [],
        context_message_ids=[item.id for item in inputs.context_messages],
        limitations=qualification.limitations if qualification else [],
        agent_output=output.model_dump(mode="json"),
        provider_mode=inputs.metadata.provider_mode,
    )
    session.add(analysis)
    session.flush()
    for event in output.usage:
        session.add(
            Usage(
                run_id=run_id,
                message_id=target_message_id,
                analysis_id=analysis.id,
                stage=event.stage,
                attempt_no=event.attempt_no,
                model=event.model,
                provider_mode=event.provider_mode,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                cost_usd=event.estimated_cost,
                cost_status=event.cost_status,
                price_version=event.price_version,
                latency_ms=event.latency_ms,
                outcome=event.outcome,
            )
        )
    return analysis
