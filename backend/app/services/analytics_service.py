"""Persistence-facing interface; pure cost/evaluation logic lives in agents."""
from typing import Protocol
from uuid import UUID
from app.schemas.analytics import AnalyticsOverview


class AnalyticsService(Protocol):
    def overview(self, user_id: UUID, run_id: UUID) -> AnalyticsOverview: ...
