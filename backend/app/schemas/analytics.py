"""Draft dashboard contract; unknown measurements remain null, never fake zeros."""
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field


class AnalyticsOverview(BaseModel):
    run_id: UUID
    provider_mode: Literal["mock", "real"]
    total_count: int = Field(ge=0)
    qualified_leads: int = Field(ge=0)
    review_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    total_cost_usd: Decimal | None
    cost_per_message: Decimal | None
    cost_per_qualified_lead: Decimal | None
    unknown_usage_count: int = Field(ge=0)
    cost_complete: bool
    feedback_acceptance: float | None = Field(ge=0, le=1)
    feedback_coverage: float | None = Field(ge=0, le=1)
