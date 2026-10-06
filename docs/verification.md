# Bootstrap verification — 4 October 2026

Actual checks on this Windows workstation (Python 3.14.7, Node 24.21.0):

| Check | Result |
| --- | --- |
| Backend pytest | 16 passed: score boundaries/guards, context isolation/bounds, grounded evidence, prompt injection as data, atomic import, BOM/timezones, duplicate rows/import/run, snapshot immutability, per-message failure + usage, expired heartbeat recovery |
| Alembic upgrade head on SQLite | Passed |
| Alembic check | No schema drift detected |
| pip check | No broken requirements |
| Real HTTP smoke with independent API and worker processes | Passed: 20/20 messages processed, completed, 4 respond results; example score 84; repeated Idempotency-Key reused run |
| OpenAPI export + TypeScript generation | Passed |
| Frontend TypeScript typecheck | Passed |
| Next.js production build | Passed; all six application routes built |
| Production frontend HTTP route checks | All six routes returned HTTP 200; this checks server delivery, not browser interaction |
| docker compose config --quiet | Passed |
| npm install dependency audit | 0 vulnerabilities reported at install time |

Initial sandbox restrictions prevented Python temporary-directory access and
Next.js subprocess spawning. Those checks were rerun with approved access and
the results above are from the successful runs. Starlette currently emits one
test-client deprecation warning about httpx; tests pass.

Docker Desktop's Linux daemon was not running (named pipe not found). The full
Compose images, PostgreSQL migration/locking behavior and container restart
cycle were not executed here. SQLite integration tests do not prove PostgreSQL
behavior. Browser interaction/visual checks and real LLM evaluation were not
performed. No empirical AI accuracy or cost-savings claim is made.

Lockfiles were generated and dependencies installed. Production backend Docker
uses Python 3.12; that Linux image remains unverified until Compose runs.
The local demo database is ignored by Git. Contracts examples contain real IDs
from the local synthetic smoke run, not portable seeded IDs for every database.

## Revised five-day skeleton review — 4 October 2026

Read the supplied five-day PDF, preserved it in docs/sources, and documented the
comparison/selected architecture and Setayesh/Roham/Fatima ownership. Auth and
online delivery are now explicitly P0 requirements, not implemented claims.

Actual checks after Agent changes: **27 backend tests passed**. New tests cover
product-specific whole-word screening, cross-conversation defense, non-course
Mock output, mutated invalid signals with usage preservation, Decimal accounting,
unknown/zero/mixed costs, evaluation completeness, failed messages, null metrics
and development/test conversation leakage. Existing 20-message flow tests still
pass. Public OpenAPI was compared with the live schema and is unchanged; the
evaluation CLI help command executes successfully. UI/schema/migrations were not
changed, so the prior frontend build and migration results were not rerun.

Pure cost/evaluation utilities are implemented, but provider/model selection,
SDK/credentials, real rates, budget enforcement, real datasets/evaluation and
grounded reply remain next-stage tasks. PDF extraction used a local pypdf tool;
it is not a new runtime dependency or a change to the project's lockfiles.

## File skeleton completion — 4 October 2026

Added draft auth/security/service contracts, response/feedback/analytics schemas,
reply contracts, qualification/reply prompt builders, fail-closed real-provider
slot, evaluation-data/deployment handoffs and login/register/dashboard UI shells.
No auth or real-provider implementation was mounted; no DB schema changed.
Auth fields/forms are disabled and do not simulate user authentication.

Backend verification: **30 tests passed**, including prompt/data separation,
foreign-context rejection, reply eligibility and session-token serialization.
These tests validate boundary behavior, not real-model injection resistance or
implemented session security. See docs/file-skeleton.md for file readiness.
Frontend typecheck and production build passed with the three new shell routes.
Public OpenAPI is unchanged. A GitHub CI workflow was added, but has not run on
GitHub; local checks are not a claim that the Linux workflow or hosting passed.

## Backend Day 1 — 6 October 2026

Implemented account registration/login/logout/current-user routes, revocable
server-side sessions, salted scrypt password hashes, HttpOnly session cookies,
per-user Product/ImportBatch/AnalysisRun ownership, and user-scoped API reads.
Import checksum and run idempotency uniqueness are now per user. Migration 0002
preserves pre-authentication rows with null ownership; authenticated routes do
not expose them. AgentInput/AgentOutput schemas were not changed; shared contract
fixtures were added.

Checks run on the local Windows environment:

- Backend suite: **207 passed**.
- Alembic upgrade to 0002 on SQLite: passed; `alembic check`: no schema drift.
- A populated 0001→0002 SQLite migration preserved legacy product, batch, and run
  rows and left their owner IDs null.
- OpenAPI export, including the session-cookie security scheme on protected
  routes, and TypeScript generation: passed.
- Frontend typecheck and production build: passed.

The PostgreSQL/Compose migration and live browser login flow have not yet been
verified. Fatima still owns frontend auth UI and credentialed API client wiring.
