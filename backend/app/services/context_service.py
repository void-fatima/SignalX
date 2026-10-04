from sqlalchemy import select
from app.models import Message
from app.agents.contracts import TargetMessage


def load_messages(session, batch_id: str) -> list[TargetMessage]:
    messages = session.scalars(select(Message).where(Message.batch_id == batch_id).order_by(Message.timestamp, Message.external_id)).all()
    return [TargetMessage(**{key: getattr(m, key) for key in TargetMessage.model_fields}) for m in messages]
