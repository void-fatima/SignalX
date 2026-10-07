"""Run-scoped operational analytics over persisted Backend/Agent records."""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Analysis, AnalysisRun, LeadFeedback, Usage
from app.schemas.analytics import AnalyticsOverview


def overview(session: Session, user_id: UUID | str, run_id: UUID | str) -> AnalyticsOverview:
    run = session.scalar(
        select(AnalysisRun).where(
            AnalysisRun.id == str(run_id),
            AnalysisRun.user_id == str(user_id),
        )
    )
    if run is None:
        raise AppError("not_found", "Run does not exist", 404)

    mode = run.config_snapshot.get("provider_mode")
    if mode not in {"mock", "real"}:
        raise AppError("invalid_run_provider", "Run provider metadata is invalid", 409)

    decisions = session.execute(
        select(Analysis.decision).where(
            Analysis.run_id == run.id,
            Analysis.status == "completed",
        )
    ).scalars().all()
    qualified = sum(decision == "respond" for decision in decisions)
    reviews = sum(decision == "review" for decision in decisions)

    usage = session.scalars(select(Usage).where(Usage.run_id == run.id)).all()
    known_costs: list[Decimal] = []
    unknown_usage_count = 0
    for event in usage:
        if event.provider_mode != mode:
            unknown_usage_count += 1
            continue
        if event.cost_status == "known" and event.cost_usd is not None:
            known_costs.append(Decimal(event.cost_usd))
        elif (event.cost_status == "mock" and event.provider_mode == "mock"
              and event.cost_usd is not None and Decimal(event.cost_usd) == 0):
            known_costs.append(Decimal(event.cost_usd))
        else:
            unknown_usage_count += 1

    # This is the sum of recorded costs. cost_complete tells consumers whether
    # it includes every attempt; per-unit totals stay null when it does not.
    total_cost = sum(known_costs, Decimal("0"))
    cost_complete = unknown_usage_count == 0
    cost_per_message = (
        total_cost / Decimal(run.total_count)
        if cost_complete and run.total_count > 0
        else None
    )
    cost_per_qualified = (
        total_cost / Decimal(qualified)
        if cost_complete and qualified > 0
        else None
    )

    feedback = session.execute(
        select(LeadFeedback.relevant)
        .join(Analysis, Analysis.id == LeadFeedback.analysis_id)
        .where(
            Analysis.run_id == run.id,
            Analysis.status == "completed",
            Analysis.decision.in_(["respond", "review"]),
        )
    ).scalars().all()
    surfaced_leads = qualified + reviews
    feedback_acceptance = (
        sum(value is True for value in feedback) / len(feedback)
        if feedback
        else None
    )
    feedback_coverage = (
        len(feedback) / surfaced_leads
        if surfaced_leads > 0
        else None
    )

    return AnalyticsOverview(
        run_id=UUID(run.id),
        provider_mode=mode,
        total_count=run.total_count,
        qualified_leads=qualified,
        review_count=reviews,
        failed_count=run.failed_count,
        total_cost_usd=total_cost,
        cost_per_message=cost_per_message,
        cost_per_qualified_lead=cost_per_qualified,
        unknown_usage_count=unknown_usage_count,
        cost_complete=cost_complete,
        feedback_acceptance=feedback_acceptance,
        feedback_coverage=feedback_coverage,
    )
