# Business / Product Setup

The existing `Product` is the business-conditioned offering. There is no separate
Business table. A user may create multiple profiles, each with `name`,
`description` and `target_customer`; existing optional product fields are retained.
Profiles are not seeded automatically and the form starts empty.

## Authentication and ownership

This branch previously contained only AuthService protocols and disabled login
forms. It now implements that interface using `users` and `auth_sessions`.
Passwords use PBKDF2-SHA256 with 600,000 iterations and independent random salts.
Opaque random sessions expire after 24 hours, are stored only as SHA256 digests,
and are revoked on logout. Password hashes and session tokens never appear in
JSON responses. Browser sessions use an HttpOnly, SameSite=Lax cookie with Secure
enabled by default. No bearer token is stored in frontend storage.

Register/login at `/api/v1/auth/register` and `/api/v1/auth/login` (POST JSON
`email`, `password`), inspect `/api/v1/auth/me` (GET), and logout with
`/api/v1/auth/logout` (POST, 204). The browser sends cookies using
`credentials: include`. Existing trusted BackendSession bearer adapters remain
available to server clients. OpenAPI documents both authentication mechanisms.
Unsafe browser requests must have an Origin in `CORS_ORIGINS`.

For local HTTP development only, explicitly set `AUTH_COOKIE_SECURE=false` in
the launching process. Production must use HTTPS and `AUTH_COOKIE_SECURE=true`.
Frontend and API must be same-site (for example app.example.com/api.example.com,
or an API reverse proxy). Cross-site hosting needs a reviewed cookie/CSRF design;
do not simply disable SameSite. Configure exact `CORS_ORIGINS`, not `*`.
Roham should configure shared login/register rate limiting at the hosting boundary
and reconcile any independent auth branch before merging this implementation.
Password reset and account administration are outside this MVP.

`POST /api/v1/products`, `GET /api/v1/products`, `GET /api/v1/products/{id}` and
`PATCH /api/v1/products/{id}` now require a session. Creation assigns the owner
server-side; request fields cannot assign or transfer ownership. Foreign IDs and
absent IDs both return 404. Blank/whitespace-only required fields are rejected.
Lists and totals are scoped to the signed-in user, with existing pagination.
Deletion is omitted so analysis references remain intact.

Imports are also owner-scoped: CSV deduplication uses owner, community and checksum.
Messages, run creation, run status, lead lists and lead details check ownership.
HTTP idempotency keys are namespaced by user so different users cannot collide.
The existing queue and atomic import semantics are retained.

Telegram user actions use the shared session dependency. The existing optional
`app.state.telegram_auth_service` and `telegram_product_access` adapters remain
compatible; an adapter cannot bypass database product ownership. New chat mappings
and ingestion verify the mapped product belongs to that owner. Existing mappings,
receipts, draft generation and human-approved sends keep their current structure.
No new sending or provider behavior is introduced.

## Runtime Agent integration

AnalysisRun already has a product FK and an immutable product snapshot. Creation
loads the selected, owned profile rather than a demo constant. Queued runs keep
the original snapshot when a profile is edited. Lead -> AnalysisRun -> Product
remains the authoritative relationship. The existing Telegram worker adapter
constructs the frozen AgentInput product with exactly `id`, `name`, `description`,
`target_customer`. CSV continues to use its existing legacy pipeline/snapshot.
The Agent contract, providers, prompts, scoring and decisions are unchanged.
Real analysis responses are now accepted by the legacy API's `provider_mode`
field as well as mock responses; this is an API schema correction, not an Agent
contract change. Unknown costs retain their existing null semantics.

## Migration ordering and existing data

Run migrations during a maintenance window with the API and worker stopped and
a verified backup. No production database was changed while implementing this.
From `backend`, using its virtual environment:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Ordering is **0001 -> 0002 -> 0003**:

1. 0001 is the unchanged foundation schema.
2. 0002 freezes the three Telegram tables from the prior SQL handoff.
3. 0003 adds users/sessions, nullable product/import owners, owner indexes/FKs,
   and owner-scoped import uniqueness. No existing rows or snapshots are deleted
   or relabeled. Readiness now expects revision 0003 and current mapped columns.

If the Telegram `schema.sql` handoff has already been applied manually, migration
0002 deliberately stops instead of overwriting tables. Roham must compare all
three existing tables, columns, types, nullability, foreign keys, unique
constraints and indexes against 0002 and verify revision 0001. Only if they are
equivalent may he explicitly adopt that schema with `alembic stamp 0002`, then
upgrade to head. Partial or incompatible schemas require a reviewed migration;
do not stamp over a mismatch.

Historical products/imports remain `owner_user_id=NULL`, invisible to authenticated
API users. They are never assigned to the first registered user. Roham must verify
ownership and backfill product and import owner IDs referencing real users in one
reviewed transaction. For historical Telegram data, reconcile mapping owners,
product owners and the corresponding message batch owners together, preserving
run/message/receipt IDs. Ingestion of a mapped product with unverified ownership
fails closed until this is done. Existing external AuthService IDs must correspond
to the users table; do not invent accounts to satisfy FKs.

SQLite migrations temporarily disable FK enforcement during Alembic table rebuilds
and check all FKs afterwards; tests use enforcement for normal API operations.
Downgrade refuses if owner-scoped imports would violate old global deduplication.
Downgrading ownership removes session/owner data and should require a backup;
downgrading Telegram removes its tables. SQLite migration round trips and metadata
parity are tested. PostgreSQL staging migration rehearsal remains a release gate.

## Frontend and validation

Login/create-account leads to `/products`: paginated own profiles, create/edit
form, profile details, current selection, validation, loading/error/retry states
and sign-out. Optional product metadata is retained under product details.
Account changes/sign-out clear locally selected product and run IDs; IDs are
convenience state, never authorization. The import selector only lists owned
profiles. Existing styles and routes are retained.

Offline coverage includes authenticated CRUD, required fields, foreign/unassigned
profiles, import/run/lead isolation, sessions, expiration, logout, secure cookies,
Origin checks, snapshot stability, migrations and the real Agent path with fake
HTTP for sensor calibration, a veterinary clinic and accounting SaaS. Production
provider calls are never made by tests. OpenAPI is regenerated by
`scripts/export_openapi.py`; frontend declarations use `npm run generate:api`.

Roham must review the new user/session storage and migration numbers against his
branches, session cookie deployment settings, ownership backfill and removal of
previous unauthenticated API access. Fatima should review the login and setup UI
changes against her frontend branch. No teammate files were overwritten in the
initially clean working tree; merge conflicts still need normal team review.

## Changed files

This branch changes the following files; no Agent source, worker or analysis service was modified.

- `.env.example`
- `README.md`
- `backend/app/api/routes/auth.py`
- `backend/app/api/routes/main.py`
- `backend/app/auth/README.md`
- `backend/app/auth/contracts.py`
- `backend/app/auth/dependencies.py`
- `backend/app/auth/service.py`
- `backend/app/core/config.py`
- `backend/app/integrations/telegram/actions.py`
- `backend/app/integrations/telegram/dependencies.py`
- `backend/app/integrations/telegram/ingestion.py`
- `backend/app/integrations/telegram/models.py`
- `backend/app/integrations/telegram/routes.py`
- `backend/app/integrations/telegram/schema.sql`
- `backend/app/main.py`
- `backend/app/models/__init__.py`
- `backend/app/schemas/api.py`
- `backend/app/services/import_service.py`
- `backend/app/services/ownership_service.py`
- `backend/migrations/env.py`
- `backend/migrations/versions/0002_telegram.py`
- `backend/migrations/versions/0003_product_ownership.py`
- `backend/tests/conftest.py`
- `backend/tests/test_authenticated_smoke_helper.py`
- `backend/tests/test_business_migrations.py`
- `backend/tests/test_business_setup.py`
- `backend/tests/test_flow.py`
- `backend/tests/test_telegram_flow.py`
- `compose.yaml`
- `contracts/examples/current_user.json`
- `contracts/openapi.json`
- `docs/api-contract.md`
- `docs/business-setup.md`
- `docs/demo-script.md`
- `docs/telegram-integration.md`
- `frontend/app/imports/page.tsx`
- `frontend/app/layout.tsx`
- `frontend/app/products/page.tsx`
- `frontend/components/AuthFormShell.tsx`
- `frontend/components/SessionBoundary.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/generated/api.d.ts`
- `scripts/smoke.py`

## Validation completed

- Complete offline backend suite: **1,132 passed** (53 additional tests).
- Existing CSV/Telegram workflows and Agent tests passed, with fake provider HTTP only.
- Frontend API generation, typecheck and production build passed.
- OpenAPI equals the application's exported schema; all six API JSON fixtures validate.
- SQLite migration upgrades/downgrades, legacy data retention and ORM parity passed.
- `pip check`, `git diff --check` and changed-file secret/whitespace audits passed.
- Agent source/contracts/providers/prompts/scoring and worker/analysis-service source are unchanged.
- No live provider requests, production migrations, commit or push were performed.
- PostgreSQL staging migration rehearsal and browser end-to-end testing were not run.
