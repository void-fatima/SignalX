"""Strict normal-text ingestion; no interpretation of community instructions."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class TelegramMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: Literal["telegram"] = "telegram"
    update_id: int = Field(ge=0, lt=2**63)
    chat_id: int = Field(gt=-(2**63), lt=0)
    message_id: int = Field(gt=0, lt=2**63)
    chat_type: Literal["group", "supergroup"]
    chat_title: str | None = None
    sender_id: int = Field(gt=0, lt=2**63)
    sender_username: str | None = None
    sender_display_name: str
    text: str = Field(min_length=1, max_length=4000)
    timestamp: AwareDatetime
    reply_to_message_id: int | None = Field(default=None, gt=0, lt=2**63)
    message_thread_id: int | None = Field(default=None, gt=0, lt=2**63)

    @property
    def external_id(self) -> str:
        return str(self.message_id)

    @property
    def conversation_id(self) -> str:
        return f"telegram:{self.chat_id}:topic:{self.message_thread_id or 0}"


def normalize_update(update: object) -> TelegramMessage | None:
    if not isinstance(update, dict) or type(update.get("update_id")) is not int:
        return None
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    sender, chat = message.get("from"), message.get("chat")
    if (not isinstance(sender, dict) or sender.get("is_bot") is not False
            or not isinstance(chat, dict) or chat.get("type") not in ("group", "supergroup")
            or "sender_chat" in message or not isinstance(message.get("text"), str)
            or not message["text"].strip()):
        return None
    # Service updates never enter the analysis queue, even with unusual text.
    if any(key in message for key in ("new_chat_members", "left_chat_member", "new_chat_title",
            "new_chat_photo", "delete_chat_photo", "group_chat_created", "supergroup_chat_created",
            "migrate_to_chat_id", "migrate_from_chat_id", "pinned_message", "forum_topic_created",
            "forum_topic_closed", "forum_topic_reopened", "video_chat_started", "video_chat_ended")):
        return None
    try:
        date = message["date"]
        if type(date) is not int or date < 0 or type(chat.get("id")) is not int or not chat["id"]:
            return None
        name = " ".join(v for key in ("first_name", "last_name")
                        if isinstance(v := sender.get(key), str) and v.strip()).strip()
        parent = message.get("reply_to_message")
        reply_id = None
        if isinstance(parent, dict):
            parent_chat = parent.get("chat", chat)
            if isinstance(parent_chat, dict) and parent_chat.get("id") == chat["id"]:
                reply_id = parent.get("message_id")
        return TelegramMessage(update_id=update["update_id"], chat_id=chat["id"],
            message_id=message["message_id"], chat_type=chat["type"], chat_title=chat.get("title"),
            sender_id=sender["id"], sender_username=sender.get("username"),
            sender_display_name=name or str(sender["id"]), text=message["text"],
            timestamp=datetime.fromtimestamp(date, timezone.utc), reply_to_message_id=reply_id,
            message_thread_id=message.get("message_thread_id"))
    except (ValueError, KeyError, TypeError, OverflowError, OSError):
        # No truncated evidence: >4000-character input is unsupported by AgentInput.
        return None
