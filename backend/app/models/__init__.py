from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, Integer, Boolean, DateTime, Numeric, ForeignKey, UniqueConstraint, Index, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utcnow():
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """SQLite loses timezone metadata; restore UTC consistently on reads."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Timestamp requires a timezone")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


json_type = JSON().with_variant(JSONB(), "postgresql")


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class User(Record, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)
    email: Mapped[str] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(String(255))


class UserSession(Record, Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_user_id", "user_id"),
        UniqueConstraint("token_digest", name="uq_user_sessions_token_digest"),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    token_digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Product(Record, Base):
    __tablename__ = "products"
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    target_customer: Mapped[str] = mapped_column(Text)
    problems_solved: Mapped[list] = mapped_column(json_type)
    best_fit: Mapped[list] = mapped_column(json_type)
    not_fit: Mapped[list] = mapped_column(json_type)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3))


class ImportBatch(Record, Base):
    __tablename__ = "import_batches"
    __table_args__ = (UniqueConstraint("user_id", "community_name", "checksum", name="uq_import_user_community_checksum"),)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    community_name: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(255))
    checksum: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer)


class Message(Record, Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("batch_id", "external_id"), Index("ix_messages_context", "batch_id", "conversation_id", "timestamp"))
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"))
    external_id: Mapped[str] = mapped_column(String(200))
    conversation_id: Mapped[str] = mapped_column(String(200))
    author: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    normalized_content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    reply_to_external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)


class AnalysisRun(Record, Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        Index("ix_runs_queue", "status", "created_at"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_runs_user_idempotency_key"),
    )
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"))
    product_snapshot: Mapped[dict] = mapped_column(json_type)
    config_snapshot: Mapped[dict] = mapped_column(json_type)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    total_count: Mapped[int] = mapped_column(Integer)
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Analysis(Record, Base):
    __tablename__ = "analyses"
    __table_args__ = (UniqueConstraint("run_id", "message_id"), Index("ix_leads", "run_id", "decision", "lead_score"))
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"))
    status: Mapped[str] = mapped_column(String(20))
    is_candidate: Mapped[bool] = mapped_column(Boolean)
    screening_reason: Mapped[str] = mapped_column(Text)
    signals: Mapped[dict | None] = mapped_column(json_type, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    need: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_signal: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lead_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(json_type, default=list)
    context_message_ids: Mapped[list] = mapped_column(json_type, default=list)
    limitations: Mapped[list] = mapped_column(json_type, default=list)
    # Preserve the complete Agent contract output (including suggested_reply and
    # all evidence/usage fields) independently from the API's read projection.
    agent_output: Mapped[dict | None] = mapped_column(json_type, nullable=True)
    scoring_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_mode: Mapped[str] = mapped_column(String(20), default="mock")


class Usage(Record, Base):
    __tablename__ = "llm_usage"
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey("analyses.id"), nullable=True)
    stage: Mapped[str] = mapped_column(String(30))
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    request_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_mode: Mapped[str] = mapped_column(String(20), default="mock")
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(14, 8), nullable=True)
    cost_status: Mapped[str] = mapped_column(String(20), default="mock")
    price_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20))
