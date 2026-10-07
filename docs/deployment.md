# Backend Deployment — Roham

The current real-provider target is AvalAI. The Agent-side AvalAI test was
reported successful; that does not yet verify the deployed Backend Worker,
PostgreSQL persistence, or production hosting. No cloud host/project is
configured in this repository yet.

## Provider settings

Set the following server-side variables on both the API and Worker services:

```text
PROVIDER_MODE=real
LLM_PROVIDER=avalai
OPENAI_BASE_URL=https://api.avalai.ir/v1
OPENAI_MODEL=gpt-5.6-luna
OPENAI_API_KEY=<AvalAI secret>
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_OUTPUT_TOKENS=2000
```

`PROVIDER_MODE=real` makes the Backend construct `AgentInput` with real mode;
`LLM_PROVIDER=avalai` selects the Agent's AvalAI-compatible Responses provider.
The API needs the key for explicitly requested reply drafts, and the Worker
needs it for analysis runs. Store `OPENAI_API_KEY` in the host secret manager;
never commit it or expose it to frontend variables. Keep the migration job free
of provider credentials.

Do not set Gemini variables for this deployment. The Agent code may retain its
separate provider adapter, but AvalAI is the agreed production selection.
Leave price variables unset unless the current AvalAI rates and price version
have been verified; unknown cost must stay null.

## Backend services

Use a persistent PostgreSQL service and the `backend/Dockerfile` image for both
API and Worker. Build context is `backend/`. Run `alembic upgrade head` as a
release/migration job before starting either service. Start the API with the
image's default command, and start exactly one Worker with:

```text
python -m app.worker
```

Set the host's internal PostgreSQL URL as `DATABASE_URL` on the migration, API,
and Worker services. Expose the API on the port expected by the selected host;
the API readiness endpoint is `/api/v1/ready`. Keep PostgreSQL private.

For an HTTPS deployment, set `AUTH_COOKIE_SECURE=true`. Use `lax` when the UI
and API are same-site. For separate sites, configure `AUTH_COOKIE_SAMESITE=none`,
`AUTH_COOKIE_SECURE=true`, and the exact frontend origin in `CORS_ORIGINS`; prefer
same-site custom domains where possible. The frontend Auth UI/API wiring remains
Fatima's task.

## Release gate

After choosing and configuring a host, verify migration, API readiness, Worker
startup, restart recovery, user isolation, and a real `Worker → Agent → PostgreSQL`
run. Inspect persisted screening, qualification, score, decision, evidence,
usage, versions, and nullable cost. Keep the test bounded to a small approved
dataset; no automatic outreach is enabled. Do not call the deployment complete
until the host reports a successful release and the persisted run is verified.
