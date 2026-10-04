"""Initial Mock foundation schema, frozen independently from ORM models."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = depends_on = None


def upgrade():
    json = sa.JSON().with_variant(JSONB(), "postgresql")
    def create(name, columns, *constraints):
        op.create_table(name, sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), *columns, *constraints)
    def col(name, type, nullable=False, fk=None):
        return sa.Column(name, type, *([sa.ForeignKey(fk)] if fk else []), nullable=nullable)
    S, T, I, D = sa.String, sa.Text, sa.Integer, sa.DateTime(timezone=True)
    create("products", [col("name", S(200)), col("description", T), col("target_customer", T),
        col("problems_solved", json), col("best_fit", json), col("not_fit", json), col("price", sa.Numeric(12, 2), True), col("currency", S(3))])
    create("import_batches", [col("community_name", S(200)), col("filename", S(255)), col("checksum", S(64)), col("row_count", I)], sa.UniqueConstraint("community_name", "checksum"))
    create("messages", [col("batch_id", S(36), fk="import_batches.id"), *[col(n, S(200)) for n in ["external_id", "conversation_id", "author"]],
        col("content", T), col("normalized_content", T), col("timestamp", D), col("reply_to_external_id", S(200), True)], sa.UniqueConstraint("batch_id", "external_id"))
    create("analysis_runs", [col("product_id", S(36), fk="products.id"), col("batch_id", S(36), fk="import_batches.id"),
        col("product_snapshot", json), col("config_snapshot", json), col("idempotency_key", S(200)), col("status", S(20)),
        *[col(n, I) for n in ["total_count", "processed_count", "failed_count"]], *[col(n, D, True) for n in ["heartbeat_at", "started_at", "finished_at"]], col("error", T, True)], sa.UniqueConstraint("idempotency_key"))
    create("analyses", [col("run_id", S(36), fk="analysis_runs.id"), col("message_id", S(36), fk="messages.id"),
        col("status", S(20)), col("is_candidate", sa.Boolean), col("screening_reason", T), col("signals", json, True),
        col("intent", S(100), True), col("need", T, True), col("budget_signal", S(50), True), col("lead_score", I, True),
        col("decision", S(20), True), col("decision_reason", T, True), col("reason", T),
        *[col(n, json) for n in ["evidence", "context_message_ids", "limitations"]], col("scoring_version", S(50)), col("prompt_version", S(50)), col("provider_mode", S(20))], sa.UniqueConstraint("run_id", "message_id"))
    create("llm_usage", [col("run_id", S(36), fk="analysis_runs.id"), col("message_id", S(36), True, "messages.id"), col("analysis_id", S(36), True, "analyses.id"),
        col("stage", S(30)), col("attempt_no", I), col("request_id", S(200), True), col("model", S(100)), col("provider_mode", S(20)),
        col("input_tokens", I, True), col("output_tokens", I, True), col("cost_usd", sa.Numeric(14, 8), True), col("cost_status", S(20)),
        col("price_version", S(50)), col("latency_ms", I), col("outcome", S(20))])
    for name, table, columns in [
        ("ix_messages_context", "messages", ["batch_id", "conversation_id", "timestamp"]),
        ("ix_runs_queue", "analysis_runs", ["status", "created_at"]),
        ("ix_leads", "analyses", ["run_id", "decision", "lead_score"]),
        ("ix_llm_usage_run_id", "llm_usage", ["run_id"])]:
        op.create_index(name, table, columns)


def downgrade():
    for name in ["llm_usage", "analyses", "analysis_runs", "messages", "import_batches", "products"]:
        op.drop_table(name)
