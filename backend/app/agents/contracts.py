from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, AwareDatetime, model_validator


class Decision(str, Enum):
    IGNORE = "IGNORE"
    REVIEW = "REVIEW"
    RESPOND = "RESPOND"


class AgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ProductInput(AgentModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    target_customer: str = Field(min_length=1)


class MessageInput(AgentModel):
    id: str = Field(min_length=1)
    content: str = Field(min_length=1, max_length=4000)
    author: str = Field(min_length=1)
    timestamp: AwareDatetime
    conversation_id: str = Field(min_length=1)
    reply_to_message_id: str | None = None


class ContextMessage(AgentModel):
    """Caller supplies only messages from the target's batch/conversation."""
    id: str = Field(min_length=1)
    content: str = Field(min_length=1, max_length=4000)
    author: str = Field(min_length=1)
    timestamp: AwareDatetime


class AgentMetadata(AgentModel):
    run_id: str = Field(min_length=1)
    provider_mode: Literal["mock", "real"]


class AgentInput(AgentModel):
    product: ProductInput
    message: MessageInput
    context_messages: list[ContextMessage] = Field(default_factory=list, max_length=5)
    metadata: AgentMetadata


class EvidenceItem(AgentModel):
    message_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class QualificationResult(AgentModel):
    intent: str
    need: str
    purchase_intent: float = Field(ge=0, le=1)
    product_fit: float = Field(ge=0, le=1)
    need_strength: float = Field(ge=0, le=1)
    urgency: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    response_opportunity: float = Field(ge=0, le=1)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ScoringResult(AgentModel):
    score: int = Field(ge=0, le=100, strict=True)
    decision: Decision


class UsageInfo(AgentModel):
    """One provider attempt. Unknown measurements remain null, not assumed zero."""
    stage: str = Field(min_length=1)
    attempt_no: int = Field(default=1, ge=1, strict=True)
    provider_mode: Literal["mock", "real"]
    model: str | None = Field(default=None, min_length=1)
    input_tokens: int | None = Field(default=None, ge=0, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, strict=True)
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    cost_status: Literal["known", "unknown", "mock"] = "unknown"
    price_version: str | None = Field(default=None, min_length=1)
    latency_ms: int | None = Field(default=None, ge=0, strict=True)
    outcome: str = Field(default="unknown", min_length=1)

    @model_validator(mode="after")
    def consistent_cost(self) -> "UsageInfo":
        if self.cost_status == "unknown" and self.estimated_cost is not None:
            raise ValueError("Unknown cost must be null")
        if self.cost_status == "known" and self.estimated_cost is None:
            raise ValueError("Known cost requires an estimated_cost")
        if self.cost_status == "mock" and (self.provider_mode != "mock" or self.estimated_cost != Decimal("0")):
            raise ValueError("Mock cost requires mock mode and explicit zero cost")
        return self


class ScreeningResult(AgentModel):
    is_candidate: bool
    reason: str


class AgentOutput(AgentModel):
    model_config = ConfigDict(frozen=True)

    screening: ScreeningResult
    qualification: QualificationResult | None = None
    scoring: ScoringResult | None = None
    decision_reason: str | None = None
    prompt_version: str | None = None
    scoring_version: str | None = None
    usage: list[UsageInfo] = Field(default_factory=list)
    suggested_reply: str | None = None
    decision_reason: str | None = None
    prompt_version: str | None = None
    scoring_version: str | None = None


# Existing pipeline contracts are retained for compatibility. The new public
# AgentInput/AgentOutput interface above does not require HTTP or database models.


class ProductSnapshot(BaseModel):
    name: str
    description: str
    target_customer: str
    problems_solved: list[str] = Field(default_factory=list)
    best_fit: list[str] = Field(default_factory=list)
    not_fit: list[str] = Field(default_factory=list)
    price: str | None = None
    currency: str = "USD"


class TargetMessage(BaseModel):
    id: str
    external_id: str
    conversation_id: str
    author: str
    content: str
    timestamp: datetime
    reply_to_external_id: str | None = None


class RunConfig(BaseModel):
    provider_mode: str = "mock"
    context_max_chars: int = Field(default=8000, ge=0, le=20000)
    offline_context: bool = True


class Signals(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    purchase_intent: float = Field(ge=0, le=1)
    product_fit: float = Field(ge=0, le=1)
    need_strength: float = Field(ge=0, le=1)
    urgency: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    response_opportunity: float = Field(ge=0, le=1)


class Evidence(BaseModel):
    message_id: str
    quote: str


class Qualification(BaseModel):
    signals: Signals
    intent: str
    need: str
    budget_signal: str = "unknown"
    reason: str
    evidence: list[Evidence]
    limitations: list[str] = Field(default_factory=list)
    needs_human_review: bool = False


class UsageEvent(BaseModel):
    stage: str = "qualification"
    attempt_no: int = 1
    model: str = "deterministic-mock-v1"
    provider_mode: str = "mock"
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: str | None = "0"
    cost_status: str = "mock"
    price_version: str = "mock_v1"
    latency_ms: int = 0
    outcome: str = "success"


class AnalysisResult(BaseModel):
    status: str = "completed"
    is_candidate: bool
    screening_reason: str
    signals: Signals | None = None
    intent: str | None = None
    need: str | None = None
    budget_signal: str | None = None
    lead_score: int | None = None
    decision: str | None = "ignore"
    decision_reason: str | None = None
    reason: str
    evidence: list[Evidence] = Field(default_factory=list)
    context_message_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    scoring_version: str = "score_v1"
    prompt_version: str = "qualify_v1"
    provider_mode: str = "mock"


AgentOutput.model_rebuild()
