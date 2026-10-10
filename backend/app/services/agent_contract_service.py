"""Backend mapping, validation and persistence for the shared Agent contract."""
from collections.abc import Iterable

from sqlalchemy import select
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
    UsageEvent,
    UsageInfo,
)
from app.agents.context import select_context
from app.models import Analysis, AnalysisRun, Usage


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


def project_intent(intent: str | None) -> str | None:
    """Bound only the legacy VARCHAR projection; structured output stays intact.

    Python slices Unicode characters, matching PostgreSQL VARCHAR character
    limits rather than UTF-8 byte lengths.
    """
    limit = Analysis.__table__.c.intent.type.length
    return intent[:limit] if intent is not None else None


def persist_analysis_usage(
    session: Session, *, run_id: str, message_id: str, run_attempt_no: int,
    events: Iterable[UsageInfo | UsageEvent | dict], analysis_id: str | None = None,
) -> list[Usage]:
    """Record each analysis provider attempt once, optionally before its result.

    The run-row lock serializes late-worker accounting as well as normal writes.
    Stage/attempt identify calls within a message's run attempt. Explicit run
    retries have a new run_attempt_no and therefore retain their actual new calls.
    Suggested-reply regeneration uses its existing separate accounting path.
    The caller owns commit/rollback; nullable analysis_id permits independent
    accounting even when an Analysis cannot be inserted.
    """
    session.scalar(select(AnalysisRun.id).where(AnalysisRun.id == run_id).with_for_update())
    existing = session.scalars(select(Usage).where(
        Usage.run_id == run_id, Usage.message_id == message_id,
        Usage.run_attempt_no == run_attempt_no,
    )).all()
    by_attempt = {(row.stage, row.attempt_no): row for row in existing}
    rows = []
    for event in events:
        values = event.model_dump() if hasattr(event, "model_dump") else dict(event)
        if "estimated_cost" in values:
            values["cost_usd"] = values.pop("estimated_cost")
        values.pop("request_id", None)
        values.pop("run_attempt_no", None)
        key = (values["stage"], values.get("attempt_no", 1))
        row = by_attempt.get(key)
        if row is None:
            row = Usage(run_id=run_id, message_id=message_id, analysis_id=analysis_id,
                        run_attempt_no=run_attempt_no, **values)
            session.add(row)
            by_attempt[key] = row
        elif analysis_id is not None and row.analysis_id is None:
            row.analysis_id = analysis_id
        rows.append(row)
    return rows


def persist_agent_output(
    session: Session,
    *,
    run_id: str,
    target_message_id: str,
    inputs: AgentInput,
    raw_output: AgentOutput | dict,
    run_attempt_no: int = 1,
) -> Analysis:
    """Validate and persist the complete contract output plus API projection."""
    output = validate_agent_output(inputs, raw_output)
    usage_rows = persist_analysis_usage(session, run_id=run_id, message_id=target_message_id,
        run_attempt_no=run_attempt_no, events=output.usage)
    qualification = output.qualification
    scoring = output.scoring
    decision = scoring.decision.value.lower() if scoring else ("ignore" if not output.screening.is_candidate else None)
    values = dict(
        status="completed",
        failure_category=None,
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
        intent=project_intent(qualification.intent) if qualification else None,
        need=qualification.need if qualification else None,
        # The Agent contract has no budget field; preserve the legacy API's
        # explicit unknown sentinel for qualified leads.
        budget_signal="unknown" if qualification else None,
        lead_score=scoring.score if scoring else None,
        decision=decision,
        decision_reason=output.decision_reason,
        reason=qualification.need if qualification else output.screening.reason,
        evidence=[item.model_dump(mode="json") for item in qualification.evidence] if qualification else [],
        context_message_ids=[item.id for item in inputs.context_messages],
        limitations=qualification.limitations if qualification else [],
        agent_output=output.model_dump(mode="json"),
        scoring_version=output.scoring_version,
        prompt_version=output.prompt_version,
        provider_mode=inputs.metadata.provider_mode,
    )
    analysis = session.scalar(select(Analysis).where(
        Analysis.run_id == run_id, Analysis.message_id == target_message_id,
    ).with_for_update())
    if analysis is None:
        analysis = Analysis(run_id=run_id, message_id=target_message_id, **values)
        session.add(analysis)
    elif analysis.status == "completed":
        for event in usage_rows:
            if event.analysis_id is None:
                event.analysis_id = analysis.id
        return analysis
    else:
        # Retry the failed/missing message in place so analysis IDs, feedback,
        # responses and references to this lead stay stable.
        for name, value in values.items():
            setattr(analysis, name, value)
    session.flush()
    for event in usage_rows:
        if event.analysis_id is None:
            event.analysis_id = analysis.id
    return analysis
