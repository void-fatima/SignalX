# Frontend contract sources

`failure-handling.openapi.json` is an unchanged snapshot of
`feat/failure-handling` at `96b7fa01da8dbadc1ba1af406938a218d7d351d2`.
Run `npm.cmd run generate:handoff` from `frontend` to regenerate
`lib/generated/failure-api.d.ts`. Do not hand-edit generated declarations.

The repository's `contracts/openapi.json` remains the source of
`lib/generated/api.d.ts` (`npm.cmd run generate:api`). It describes the backend
already integrated on main, including response review, feedback and analytics.
The handoff adds run retries, failure categories, source metadata and delivery
recovery; it does not include main's response/feedback/analytics endpoints.
`lib/api.ts` is an explicit compatibility adapter over these two generated
sources. Absent source/attempt metadata stays unavailable; it is not fabricated.

This snapshot does not install or merge a backend. Main and the handoff diverge
after `bea8e58af1bccf889698c9a4b6cf24852f279d18`, with incompatible migration
histories and different ownership/auth implementations. Backend reconciliation
belongs to Roham. A unified backend contract must be exported and these clients
regenerated when that work is integrated. Do not overwrite root OpenAPI with the
handoff snapshot: doing so would discard documented main endpoints.

All active browser clients use `NEXT_PUBLIC_API_URL` and `credentials: include`.
No session token is stored by frontend JavaScript. The handoff cookie name is
`signalx_session`; main's current cookie is `singnalx_session`. The retained
same-origin Telegram proxy is a legacy server adapter. If explicitly used with
the handoff, configure its `BACKEND_SESSION_COOKIE` to the appropriate cookie
name; the active browser client no longer depends on that bridge. The proxy
forwards an incoming Idempotency-Key unchanged.

Actual CORS, trusted Origin, cookie Secure/SameSite and HTTPS settings must match
the chosen frontend/backend hosts. This work does not change deployment settings.
Recovery against a backend missing the handoff endpoints reports an error.
Telegram recovery additionally requires the new delivery metadata before an
unconfirmed request can be replayed. There is no fallback to demo, no automatic
retry, and no browser call to Telegram Bot API.
