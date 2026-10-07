"""Commit normalized Message + the existing queue job atomically, without AI."""
import hashlib

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from app.agents.screening import normalize
from app.agents.providers.base import ProviderError
from app.core.config import settings
from app.core.errors import AppError
from app.integrations.telegram.models import TelegramChatMapping, TelegramReceipt
from app.integrations.telegram.normalization import TelegramMessage
from app.models import ImportBatch, Message, Product
from app.schemas.api import RunInput
from app.services.analysis_service import create_run


def _existing(session, source):
    receipt = session.scalar(select(TelegramReceipt).where(or_(TelegramReceipt.update_id == source.update_id,
        (TelegramReceipt.telegram_chat_id == source.chat_id) & (TelegramReceipt.telegram_message_id == source.message_id))))
    if receipt and (receipt.telegram_chat_id != source.chat_id or receipt.telegram_message_id != source.message_id):
        raise AppError("telegram_update_conflict", "Update identifier conflicts with an existing message", 409)
    return receipt


def ingest(session, source: TelegramMessage) -> str:
    try:
        if _existing(session, source):
            return "duplicate"
        mapping = session.scalar(select(TelegramChatMapping).where(
            TelegramChatMapping.telegram_chat_id == source.chat_id, TelegramChatMapping.enabled.is_(True)).with_for_update())
        if mapping is None:
            return "unmapped"
        product = session.get(Product, mapping.product_id)
        if product is None or product.owner_user_id != mapping.owner_user_id:
            raise AppError("telegram_ownership_unavailable", "Mapped product ownership must be verified before ingestion", 503)
        if settings().provider_mode != "real":
            raise AppError("real_provider_required", "Telegram analysis requires explicitly configured real provider mode", 503)
        namespace = "telegram:" + mapping.id + ":" + source.conversation_id
        checksum = hashlib.sha256(namespace.encode()).hexdigest()
        batch = session.scalar(select(ImportBatch).where(ImportBatch.community_name == namespace, ImportBatch.checksum == checksum))
        if batch is None:
            batch = ImportBatch(owner_user_id=mapping.owner_user_id, community_name=namespace, filename="telegram", checksum=checksum, row_count=0)
            session.add(batch)
            session.flush()
        elif batch.owner_user_id != mapping.owner_user_id:
            raise AppError("telegram_ownership_unavailable", "Mapped conversation ownership must be verified before ingestion", 503)
        message = Message(batch_id=batch.id, external_id=source.external_id, conversation_id=source.conversation_id,
            author=(source.sender_username or source.sender_display_name)[:200], content=source.text,
            normalized_content=normalize(source.text), timestamp=source.timestamp,
            reply_to_external_id=str(source.reply_to_message_id) if source.reply_to_message_id else None)
        session.add(message)
        batch.row_count += 1
        session.flush()
        key = "telegram:v1:" + hashlib.sha256(f"{source.chat_id}:{source.message_id}".encode()).hexdigest()
        run = create_run(session, RunInput(product_id=mapping.product_id, batch_id=batch.id), key, commit=False)
        # A stream run analyzes only this receipt's target, not the whole growing batch.
        run.total_count = 1
        session.add(TelegramReceipt(update_id=source.update_id, telegram_chat_id=source.chat_id,
            telegram_message_id=source.message_id, mapping_id=mapping.id, message_id=message.id,
            run_id=run.id, source_metadata=source.model_dump(mode="json")))
        session.commit()
        return "queued"
    except IntegrityError:
        session.rollback()
        if _existing(session, source):
            return "duplicate"
        # A concurrent first-message batch creation may have won. Ask Telegram to redeliver.
        raise AppError("telegram_ingestion_conflict", "Concurrent ingestion; redelivery is safe", 503) from None
    except (OperationalError, ProgrammingError):
        session.rollback()
        raise AppError("telegram_storage_unavailable", "Telegram schema/storage must be ready before ingestion", 503) from None
    except ProviderError:
        session.rollback()
        raise AppError("real_provider_unavailable", "Configure the real Agent provider before Telegram ingestion", 503) from None
