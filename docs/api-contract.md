# singnalX API contract

The authoritative machine contract is contracts/openapi.json, exported from
backend Pydantic models. Base URL: http://localhost:8000/api/v1. See /docs on the
API server for interactive documentation. JSON uses snake_case, UUID strings,
UTC times and lowercase enums. Lists return items/total/limit/offset (20, max 100).
Errors are {"error":{"code":"...","message":"...","details":[]}}.

Implemented foundation: health/ready; POST/GET/PATCH products; POST imports;
GET messages; POST analysis/runs (202, required Idempotency-Key);
GET analysis/runs/{id}; GET leads (run_id required, decision/min_score filters);
GET leads/{id}. Same idempotency key with a different payload returns 409.
The import endpoint accepts multipart file + community_name. Import belongs to a
community; the selected product is bound when creating the run.

Business Setup adds POST `/auth/register`, `/auth/login`, `/auth/logout` and
GET `/auth/me`. All product/import/message/run/lead operations require a session
and are scoped to the owner. BrowserSession is an HttpOnly cookie; BackendSession
supports trusted bearer clients. HTTP keys and import deduplication are per-user.
See [migration and authentication details](business-setup.md). Frozen Agent
contracts remain unchanged; generated API types are synchronized with this branch.

Runs snapshot the product and config. processed_count includes failed messages;
successful count is processed_count minus failed_count. Screened-out analyses
have null signals/score/intent, decision ignore. Failed analyses have decision
null. Mock output has provider_mode=mock. Mock usage has null real token counts and zero
cost_usd with cost_status=mock. This is not real provider telemetry.

Context is offline, limited to the same batch/conversation, up to three preceding
and two following messages (parent prioritized), maximum five messages and 8000
characters. Product edits never change old run snapshots.

Reply, feedback and analytics endpoints in the architecture are later-stage
work, outside the bootstrap scope. Do not show a generated reply as a real AI result.

Auth and ownership are implemented by the Business Setup follow-up. Roham owns
their final integration and deployment; Fatima owns frontend review. Existing
historical rows require verified ownership backfill before they become visible.

Regenerate from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe scripts/export_openapi.py
Set-Location frontend
npm run generate:api
```
