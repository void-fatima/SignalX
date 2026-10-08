"""Telegram persistence tables; migration 0006 adds their ownership FKs."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, Record, UTCDateTime, json_type


class TelegramChatMapping(Record, Base):
    __tablename__ = "telegram_chat_mappings"
    # One configured bot per deployment: a chat has exactly one business/owner.
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class TelegramReceipt(Record, Base):
    __tablename__ = "telegram_receipts"
    __table_args__ = (UniqueConstraint("telegram_chat_id", "telegram_message_id"),)
    update_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger)
    telegram_message_id: Mapped[int] = mapped_column(BigInteger)
    mapping_id: Mapped[str] = mapped_column(ForeignKey("telegram_chat_mappings.id"))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), unique=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), unique=True)
    source_metadata: Mapped[dict] = mapped_column(json_type)
    agent_input: Mapped[dict | None] = mapped_column(json_type, nullable=True)
    agent_output: Mapped[dict | None] = mapped_column(json_type, nullable=True)


class TelegramDelivery(Record, Base):
    __tablename__ = "telegram_deliveries"
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), unique=True)
    state: Mapped[str] = mapped_column(String(20), default="not_sent")
    approved_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sent_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    failure_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_after_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    send_history: Mapped[list] = mapped_column(json_type, default=list)
    delivery_uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    draft_busy: Mapped[bool] = mapped_column(Boolean, default=False)
