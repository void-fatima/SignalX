"""Authorized suggested-response generation, editing, and feedback persistence."""
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.contracts import (
    AgentInput,
    AgentMetadata,
    AgentOutput,
    ContextMessage,
    MessageInput,
    ProductInput,
    UsageInfo,
)
from app.agents.providers.base import ProviderError
from app.agents.reply import generate_suggested_reply
from app.core.errors import AppError
from app.models import (
    Analysis,
    AnalysisRun,
    LeadFeedback,
    Message,
    SuggestedResponse,
    Usage,
    utcnow,
)
from app.schemas.response import FeedbackInput, FeedbackOut, ResponseDraft, ResponsePatch


REPLY_STAGES = {"suggested_reply", "suggested_reply_repair"}


def _owned_analysis(session: Session, user_id: UUID | str, analysis_id: UUID | str) -> Analysis:
    analysis = session.scalar(
        select(Analysis)
        .join(AnalysisRun, AnalysisRun.id == Analysis.run_id)
        .where(Analysis.id == str(analysis_id), AnalysisRun.user_id == str(user_id))
    )
    if analysis is None:
        raise AppError("not_found", "Lead does not exist", 404)
    return analysis


def response_out(row: SuggestedResponse | None) -> ResponseDraft | None:
    if row is None:
        return None
    return ResponseDraft(
        analysis_id=UUID(row.analysis_id),
        response_text=row.response_text,
        status=row.status,
        provider_mode=row.provider_mode,
        updated_at=row.updated_at,
    )


def feedback_out(row: LeadFeedback | None) -> FeedbackOut | None:
    if row is None:
        return None
    return FeedbackOut(
        analysis_id=UUID(row.analysis_id),
        relevant=row.relevant,
        comment=row.comment,
        updated_at=row.updated_at,
    )


def _reply_input(session: Session, analysis: Analysis, run: AnalysisRun) -> AgentInput:
    target = session.scalar(
        select(Message).where(
            Message.id == analysis.message_id,
            Message.batch_id == run.batch_id,
        )
    )
    if target is None:
        raise AppError("invalid_analysis", "Lead message is unavailable", 409)

    context_ids = list(analysis.context_message_ids or [])
    if len(context_ids) != len(set(context_ids)) or target.id in context_ids:
        raise AppError("invalid_analysis_context", "Lead context is invalid", 409)
    context_by_id: dict[str, Message] = {}
    if context_ids:
        rows = session.scalars(
            select(Message).where(
                Message.id.in_(context_ids),
                Message.batch_id == run.batch_id,
                Message.conversation_id == target.conversation_id,
            )
        ).all()
        context_by_id = {row.id: row for row in rows}
    if len(context_by_id) != len(set(context_ids)):
        raise AppError("invalid_analysis_context", "Lead context is unavailable or out of scope", 409)

    # Parent references are resolved only inside this batch and conversation.
    parent = None
    if target.reply_to_external_id:
        parent = session.scalar(
            select(Message).where(
                Message.batch_id == run.batch_id,
                Message.conversation_id == target.conversation_id,
                Message.external_id == target.reply_to_external_id,
            )
        )

    product = run.product_snapshot
    mode = run.config_snapshot.get("provider_mode")
    if mode not in {"mock", "real"} or analysis.provider_mode != mode:
        raise AppError("invalid_analysis_provider", "Lead provider metadata is inconsistent", 409)
    return AgentInput(
        product=ProductInput(
            id=run.product_id,
            name=product["name"],
            description=product["description"],
            target_customer=product["target_customer"],
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
                id=context_by_id[context_id].id,
                content=context_by_id[context_id].content,
                author=context_by_id[context_id].author,
                timestamp=context_by_id[context_id].timestamp,
            )
            for context_id in context_ids
        ],
        metadata=AgentMetadata(run_id=run.id, provider_mode=mode),
    )


def _append_reply_usage(
    session: Session,
    *,
    analysis: Analysis,
    target_message_id: str,
    events: list[UsageInfo],
) -> None:
    for event in events:
        if event.stage not in REPLY_STAGES:
            continue
        session.add(
            Usage(
                run_id=analysis.run_id,
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


def _attempts_after(existing_count: int, events: list[object]) -> list[UsageInfo]:
    attempts = [UsageInfo.model_validate(event.model_dump(), strict=True) for event in events[existing_count:]]
    if any(event.stage not in REPLY_STAGES for event in attempts):
        raise ValueError("Reply returned usage for an unrelated stage")
    return attempts


def generate_response(
    session: Session,
    user_id: UUID | str,
    analysis_id: UUID | str,
    *,
    regenerate: bool = False,
) -> ResponseDraft:
    analysis = _owned_analysis(session, user_id, analysis_id)
    existing = session.scalar(
        select(SuggestedResponse).where(SuggestedResponse.analysis_id == analysis.id)
    )
    if existing is not None and not regenerate:
        return response_out(existing)

    run = session.get(AnalysisRun, analysis.run_id)
    if run is None or analysis.status != "completed" or not analysis.is_candidate:
        raise AppError("response_not_eligible", "A response draft requires a completed candidate analysis", 409)
    if not analysis.agent_output:
        raise AppError("response_not_available", "The stored Agent output is unavailable", 409)
    try:
        inputs = _reply_input(session, analysis, run)
        output = AgentOutput.model_validate(analysis.agent_output)
        if (output.screening.is_candidate != analysis.is_candidate
                or (output.scoring.score if output.scoring else None) != analysis.lead_score
                or (output.scoring.decision.value.lower() if output.scoring else None) != analysis.decision):
            raise ValueError("Stored API projection does not match AgentOutput")
    except AppError:
        raise
    except (ValidationError, KeyError, TypeError, ValueError):
        raise AppError("invalid_analysis_output", "The stored Agent output cannot be used", 409) from None

    try:
        session.commit()  # Do not hold a database transaction during provider calls.
    except Exception:
        session.rollback()
        raise

    existing_usage_count = len(output.usage)
    try:
        updated_output = generate_suggested_reply(inputs, output)
        reply_attempts = _attempts_after(existing_usage_count, updated_output.usage)
        if not reply_attempts or reply_attempts[-1].outcome != "success":
            raise ProviderError("Reply did not produce a successful usage record", updated_output.usage)
        text = updated_output.suggested_reply
        if not text:
            raise ProviderError("Reply provider returned no draft", updated_output.usage)
    except ProviderError as exc:
        try:
            attempts = _attempts_after(existing_usage_count, exc.usage)
        except (ValidationError, ValueError, AttributeError, TypeError):
            attempts = []
        current = session.scalar(
            select(Analysis)
            .where(Analysis.id == analysis.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if current is None:
            session.rollback()
            raise AppError("not_found", "Lead does not exist", 404) from None
        latest_output = AgentOutput.model_validate(current.agent_output)
        _append_reply_usage(
            session, analysis=current, target_message_id=analysis.message_id, events=attempts
        )
        if attempts:
            current.agent_output = latest_output.model_copy(
                update={"usage": [*latest_output.usage, *attempts]}
            ).model_dump(mode="json")
        session.commit()
        raise AppError("response_generation_failed", "Could not generate a response draft", 502) from None
    except (ValidationError, ValueError):
        session.rollback()
        raise AppError("response_not_eligible", "This lead is not eligible for a response draft", 409) from None

    # Serialize the short persistence section, not the provider call. This
    # prevents concurrent explicit requests from overwriting each other's Usage.
    current = session.scalar(
        select(Analysis)
        .where(Analysis.id == analysis.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if current is None:
        raise AppError("not_found", "Lead does not exist", 404)
    existing = session.scalar(
        select(SuggestedResponse).where(SuggestedResponse.analysis_id == current.id)
    )
    if existing is None:
        existing = SuggestedResponse(
            analysis_id=current.id,
            response_text=text,
            status="pending",
            provider_mode=inputs.metadata.provider_mode,
            updated_at=utcnow(),
        )
        session.add(existing)
    elif regenerate:
        existing.response_text = text
        existing.status = "pending"
        existing.provider_mode = inputs.metadata.provider_mode
        existing.updated_at = utcnow()
    # If a non-regenerating call raced another request, retain the first draft
    # while still recording this call's provider usage and cost.
    latest_output = AgentOutput.model_validate(current.agent_output)
    current.agent_output = latest_output.model_copy(update={
        "suggested_reply": existing.response_text,
        "usage": [*latest_output.usage, *reply_attempts],
    }).model_dump(mode="json")
    _append_reply_usage(
        session, analysis=current, target_message_id=current.message_id, events=reply_attempts
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        # The call may have raced a draft insert on a database without row-level
        # locking. Preserve its billable Usage even if its draft loses the race.
        current = session.scalar(
            select(Analysis)
            .where(Analysis.id == analysis.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        saved = session.scalar(
            select(SuggestedResponse).where(SuggestedResponse.analysis_id == analysis.id)
        )
        if saved is None or current is None:
            raise AppError("response_conflict", "The response draft changed concurrently", 409) from None
        latest_output = AgentOutput.model_validate(current.agent_output)
        current.agent_output = latest_output.model_copy(update={
            "usage": [*latest_output.usage, *reply_attempts],
        }).model_dump(mode="json")
        _append_reply_usage(
            session, analysis=current, target_message_id=current.message_id, events=reply_attempts
        )
        session.commit()
        return response_out(saved)
    return response_out(existing)


def update_response(
    session: Session,
    user_id: UUID | str,
    analysis_id: UUID | str,
    patch: ResponsePatch,
) -> ResponseDraft:
    analysis = _owned_analysis(session, user_id, analysis_id)
    row = session.scalar(
        select(SuggestedResponse).where(SuggestedResponse.analysis_id == analysis.id)
    )
    if row is None:
        raise AppError("not_found", "Response draft does not exist", 404)
    changes = patch.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        raise AppError("validation_error", "Provide a non-null response text or status", 422)
    if "response_text" in changes:
        if not changes["response_text"].strip():
            raise AppError("validation_error", "Response text must not be blank", 422)
        row.response_text = changes["response_text"]
        if "status" not in changes:
            row.status = "edited"
    if "status" in changes:
        if changes["status"] == "edited" and "response_text" not in changes:
            raise AppError("validation_error", "Editing status requires response_text", 422)
        row.status = changes["status"]
    row.updated_at = utcnow()
    session.commit()
    return response_out(row)


def save_feedback(
    session: Session,
    user_id: UUID | str,
    analysis_id: UUID | str,
    payload: FeedbackInput,
) -> FeedbackOut:
    analysis = _owned_analysis(session, user_id, analysis_id)
    if analysis.status != "completed" or not analysis.is_candidate or analysis.decision not in {"review", "respond"}:
        raise AppError("feedback_not_eligible", "Feedback requires a completed review/respond lead", 409)

    row = session.scalar(select(LeadFeedback).where(LeadFeedback.analysis_id == analysis.id))
    normalized_comment = (payload.comment or "").strip() or None
    values = {"relevant": payload.relevant, "comment": normalized_comment,
              "updated_at": utcnow()}
    if row is None:
        row = LeadFeedback(analysis_id=analysis.id, **values)
        session.add(row)
    else:
        for name, value in values.items():
            setattr(row, name, value)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        row = session.scalar(select(LeadFeedback).where(LeadFeedback.analysis_id == analysis.id))
        if row is None:
            raise AppError("feedback_conflict", "Feedback changed concurrently", 409) from None
        for name, value in values.items():
            setattr(row, name, value)
        session.commit()
    return feedback_out(row)
