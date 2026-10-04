"""Roham implements ownership checks and draft/feedback persistence here."""
from typing import Protocol
from uuid import UUID
from app.schemas.response import ResponseDraft, ResponsePatch, FeedbackInput


class ResponseService(Protocol):
    # Reuse existing draft unless regeneration is explicitly requested.
    def generate(self, user_id: UUID, analysis_id: UUID, *, regenerate: bool = False) -> ResponseDraft: ...
    # Approval changes stored status only. Never sends community messages.
    def update(self, user_id: UUID, analysis_id: UUID, patch: ResponsePatch) -> ResponseDraft: ...
    # One current feedback vote per analysis; repeated votes replace it.
    def feedback(self, user_id: UUID, analysis_id: UUID, payload: FeedbackInput) -> None: ...
