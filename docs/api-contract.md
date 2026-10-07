# singnalX API contract

The authoritative machine contract is contracts/openapi.json, exported from
backend Pydantic models. Base URL: http://localhost:8000/api/v1. See /docs on the
API server for interactive documentation. JSON uses snake_case, UUID strings,
UTC times and lowercase enums. Lists return items/total/limit/offset (20, max 100).
Errors are {"error":{"code":"...","message":"...","details":[]}}.

Implemented endpoints: health/ready; POST/GET/PATCH products; POST imports;
GET messages; POST analysis/runs (202, required Idempotency-Key);
GET analysis/runs/{id}; GET leads (run_id required, decision/min_score filters);
GET leads/{id}; POST/PATCH leads/{id}/response; PUT leads/{id}/feedback;
POST /auth/register; POST /auth/login;
POST /auth/logout; GET /auth/me. Authenticated product, import, message, run,
lead, response, and feedback operations are scoped to the current user.
Same-user reuse of an idempotency key with a
different payload returns 409. Import accepts multipart file + community_name.
Import checksum and idempotency uniqueness are scoped per user.

Authentication uses an HttpOnly, SameSite=Lax opaque session cookie. The token
is stored only as a digest in the database and revoked on logout. The frontend
must send requests with credentials included. Set `AUTH_COOKIE_SECURE=true`
behind HTTPS; local HTTP uses the default `false`.

Runs snapshot the product and config. processed_count includes failed messages;
successful count is processed_count minus failed_count. Screened-out analyses
have null signals/score/intent, decision ignore. Failed analyses have decision
null. Analysis output reports the provider mode used by its run (`mock` or `real`).
Mock usage has null token counts and zero cost_usd with cost_status=mock. Real
usage preserves unknown token counts and cost as null; missing telemetry is not
inferred by the API.
Prompt and scoring versions are nullable when their corresponding Agent stage
did not run; Backend does not invent versions for screened-out messages.

Context is offline, limited to the same batch/conversation, up to three preceding
and two following messages (parent prioritized), maximum five messages and 8000
characters. Product edits never change old run snapshots.

Response drafts are generated only on explicit POST and remain pending until a
human changes their status. Approval only persists status; the Backend never sends
community messages. Existing drafts are reused unless `?regenerate=true` is
requested. Reply attempts are persisted in `llm_usage`; the draft and feedback
remain available from GET leads/{id}. Feedback is one current vote per analysis.
Never show mock output as a real AI result. Run-level analytics is not part of this
branch yet.

Pre-authentication rows remain unowned after migration 0002 and are inaccessible
through authenticated API routes. Auth endpoints and ownership enforcement are
implemented in the local backend. Fatima owns auth UI/guards and must use
credentialed API requests. Setayesh owns Agent logic; the agreed internal
AgentInput/AgentOutput schema is separate from this public OpenAPI contract.
The shared Agent fixtures are in `contracts/examples/agent-input.json` and
`agent-output.json`. The output is a schema example; its score is not a verified
execution result. `message.id` and evidence/context IDs use internal message IDs;
Backend maps `reply_to_external_id` to the matching same-conversation internal ID.

Regenerate from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe scripts/export_openapi.py
Set-Location frontend
npm run generate:api
```
