# Telegram frontend handoff

Implemented on 8 October 2026. The attached Telegram request superseded the older
three-screen IDE selection; overview, import validation and analysis progress
already exist in the UI base.

## Branches and commits

The starting checkout was `feat/signalx-opportunity-inbox-analysis-modal` at
`4340d98`. Auth, Product profile and the previous three screens are ancestors of
that checkout. The only pre-existing working-tree change was untracked `.vscode/`,
which was preserved. None of the requested new branch names already existed.

| Branch | Base | Commits created on this branch |
| --- | --- | --- |
| `feat/frontend-telegram-leads` | `feat/signalx-opportunity-inbox-analysis-modal` / `4340d98` | `b765a65`, `c5d0607`, `b6b7969` |
| `feat/frontend-telegram-reply` | `feat/frontend-telegram-leads` / `b6b7969` | `71f7349`, `98c4a64`, `b79180a` |
| `feat/frontend-telegram-delivery` | `feat/frontend-telegram-reply` / `b79180a` | `42a4042`, `b7a2305`, `342ac1c`, `8f74d52`, plus this documentation commit |

Commit subjects:

- `b765a65` — feat(telegram): add typed lead client and session bridge
- `c5d0607` — feat(telegram): render lead queue evidence and reply destination
- `b6b7969` — test(telegram): cover source metadata nulls and responsive review
- `71f7349` — feat(telegram): add explicit generation and session-scoped draft editing
- `98c4a64` — feat(telegram): submit exact reviewed text only on explicit approval
- `b79180a` — test(telegram): verify draft editing approval and origin protection
- `42a4042` — feat(telegram): reconcile delivery errors without automatic resend
- `b7a2305` — fix(telegram): isolate connected states and refine grounded message review
- `342ac1c` — fix(telegram): scope snapshots to accounts and label provider usage
- `8f74d52` — test(telegram): verify delivery recovery isolation and offline session forwarding

No backend branch was merged; no branch was pushed, amended, squashed or merged
into the default branch. The final checkout is `feat/frontend-telegram-delivery`.

## Contract and changed UI

Contract source: `feat/telegram-integration` at
`c60f9172279f05374d6d2330487a7e815fa64222`. Read its
`docs/telegram-integration.md`, `contracts/examples/telegram_lead.json`, Telegram
schemas, normalization, authentication dependencies, actions and Agent contracts.
The backend and `contracts/` remain unchanged. The schema-valid synthetic fixture
is copied into `frontend/tests/fixtures/telegram-lead.json` for offline tests only.

- `/leads?source=telegram`: dedicated authenticated Telegram list, pagination,
  current-page conversation search, source identity, scores, decisions, delivery
  state and links into review. The existing CSV inbox links to this list.
- `/leads/{lead_id}?source=telegram`: Telegram review using the existing sidebar,
  brand, top bar, product selector, tokens, icons, avatars and accessible dialog.
  Sender, chat, optional topic/username, UTC timestamp, original message,
  score/decision/reason, qualification, evidence and destination use API data.
- `components/telegram/`: source, grounded message highlighting, composer,
  delivery, provider usage, list and review components plus their scoped styling
  and workflow hook. Responsive review reflows into one column; the dense inbox
  table has keyboard-accessible horizontal scrolling.
- `components/leads/ReviewSession.tsx`: account-scoped, lead-keyed Telegram edits
  alongside the existing CSV draft/feedback state. Account changes clear local
  edits. Snapshots and late request responses are checked against lead/account.
- `lib/telegram.ts`: additive Telegram types/client instead of forcing the
  real/nullable AgentOutput snapshot into shared Mock-only AnalysisOut.
- `lib/api.ts`: retain error HTTP status/code/details without changing cookie
  authentication for existing features.

The original Telegram message number and the delivered reply's Telegram message
number are displayed separately. A Respond/Review decision never represents
human approval. Exact source quotes are highlighted only when their internal
message ID and text match the original. Actual Mock usage is labeled; unknown
costs remain unavailable. No draft, provider activity or delivery is fabricated.

## Authentication and operations

The existing login returns an HttpOnly cookie and excludes the opaque token from
JSON. The Telegram contract requires `Authorization: Bearer <backend-session>`.
Four narrow Next route handlers under `/api/v1/` bridge these existing sessions
on the server. Browser JavaScript never reads the session token or bot secrets.

Upstream paths and bodies are exactly:

- GET `/api/v1/integrations/telegram/leads?limit=20&offset=0`
- GET `/api/v1/leads/{lead_id}/telegram`
- POST `/api/v1/leads/{lead_id}/telegram/suggested-reply`, `{"regenerate":false}`
  for explicit initial generation, true only for explicit regeneration
- POST `/api/v1/leads/{lead_id}/telegram/reply`, `{"text":"<exact reviewed text>"}`
  only after an explicit Approve & Reply click

POST handlers require the app's Origin, validate the body, preserve approved
whitespace, send one upstream request and return the documented error envelope.
No automatic transport retry occurs. Requests and responses use no-store.

Server configuration:

| Variable | Meaning |
| --- | --- |
| `BACKEND_API_URL` | Server-only backend base including `/api/v1`; falls back to `NEXT_PUBLIC_API_URL`, then `http://localhost:8000/api/v1` |
| `BACKEND_SESSION_COOKIE` | Existing backend cookie name; defaults to `singnalx_session` |
| `APP_ORIGIN` | Canonical frontend origin, recommended behind HTTPS/reverse proxies; otherwise inferred from the request host and protocol |

The existing backend session cookie must reach the app host at `/api/v1`.
Localhost ports share the hostname, so the current local cookie flow can bridge
without exposing tokens. Separate production frontend/backend hostnames need
an approved same-host authentication/proxy arrangement; a backend-only cookie
is not readable by the frontend server. Missing sessions return 401 and a sign-in
action, not fake connected data. Missing upstream Telegram endpoints show an
explicit feature-unavailable state. `demo=1` never calls connected Telegram APIs.

## Drafts and delivery

Null suggestions require Generate suggested reply. Approval stays disabled until
a nonblank draft is reviewed. Save/Cancel controls retain local edits in the
current browser UI session; Save does not claim backend draft persistence.
Refresh preserves edits. Regeneration is blocked while editing. Explicit
generation/regeneration never invokes the send endpoint.

Sending has a synchronous request lock, disabled controls, an account/lead session
latch and a non-sensitive sessionStorage guard. Confirmed success shows the
returned Telegram reply ID. Sending, uncertain delivery, failed delivery,
confirmed success and draft_busy block another send. After 502, conflicts or
transport errors, the UI reads authoritative detail using GET only. If success
cannot be confirmed, it instructs the user to check the original Telegram thread
and contact the backend operator for reconciliation. A page reload cannot clear
that tab's ambiguous-send guard.

The contract supplies no audited resend authorization/reset operation, so this
UI exposes no resend control or client-side way to clear the guard. Draft edits
are kept in memory, not persisted across full page reloads. DeliveryOut does not
include approved_text; after reload, a stored suggestion is not proof of the
exact text previously delivered. The original Telegram thread remains the
authoritative place to inspect delivered text.

## Verification

Final checks, run from `frontend/` unless stated otherwise:

| Command | Result |
| --- | --- |
| `npm.cmd run typecheck` | Passed |
| `npm.cmd run build` | Passed; production Next build includes all four bridge routes |
| `npm.cmd test` | 103 passed in 51.8 seconds using headless Microsoft Edge; 32 Telegram tests and 71 existing tests |
| `git diff --check` | Passed; Git reports only the repository's LF/CRLF normalization notices |

No lint script or lint configuration is provided by the repository, so no
separate lint check ran. Backend tests and OpenAPI regeneration did not run
because backend/schema/generated contracts were unchanged. An initial `npm`
PowerShell invocation was blocked by execution policy; all checks completed
using `npm.cmd` without changing that policy.

Tests cover metadata/evidence/nulls, explicit generation, provider failure,
Save/Cancel/refresh, exact edited approval, classification not sending,
duplicate prevention, all delivery states, uncertainty, draft conflicts, 502
detail refresh, network failure, reload guards, late responses after lead
switching, account changes, Mock/unknown costs and origin/body validation.
The server bridge is exercised against a local fake HTTP server with a synthetic
session. Its test environment forces `BACKEND_API_URL` to that offline server.
No real Telegram message or paid provider generation was used.

Desktop (1753×1160) and mobile (390×844) review screenshots were generated and
visually inspected; both retain readable controls and avoid page overflow.
The queue was checked at both widths. Artifacts are ignored local files under
`frontend/test-results/`: `telegram-review-1753.png`,
`telegram-review-390.png`, `telegram-source-1753.png`, and
`telegram-source-390.png`. Screenshot data comes from synthetic mock HTTP.

## Remaining backend/deployment gates

Roham must integrate the Telegram routes with the existing audited session and
product-ownership adapters, apply Telegram tables through the approved migration
chain, configure the actual worker/provider/bot/webhook and verify production
ownership, HTTPS/cookies and delivery. The contract branch explicitly leaves
these gates incomplete. Its existence does not demonstrate a deployed working
integration. This frontend work preserves that gap and does not deploy, modify
Agent/scoring/prompts/connector behavior or automatically send messages.
