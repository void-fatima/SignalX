import csv
import hashlib
import io
from datetime import timezone
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models import ImportBatch, Message
from app.schemas.api import CSVRow
from app.agents.screening import normalize
from app.core.errors import AppError


def import_csv(session, content: bytes, filename: str, community_name: str, user_id: str):
    community_name = community_name.strip()
    if not community_name or len(community_name) > 200:
        raise AppError("invalid_csv", "Community name must contain 1–200 characters")
    if len(content) > 5 * 1024 * 1024:
        raise AppError("invalid_csv", "CSV exceeds 5 MB")
    checksum = hashlib.sha256(content).hexdigest()
    existing = session.scalar(select(ImportBatch).where(
        ImportBatch.user_id == user_id,
        ImportBatch.community_name == community_name,
        ImportBatch.checksum == checksum,
    ))
    if existing:
        return existing, True, []
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
        required = set(CSVRow.model_fields) - {"reply_to_external_id"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames) or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise AppError("invalid_csv", "Missing or duplicate CSV headers", details=[{"required": sorted(required)}])
        rows, errors, seen = [], [], set()
        for number, row in enumerate(reader, start=2):
            if number > 501:
                raise AppError("invalid_csv", "CSV exceeds 500 messages")
            if None in row:
                errors.append({"row": number, "field": "row", "message": "Extra columns"})
                continue
            try:
                data = {k: (v.strip() if v is not None else v) for k, v in row.items()}
                data["reply_to_external_id"] = data.get("reply_to_external_id") or None
                parsed = CSVRow.model_validate(data)
                if parsed.external_id in seen:
                    errors.append({"row": number, "field": "external_id", "message": "Duplicate external_id"})
                seen.add(parsed.external_id)
                rows.append(parsed)
            except ValidationError as exc:
                errors.extend({"row": number, "field": str(e["loc"][0]), "message": e["msg"]} for e in exc.errors())
        if errors or not rows:
            raise AppError("invalid_csv", "Entire CSV rejected; no messages imported", details=errors)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise AppError("invalid_csv", "CSV must be valid UTF-8", details=[{"message": str(exc)}]) from exc
    warnings = []
    by_external = {r.external_id: r for r in rows}
    for number, row in enumerate(rows, start=2):
        if row.reply_to_external_id:
            parent = by_external.get(row.reply_to_external_id)
            if parent is None or parent.conversation_id != row.conversation_id:
                warnings.append({"row": number, "field": "reply_to_external_id", "message": "Parent missing or belongs to another conversation; excluded from context"})
    batch = ImportBatch(user_id=user_id, community_name=community_name,
        filename=(filename or "messages.csv")[:255], checksum=checksum, row_count=len(rows))
    try:
        session.add(batch)
        session.flush()
        for row in rows:
            values = row.model_dump()
            values["timestamp"] = row.timestamp.astimezone(timezone.utc)
            session.add(Message(batch_id=batch.id, normalized_content=normalize(row.content), **values))
        session.commit()
    except IntegrityError:
        session.rollback()
        batch = session.scalar(select(ImportBatch).where(
            ImportBatch.user_id == user_id,
            ImportBatch.community_name == community_name,
            ImportBatch.checksum == checksum,
        ))
        if batch:
            return batch, True, warnings
        raise
    return batch, False, warnings
