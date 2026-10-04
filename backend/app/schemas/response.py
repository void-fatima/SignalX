"""Draft response contracts; not yet mounted in the public API."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field


class ResponseDraft(BaseModel):
    analysis_id: UUID
    response_text: str = Field(min_length=1, max_length=4000)
    status: Literal["pending", "approved", "edited", "rejected"]
    provider_mode: Literal["mock", "real"]
    updated_at: datetime


class ResponsePatch(BaseModel):
    response_text: str | None = Field(default=None, min_length=1, max_length=4000)
    status: Literal["pending", "approved", "edited", "rejected"] | None = None


class FeedbackInput(BaseModel):
    relevant: bool
    comment: str | None = Field(default=None, max_length=2000)
