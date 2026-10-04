from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


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


class ScreeningResult(BaseModel):
    is_candidate: bool
    reason: str


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
