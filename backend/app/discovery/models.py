from sqlalchemy import ForeignKey, String, Text, Integer, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base, Record, UTCDateTime, json_type
from datetime import datetime

class DiscoverySearch(Record, Base):
    __tablename__ = "discovery_searches"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_discovery_user_key"), Index("ix_discovery_user_created", "user_id", "created_at"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    source: Mapped[str] = mapped_column(String(20))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    fingerprint: Mapped[str] = mapped_column(String(64))
    query: Mapped[dict] = mapped_column(json_type)
    product_snapshot: Mapped[dict] = mapped_column(json_type)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    results: Mapped[list] = mapped_column(json_type, default=list)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

class DiscoveryProspect(Record, Base):
    __tablename__ = "discovery_prospects"
    __table_args__ = (UniqueConstraint("user_id", "product_id", "source", "source_id", name="uq_discovery_prospect_source"), Index("ix_discovery_prospect_owner", "user_id", "created_at"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    search_id: Mapped[str] = mapped_column(ForeignKey("discovery_searches.id"))
    source: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(240))
    url: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(200))
    signal: Mapped[str] = mapped_column(String(30), default="not_evaluated")
    explanation: Mapped[str] = mapped_column(Text)
    qualification_status: Mapped[str] = mapped_column(String(20), default="not_requested")
    qualification_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    qualification_usage: Mapped[list] = mapped_column(json_type, default=list)
    qualification_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_output: Mapped[dict | None] = mapped_column(json_type, nullable=True)

class DiscoveryBudget(Base):
    __tablename__ = "discovery_budgets"
    source: Mapped[str] = mapped_column(String(20), primary_key=True)
    last_request_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    window_started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    request_count: Mapped[int] = mapped_column(Integer, default=0)
