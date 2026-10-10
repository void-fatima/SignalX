from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Source = Literal["brave", "greenhouse", "lever", "places"]
Signal = Literal["not_evaluated", "relevant_company", "possible_need", "explicit_buying_intent"]

class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    product_id: UUID
    source: Source
    keywords: str = Field(min_length=1, max_length=200)
    industry: str = Field(default="", max_length=100)
    location: str = Field(default="", max_length=150)
    country: str = Field(default="", pattern=r"^(?:[A-Z]{2})?$")
    board_slug: str = Field(default="", pattern=r"^(?:[a-zA-Z0-9_-]{1,80})?$")
    limit: int = Field(default=10, ge=1, le=20)

    @field_validator("keywords", "industry", "location")
    @classmethod
    def plain_input(cls, value):
        if any(ord(c) < 32 for c in value):
            raise ValueError("Use plain single-line search text")
        return value

    @model_validator(mode="after")
    def source_inputs(self):
        if self.source in {"greenhouse", "lever"}:
            if not self.board_slug:
                raise ValueError("Job search requires one company's board slug")
            if self.country or self.industry:
                raise ValueError("Job APIs support location/keyword filters, not country or industry filters")
        elif self.board_slug:
            raise ValueError("Board slug applies only to job sources")
        if self.source == "places" and not self.location:
            raise ValueError("Local business search requires a location")
        return self

class DiscoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Source
    source_id: str = Field(max_length=200)
    title: str = Field(max_length=240)
    url: str = Field(max_length=2000)
    excerpt: str = Field(max_length=800)
    location: str = Field(default="", max_length=200)
    signal: Signal = "not_evaluated"
    explanation: str = "Source match only; buying intent has not been verified."

class SearchOut(BaseModel):
    id: str
    product_id: str
    source: Source
    status: Literal["pending", "completed", "failed"]
    results: list[DiscoveryResult]
    cached: bool = False
    request_count: int
    estimated_cost_usd: None = None
    cost_status: Literal["unknown"] = "unknown"
    error_code: str | None = None
    error: str | None = None
    created_at: datetime

class SaveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search_id: UUID
    source_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("source_ids")
    @classmethod
    def distinct(cls, value):
        if len(set(value)) != len(value) or any(not v or len(v) > 200 for v in value):
            raise ValueError("Select unique source IDs from this search")
        return value

class ProspectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    product_id: str
    search_id: str
    source: Source
    source_id: str
    title: str
    url: str
    excerpt: str
    location: str
    signal: Signal
    explanation: str
    qualification_status: str
    qualification_usage: list[dict]
    qualification_error: str | None
    created_at: datetime

class SourceStatus(BaseModel):
    source: Source
    configured: bool
    message: str

class SourcesOut(BaseModel):
    items: list[SourceStatus]
