-- PostgreSQL reference for Alembic revision 0006_telegram_integration.py.
-- Apply migrations through Alembic; do not execute this file manually.
BEGIN;

CREATE TABLE telegram_chat_mappings (
	telegram_chat_id BIGINT NOT NULL,
	owner_user_id VARCHAR(36) NOT NULL,
	product_id VARCHAR(36) NOT NULL,
	enabled BOOLEAN NOT NULL,
	id VARCHAR(36) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (telegram_chat_id),
	FOREIGN KEY(owner_user_id) REFERENCES users (id),
	FOREIGN KEY(product_id) REFERENCES products (id)
);

CREATE INDEX ix_telegram_chat_mappings_owner_user_id ON telegram_chat_mappings (owner_user_id);

CREATE TABLE telegram_receipts (
	update_id BIGINT NOT NULL,
	telegram_chat_id BIGINT NOT NULL,
	telegram_message_id BIGINT NOT NULL,
	mapping_id VARCHAR(36) NOT NULL,
	message_id VARCHAR(36) NOT NULL,
	run_id VARCHAR(36) NOT NULL,
	source_metadata JSONB NOT NULL,
	agent_input JSONB,
	agent_output JSONB,
	id VARCHAR(36) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (telegram_chat_id, telegram_message_id),
	UNIQUE (update_id),
	FOREIGN KEY(mapping_id) REFERENCES telegram_chat_mappings (id),
	UNIQUE (message_id),
	FOREIGN KEY(message_id) REFERENCES messages (id),
	UNIQUE (run_id),
	FOREIGN KEY(run_id) REFERENCES analysis_runs (id)
);

CREATE TABLE telegram_deliveries (
	analysis_id VARCHAR(36) NOT NULL,
	state VARCHAR(20) NOT NULL,
	approved_text TEXT,
	approved_by VARCHAR(36),
	sent_message_id BIGINT,
	failure_category VARCHAR(50),
	delivery_uncertain BOOLEAN NOT NULL,
	draft_busy BOOLEAN NOT NULL,
	id VARCHAR(36) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (analysis_id),
	FOREIGN KEY(analysis_id) REFERENCES analyses (id),
	FOREIGN KEY(approved_by) REFERENCES users (id)
);

COMMIT;
