"""Upgrade real Alembic revisions, retain pre-ownership data, compare with the ORM."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text

from app.models import Base


def configuration(connection):
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.attributes["connection"] = connection
    return config


def test_upgrade_preserves_legacy_product_messages_and_telegram_receipts(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.connect() as connection:
        config = configuration(connection)
        command.upgrade(config, "0002")
        tables = MetaData()
        tables.reflect(connection)
        product_id, batch_id, message_id, run_id = (str(uuid4()) for _ in range(4))
        common = {"created_at": datetime.now(timezone.utc)}
        connection.execute(tables.tables["products"].insert(), {**common, "id": product_id,
            "name": "Legacy clinic", "description": "Existing data", "target_customer": "Pet owners",
            "problems_solved": [], "best_fit": [], "not_fit": [], "currency": "USD"})
        connection.execute(tables.tables["import_batches"].insert(), {**common, "id": batch_id,
            "community_name": "telegram:legacy", "checksum": "a" * 64, "filename": "telegram", "row_count": 1})
        connection.execute(tables.tables["messages"].insert(), {**common, "id": message_id,
            "batch_id": batch_id, "external_id": "1", "conversation_id": "chat", "author": "Alex",
            "content": "My dog needs care", "normalized_content": "my dog needs care", "timestamp": common["created_at"]})
        connection.execute(tables.tables["analysis_runs"].insert(), {**common, "id": run_id,
            "product_id": product_id, "batch_id": batch_id, "product_snapshot": {"name": "Legacy clinic"},
            "config_snapshot": {}, "idempotency_key": "legacy-run", "status": "queued", "total_count": 1,
            "processed_count": 0, "failed_count": 0})
        mapping_id, receipt_id = str(uuid4()), str(uuid4())
        connection.execute(tables.tables["telegram_chat_mappings"].insert(), {**common, "id": mapping_id,
            "telegram_chat_id": -100123, "owner_user_id": str(uuid4()), "product_id": product_id, "enabled": True})
        connection.execute(tables.tables["telegram_receipts"].insert(), {**common, "id": receipt_id,
            "mapping_id": mapping_id, "update_id": 1, "telegram_chat_id": -100123, "telegram_message_id": 1,
            "message_id": message_id, "run_id": run_id, "source_metadata": {"text": "My dog needs care"}})
        connection.commit()
        command.upgrade(config, "head")
        current = MetaData(); current.reflect(connection)
        product = connection.execute(select(current.tables["products"])).mappings().one()
        assert product["id"] == product_id and product["name"] == "Legacy clinic" and product["owner_user_id"] is None
        assert connection.execute(select(current.tables["messages"].c.content)).scalar() == "My dog needs care"
        assert connection.execute(select(current.tables["telegram_receipts"].c.id)).scalar() == receipt_id
        assert connection.execute(select(current.tables["analysis_runs"].c.product_id)).scalar() == product_id
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0004"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        connection.commit()
        command.downgrade(config, "0002")
        assert "owner_user_id" not in {c["name"] for c in inspect(connection).get_columns("products")}
        assert connection.execute(text("SELECT name FROM products")).scalar() == "Legacy clinic"
    engine.dispose()


def test_fresh_upgrade_and_downgrade(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    with engine.connect() as connection:
        config = configuration(connection)
        command.upgrade(config, "head")
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        connection.commit()
        command.downgrade(config, "base")
        assert inspect(connection).get_table_names() == ["alembic_version"]
    engine.dispose()


def test_manual_telegram_tables_are_not_overwritten(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'manual.db'}")
    with engine.connect() as connection:
        config = configuration(connection)
        command.upgrade(config, "0001")
        connection.execute(text("CREATE TABLE telegram_chat_mappings (id TEXT PRIMARY KEY)"))
        connection.execute(text("INSERT INTO telegram_chat_mappings VALUES ('preserve-me')"))
        connection.commit()
        with pytest.raises(RuntimeError, match="already exist"):
            command.upgrade(config, "head")
        assert connection.execute(text("SELECT id FROM telegram_chat_mappings")).scalar() == "preserve-me"
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0001"
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    engine.dispose()


def test_downgrade_refuses_to_destroy_owner_scoped_duplicate_imports(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'duplicate.db'}")
    with engine.connect() as connection:
        config = configuration(connection)
        command.upgrade(config, "head")
        batch = Table("import_batches", MetaData(), autoload_with=connection)
        common = {"created_at": datetime.now(timezone.utc), "community_name": "shared", "checksum": "a" * 64,
                  "filename": "test.csv", "row_count": 1}
        connection.execute(batch.insert(), [{**common, "id": str(uuid4())}, {**common, "id": str(uuid4())}])
        connection.commit()
        with pytest.raises(RuntimeError, match="Cannot downgrade"):
            command.downgrade(config, "0002")
        assert connection.execute(text("SELECT count(*) FROM import_batches")).scalar() == 2
        assert "users" in inspect(connection).get_table_names()
    engine.dispose()
