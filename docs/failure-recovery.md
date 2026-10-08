# Failure recovery and retries

This backend recovery work is additive on the current mainline after migration
`0006`. It does not change AgentInput/AgentOutput, the native `analyze_agent`
worker path, auth/ownership, successful AgentOutput snapshots, usage semantics,
or Telegram receipts. It does not import the reference branch's migration `0004`.

## Analysis runs

`POST /api/v1/analysis/runs/{run_id}/retry` is an authenticated, owner-scoped,
manual retry. It requires `Idempotency-Key` (1–200 characters). Only runs in
`failed`, `partial`, or `interrupted` states can be retried. The endpoint stores
only the SHA-256 digest in `retry_history`, returns the same run for a repeated
key, and returns 409 if a different retry is already active. It increments
`attempt_no`, clears stale run state and queues failed or missing message results.

Completed results are skipped. A failed result is updated in place, preserving
its Analysis ID and references. Complete successful AgentOutput snapshots and
successful Usage rows are kept. Every Usage row records its `run_attempt_no`;
when a provider call returns after its worker lost the lease, its usage is saved
against the old attempt without allowing its result to overwrite newer work.
`GET /api/v1/leads?run_id=<UUID>&status=failed` lists failed rows. Failure
categories are a fixed allowlist: `provider_timeout`, `provider_failure`,
`invalid_provider_output`, `provider_refusal`, and
`internal_analysis_failure`. Provider exception text, raw responses and
credentials are not written into run/analysis failure fields.

The worker claims queued work with a conditional status/attempt update. Before
persisting each result and final status it checks that the run is still running
at the same attempt. Heartbeat recovery moves stale work to `interrupted`;
manual retry creates the next attempt. Provider calls run outside DB
transactions. `HEARTBEAT_TIMEOUT_SECONDS` must allow at least two configured
provider request timeouts plus 30 seconds for the Agent's repair request.

## Telegram delivery

Reply sending remains a separate human-approved action; analysis never sends a
message. Reply POST accepts an optional `Idempotency-Key` for compatibility with
existing callers. A new key is needed for a deliberate retry. Only key and text
hashes are recorded in `send_history`; the original key is not stored there.
Same key and same text returns the current delivery without a second HTTP call;
same key with changed text returns 409. A row-level compare-and-swap claim
prevents concurrent sends.

HTTP 429 stores the HTTP status and `retry_after_at`; another send is blocked
until that time. Confirmed failures can then be retried with a new key. Uncertain
sends stay blocked for human review because Telegram and PostgreSQL cannot share
a transaction. There is no automatic resend or automatic message sending.

## Migration 0007

Revision `0007` follows the verified `0006` head and adds exactly seven columns
to existing tables; it creates no table:

| Table | Columns |
| --- | --- |
| `analysis_runs` | `attempt_no`, `retry_history` |
| `analyses` | `failure_category` |
| `llm_usage` | `run_attempt_no` |
| `telegram_deliveries` | `failure_http_status`, `retry_after_at`, `send_history` |

Defaults backfill existing records (`attempt_no=1`, empty histories,
`run_attempt_no=1`); existing analysis, usage, and Telegram rows remain in place.
The migration's SQLite regression verifies upgrade and downgrade preserve prior
data. PostgreSQL validation runs the complete migration chain in an isolated
test schema and exercises worker claim, stale-worker fencing, and retry.

To run the PostgreSQL check, set `TEST_POSTGRES_URL` to a dedicated database
whose name contains `test`; the test creates and removes only a unique schema
inside that database. Do not point it at a production or shared development
database.
