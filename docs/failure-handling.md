# Failure handling and explicit recovery

Implemented on `feat/failure-handling`. Agent contracts, scoring, prompts and provider
selection are unchanged. AvalAI remains the intended deployment provider; select it
through the existing environment configuration. Neither analysis nor delivery failures
switch providers. All automated verification uses offline HTTP fakes.

## Analysis states and recovery

Existing run states remain `queued`, `running`, `completed`, `partial`, `failed`,
`interrupted`. Queued/running represent pending/processing. An analysis stays
`completed` or `failed`; no competing status system was introduced. A failed row
has no score/decision and exposes `failure_category` plus a fixed, safe `reason`.
Categories: `provider_timeout`, `provider_failure`, `invalid_provider_output`,
`provider_refusal`, `internal_analysis_failure`. Exception text, provider bodies,
credentials and SQL parameters are not persisted as failure reasons or logged by
the generic API/worker error handlers.

`GET /api/v1/leads?run_id={id}&status=failed` lists failed results, including those
without a decision. Omit score/decision filters for this view. Default lead listing
retains its REVIEW/RESPOND behavior. Detail exposes source `csv` or `telegram`.

`POST /api/v1/analysis/runs/{id}/retry`, required `Idempotency-Key` (1–200 nonblank
characters), no body, returns HTTP 202 with RunOut. Both product and batch must be
owned by the authenticated user. Missing auth returns 401, another owner's run
404; invalid keys 422; active/completed runs or competing retry intents 409.

Only failed/partial/interrupted runs with unfinished results qualify. The original
run, product/config snapshots, source messages, Telegram receipt and successful
results stay intact. Failed results are updated under the same IDs; missing results
are inserted under the existing `(run_id, message_id)` uniqueness constraint.
This is a run-level action: it retries every failed/missing target in that run,
never its successful analyses. Telegram runs contain a single target.

Each accepted retry increments `attempt_no`, resets pending progress, and stores a
private audit entry with a hashed key, timestamp, previous status/attempt and failed
result IDs/categories. A replayed key returns the current run without requeueing,
even after a later failure. A new intentional retry needs a new key. Persist keys
across uncertain HTTP outcomes; do not automatically create new keys/retry loops.
All existing usage records survive; `run_attempt_no` identifies the analysis retry
generation, while provider `attempt_no` still identifies its bounded repair call.
Unknown tokens/cost remain null/unknown. An AgentOutput snapshot represents the
latest successful analysis; historical usage remains in `llm_usage`.

Workers conditionally claim queued runs. Heartbeat recovery marks stalled runs
interrupted, never queues them automatically. Conditional writes guard generation
and running state so late workers cannot overwrite a recovered/retried result.
Late returned usage is recorded under its original generation. No database lock
is held while calling a provider. A database outage cannot persist a new failure
immediately: the worker logs a fixed message, survives, and recovers interrupted
work after reconnection. No provider retry occurs until explicit user recovery.
Set heartbeat timeout above the provider's longest operation (including its one
allowed repair); otherwise an active request may be classified as interrupted.

## Human-approved Telegram delivery

Existing delivery states remain `not_sent`, `sending`, `sent`, `failed`. Approved
text is persisted before the HTTP request and returned in the authorized delivery
view. Failure category, HTTP status and `retry_after_at` are safe metadata. The
original analysis/AgentOutput never changes when sending. Sending does not invoke
qualification or draft generation.

Reuse `POST /api/v1/leads/{id}/telegram/reply` with `{ "text": "reviewed text" }`.
New clients should always supply `Idempotency-Key`. It is optional only for
compatibility with existing clients. The UI supplies one and retains it across
unknown network outcomes. The same key and text return current delivery state
without calling Telegram again, including a recorded failure. A changed text with
that key returns 409. A deliberate retry after a definite failure uses a new key.
Old clients without keys still get active-send and already-sent guards, but cannot
deduplicate a replay arriving after a definite failure.

Only explicit approval sends a message. A conditional database claim prevents two
concurrent approvals from sending simultaneously. Completed delivery cannot be
sent again (same text returns its existing state; different text returns 409).
429 cooldown is persisted and enforced by the server; no scheduled resend follows
the cooldown. Failed approved text and hashed attempt history remain available.

Timeouts, transport failures, invalid acknowledgements and server failures may
occur after Telegram accepted a send: they remain failed with
`delivery_uncertain=true`. They cannot be retried, even with a fresh key. A crash
or database failure after acceptance can leave `sending` persisted; it is also
blocked. A human must inspect the original chat and reconcile via the existing
operator procedure before allowing another send. There is no new automatic
reconciliation endpoint and no exactly-once delivery claim. Do not clear uncertainty
based only on elapsed time. Concurrent draft/send actions are also guarded.

## Migration and integration

Apply in order: `0001` initial → `0002` Telegram → `0003` ownership/sessions →
`0004` failure handling. Run the existing `alembic upgrade head` from backend
before starting the updated API/worker. Readiness now requires `0004`. Pause
workers during migration and coordinate deployment with Roham.

0004 adds only audit/metadata: run attempt/history; analysis failure category;
usage run attempt; Telegram failure HTTP status, cooldown, send history. Existing
rows default to attempt 1/empty history and retain their sources, approved text,
statuses and nullable costs. Older failures have a nullable category; new failures
use fixed messages. Historical data is not scrubbed by this additive migration:
Roham should review preexisting failure text/log retention separately if sensitive
exceptions were previously captured. Downgrade drops new metadata/history only;
do not downgrade while jobs/sends are active. SQLite upgrade/downgrade and ORM
comparison are tested; PostgreSQL deployment rehearsal remains a release check.

OpenAPI and generated frontend declarations include these additive backend fields
and the retry endpoint; the frozen AgentInput/AgentOutput are unchanged. API fixtures
include a failed run/result and Telegram failure with retained approved text.
The UI shows pending/processing, failure reasons, an explicit run retry, successful
recovery, a failed-results filter, and reviewed Telegram send/retry controls. It
blocks uncertain/sending/sent deliveries and displays cooldowns. Fatima owns UI
review; Roham owns migration, backend integration and operational reconciliation.

## Validation and handoff audit

Complete offline backend suite: **1172 passed**, 13 existing dependency warnings
(Starlette/httpx and Alembic configuration). Migration tests cover old records,
foreign keys, full upgrade/downgrade and ORM comparison. All nine shared backend
fixtures validate; exported OpenAPI equals the running application schema.
Frontend typecheck and production build pass. `pip check` passes; all 28 runtime
and 38 development lock pins and pyproject ranges match installed distributions.
No dependencies were changed. `git diff --check` passes. Changed-file secret
pattern review found no credentials or local environment files. Agent files,
contracts, scoring, prompts and both provider implementations have no diff.

Race checks include simultaneous worker claims, stale retry intents, repeated
keys after later failures, late worker usage, concurrent human approvals and
Telegram cooldown/uncertainty. Run writes and approval claims commit atomically
before external work. Database/HTTP failures never imply successful analysis
or sending. Source messages, snapshots, result IDs and previous usage survive
recovery. Browser controls disable double clicks and isolate state per lead.

Roham must coordinate migration 0004 with any parallel revisions, rehearse
PostgreSQL migration/deployment, configure heartbeat timeout, and retain the
human reconciliation procedure for uncertain delivery or stuck draft flags.
Fatima should review failure/retry copy and exercise browser end-to-end flows.
This change did not rehearse PostgreSQL or browser/Telegram live failure paths.
No live provider/Telegram calls, commits, pushes or deployments were performed.

## Files changed

- `README.md`
- `backend/app/api/routes/main.py`
- `backend/app/integrations/telegram/actions.py`
- `backend/app/integrations/telegram/models.py`
- `backend/app/integrations/telegram/routes.py`
- `backend/app/integrations/telegram/schemas.py`
- `backend/app/main.py`
- `backend/app/models/__init__.py`
- `backend/app/schemas/api.py`
- `backend/app/services/analysis_service.py`
- `backend/app/worker.py`
- `backend/migrations/versions/0004_failure_handling.py`
- `backend/tests/test_business_migrations.py`
- `backend/tests/test_business_setup.py`
- `backend/tests/test_failure_contracts.py`
- `backend/tests/test_failure_handling.py`
- `backend/tests/test_failure_migration.py`
- `backend/tests/test_telegram_flow.py`
- `contracts/examples/failed_lead.json`
- `contracts/examples/failed_run.json`
- `contracts/examples/failed_telegram_lead.json`
- `contracts/openapi.json`
- `docs/api-contract.md`
- `docs/failure-handling.md`
- `docs/telegram-integration.md`
- `frontend/app/leads/[id]/page.tsx`
- `frontend/app/leads/page.tsx`
- `frontend/app/runs/[id]/page.tsx`
- `frontend/components/RunRecovery.tsx`
- `frontend/components/TelegramDelivery.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/generated/api.d.ts`
