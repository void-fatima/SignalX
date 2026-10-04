from datetime import datetime
from decimal import Decimal
from typing import Generic, TypeVar, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProductInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    target_customer: str = Field(min_length=1, max_length=2000)
    problems_solved: list[str] = Field(default_factory=list)
    best_fit: list[str] = Field(default_factory=list)
    not_fit: list[str] = Field(default_factory=list)
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")


class ProductOut(ProductInput, ORM):
    id: UUID
    created_at: datetime


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    target_customer: str | None = Field(default=None, min_length=1, max_length=2000)
    problems_solved: list[str] | None = None
    best_fit: list[str] | None = None
    not_fit: list[str] | None = None
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")


class CSVRow(BaseModel):
    external_id: str = Field(min_length=1, max_length=200)
    conversation_id: str = Field(min_length=1, max_length=200)
    author: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=4000)
    timestamp: AwareDatetime
    reply_to_external_id: str | None = Field(default=None, max_length=200)


class BatchOut(ORM):
    id: UUID
    community_name: str
    filename: str
    checksum: str
    row_count: int
    created_at: datetime


class ImportOut(BaseModel):
    batch: BatchOut
    count: int
    duplicate: bool
    warnings: list[dict]


class MessageOut(ORM):
    id: UUID
    batch_id: UUID
    external_id: str
    conversation_id: str
    author: str
    content: str
    timestamp: datetime
    reply_to_external_id: str | None


class RunInput(BaseModel):
    product_id: UUID
    batch_id: UUID


class RunOut(ORM):
    id: UUID
    product_id: UUID
    batch_id: UUID
    status: Literal["queued", "running", "completed", "partial", "failed", "interrupted"]
    total_count: int
    processed_count: int
    failed_count: int
    error: str | None
    heartbeat_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    config_snapshot: dict


from app.agents.contracts import Signals, Evidence


class AnalysisOut(ORM):
    id: UUID
    run_id: UUID
    message_id: UUID
    status: Literal["completed", "failed"]
    is_candidate: bool
    screening_reason: str
    signals: Signals | None
    intent: str | None
    need: str | None
    budget_signal: str | None
    lead_score: int | None = Field(ge=0, le=100)
    decision: Literal["ignore", "review", "respond"] | None
    decision_reason: str | None
    reason: str
    evidence: list[Evidence]
    context_message_ids: list[UUID]
    limitations: list[str]
    scoring_version: str
    prompt_version: str
    provider_mode: Literal["mock"]


class LeadDetail(BaseModel):
    analysis: AnalysisOut
    message: MessageOut
    context: list[MessageOut]
    product_snapshot: dict
    offline_context: bool = True


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict] = Field(default_factory=list)


class ErrorOut(BaseModel):
    error: ErrorBody
