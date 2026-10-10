# Frontend contract sources

## Active unified contract

All active API and Telegram client types now come from `contracts/openapi.json`
through `lib/generated/api.d.ts`. The verified backend is
`feature/backend-failure-recovery@072a4dc72cb634b8c1e86d0ba73a50be501c8f09`, merged
by PR #7 into `origin/main@7629e1b59337c87e3b98875ad2a87ac45c4fe1ee`.
Its backend tree is unchanged by this frontend work. It includes analysis retry,
failure categories, server attempts, approved Telegram text and recovery metadata,
while retaining response, feedback and analytics endpoints.

Regenerate from repository root with the backend Python and
`scripts/export_openapi.py`, then run `npm.cmd run generate:api` from `frontend`.
The export normalizes the Python-dependent HTTP 422 description. Runtime/export
and generated-type equality were checked. Do not hand-edit generated declarations.

Generic LeadDetail does not declare a source discriminator in the unified schema.
The client keeps optional legacy source metadata without fabricating it. The
separate Telegram endpoint explicitly identifies its source. Nullable attempt or
recovery metadata stays unavailable; no default attempt is invented.

## Archived handoff

`failure-handling.openapi.json` remains an unchanged historical snapshot of
`feat/failure-handling@96b7fa01da8dbadc1ba1af406938a218d7d351d2`.
`npm.cmd run generate:handoff` reproduces `lib/generated/failure-api.d.ts`, which
is retained for historical comparison and is no longer imported by active clients.
That older branch lacked main's response/feedback/analytics endpoints and had a
different migration/ownership history. Never overwrite the unified export with it.
The final backend uses mainline migration 0007; the old handoff migration 0004 was
not imported.

## Sessions and delivery

Browser clients use `NEXT_PUBLIC_API_URL` and `credentials: include`. JavaScript
stores no session token. Main's HttpOnly cookie is `singnalx_session`; the archived
handoff used `signalx_session`. The retained same-origin Telegram proxy is a
legacy server adapter. Configure `BACKEND_SESSION_COOKIE` if deliberately using
that adapter with a different cookie name. It forwards Idempotency-Key unchanged.

Only validated `delivery.status === "sent"` displays Sent. Sending and uncertainty
block new delivery. Pending scoped sessionStorage intents retain the exact approved
text and key. Explicit checks replay that key; definitive acknowledgement permits
another deliberate retry with a fresh key. Failed acknowledgements must contain
valid recovery metadata and the matching approved text before clearing an intent.
Cooldown expiry only enables a control. An authenticated backend reconciliation
endpoint is available for an owner who has manually checked an uncertain send;
it never sends or retries a message. Client support is not part of this backend
change. No browser calls Telegram's Bot API directly.

See [the final Failure Handling audit](../../docs/frontend-failure-final-audit.md)
for connected local HTTP tests and release limitations. Browser acceptance tests
use actual FastAPI routes with isolated SQLite and controlled provider/Telegram
transports. Production PostgreSQL, HTTPS, CORS/Origin/cookie configuration and live
worker/deployment checks remain separate release gates.
