# Deployment handoff — Roham

The local compose.yaml is the starting point. Online hosting is not configured
or performed. Choose the container host and database together before adding
provider-specific deployment files. The Gemini Agent branch is integrated locally;
production variables must be added to the selected host before a live deployment.

For Gemini, configure these variables on both the API and Worker services:

```text
PROVIDER_MODE=real
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
GEMINI_API_KEY=<host secret>
```

Also set `GEMINI_TIMEOUT_SECONDS=30` and `GEMINI_MAX_OUTPUT_TOKENS=2000` unless
the deployment needs different bounded values. Keep `GEMINI_API_KEY` in the
host's secret manager; do not commit it or place it in frontend variables. The
API needs the key for on-demand reply drafts, and the Worker needs it for runs.
Database migration service does not need any provider key. Keep the backend
`PROVIDER_MODE=real`; the Agent's provider selector is independently
`LLM_PROVIDER=gemini`. Usage costs remain unknown/null unless verified pricing
is configured by the Agent contract.

Backend auth and ownership routes now exist locally. Before the online release,
connect the auth UI/API client, verify credentialed browser requests, run migration
0002 on PostgreSQL, and check two-user isolation there. Also require migrations
before API/worker startup; one worker; persistent PostgreSQL; HTTPS and secure
session settings; origin/CORS configuration; server-only secrets; explicit
provider mode; health/readiness checks; known model rates and bounded paid usage;
and restart smoke tests. Build the frontend with the reachable API URL, not localhost.

For same-site frontend/API hosts, `AUTH_COOKIE_SAMESITE=lax` is sufficient. If
the frontend and API use different sites, configure `AUTH_COOKIE_SAMESITE=none`
and `AUTH_COOKIE_SECURE=true` over HTTPS, and set `CORS_ORIGINS` to the exact
frontend origin. Browsers may restrict third-party cookies; prefer same-site
custom domains or a same-origin proxy when that restriction applies.

Confirm the URL lifetime and competition requirements from the actual rules.
The revised plan targets first online Mock slice at end of Day 2. This file is a
handoff plan, not a deployable host configuration or a deployed URL.
