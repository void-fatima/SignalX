"""Exercise 0003 -> 0004 with existing failures, usage and approved delivery text."""
from datetime import datetime, timezone
from uuid import uuid4

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, MetaData, select, text

from app.models import Base
from test_business_migrations import configuration


def test_failure_upgrade_preserves_original_records_and_backfills_attempts(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'failure-migration.db'}")
    with engine.connect() as connection:
        config = configuration(connection)
        command.upgrade(config, "0003")
        tables = MetaData(); tables.reflect(connection)
        ids = {key: str(uuid4()) for key in ("product", "batch", "message", "run", "analysis", "usage", "delivery")}
        common = {"created_at": datetime.now(timezone.utc)}
        def insert(table, identity, **values):
            connection.execute(tables.tables[table].insert(), {**common, "id": ids[identity], **values})
        insert("products", "product", name="Legacy business", description="Original product",
            target_customer="Customers", problems_solved=[], best_fit=[], not_fit=[], currency="USD")
        insert("import_batches", "batch", community_name="original", filename="sample.csv", checksum="a" * 64, row_count=1)
        insert("messages", "message", batch_id=ids["batch"], external_id="1", conversation_id="same",
            author="Alex", content="Original source", normalized_content="original source", timestamp=common["created_at"])
        insert("analysis_runs", "run", product_id=ids["product"], batch_id=ids["batch"], product_snapshot={},
            config_snapshot={}, idempotency_key="original-run", status="failed", total_count=1, processed_count=1, failed_count=1, error="Failed")
        insert("analyses", "analysis", run_id=ids["run"], message_id=ids["message"], status="failed",
            is_candidate=True, screening_reason="processing_error", reason="Original failure", evidence=[], context_message_ids=[],
            limitations=[], scoring_version="score_v1", prompt_version="qualify_real_v1", provider_mode="real")
        insert("llm_usage", "usage", run_id=ids["run"], message_id=ids["message"], analysis_id=ids["analysis"],
            stage="qualification", attempt_no=1, model="gpt-5.6-luna", provider_mode="real", cost_status="unknown",
            price_version="unknown", latency_ms=5, outcome="timeout")
        insert("telegram_deliveries", "delivery", analysis_id=ids["analysis"], state="failed", approved_text="Human approval",
            failure_category="timeout", delivery_uncertain=True, draft_busy=False)
        connection.commit()
        command.upgrade(config, "head")
        current = MetaData(); current.reflect(connection)
        run = connection.execute(select(current.tables["analysis_runs"])).mappings().one()
        delivery = connection.execute(select(current.tables["telegram_deliveries"])).mappings().one()
        usage = connection.execute(select(current.tables["llm_usage"])).mappings().one()
        assert run["id"] == ids["run"] and run["status"] == "failed" and run["attempt_no"] == 1 and run["retry_history"] == []
        assert delivery["approved_text"] == "Human approval" and delivery["delivery_uncertain"] and delivery["send_history"] == []
        assert usage["cost_usd"] is None and usage["run_attempt_no"] == 1
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0004"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        connection.commit()
        command.downgrade(config, "0003")
        assert connection.execute(text("SELECT approved_text FROM telegram_deliveries")).scalar() == "Human approval"
        assert connection.execute(text("SELECT content FROM messages")).scalar() == "Original source"
    engine.dispose()
