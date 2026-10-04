"""Setayesh's reply boundary; adapters must generate only grounded drafts."""
from typing import Protocol, Literal
from pydantic import BaseModel, Field
from app.agents.contracts import ProductSnapshot, TargetMessage, AnalysisResult, UsageEvent


class ReplyInput(BaseModel):
    product: ProductSnapshot
    target: TargetMessage
    context: list[TargetMessage] = Field(default_factory=list)
    analysis: AnalysisResult


class ReplyResult(BaseModel):
    response_text: str = Field(min_length=1, max_length=4000)
    provider_mode: Literal["mock", "real"]
    prompt_version: str
    limitations: list[str] = Field(default_factory=list)


class ReplyProvider(Protocol):
    def generate_reply(self, payload: ReplyInput) -> tuple[ReplyResult, list[UsageEvent]]: ...
