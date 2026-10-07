from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.contracts import AgentOutput, ContextMessage
from app.integrations.telegram.normalization import TelegramMessage


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatMappingInput(StrictModel):
    product_id: UUID
    telegram_chat_id: int = Field(strict=True, gt=-(2**63), lt=0)


class ChatMappingOut(StrictModel):
    id: UUID
    product_id: UUID
    telegram_chat_id: int
    enabled: bool


class ApprovedReply(StrictModel):
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Reply must not be blank")
        return value


class DraftRequest(StrictModel):
    regenerate: bool = False


class DeliveryOut(StrictModel):
    status: Literal["not_sent", "sending", "sent", "failed"] = "not_sent"
    telegram_message_id: int | None = None
    failure_category: str | None = None
    delivery_uncertain: bool = False
    draft_busy: bool = False


class TelegramLeadOut(StrictModel):
    id: UUID
    run_id: UUID
    product_id: UUID
    message_id: UUID
    source: Literal["telegram"] = "telegram"
    original_message: TelegramMessage
    context: list[ContextMessage] = Field(default_factory=list)
    analysis: AgentOutput
    delivery: DeliveryOut


class TelegramLeadPage(StrictModel):
    items: list[TelegramLeadOut]
    total: int
    limit: int
    offset: int


class WebhookOut(StrictModel):
    ok: bool = True
    status: Literal["ignored", "unmapped", "queued", "duplicate"]
