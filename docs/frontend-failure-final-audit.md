# Final Failure Handling frontend integration audit

Audit date: 2026-10-08. UI base: merged PR #6,
`main@258d841e2fddd918e28a34f046d7a9cb5b774286`.
The existing Lead/Telegram screens, shell, logo, theme and layouts are preserved.

## Verified unified backend

The initial fetch contained only the divergent main and old Failure Handling
handoff. A later fetch during this audit discovered PR #7:
`feature/backend-failure-recovery@072a4dc72cb634b8c1e86d0ba73a50be501c8f09`, merged
into `origin/main@7629e1b59337c87e3b98875ad2a87ac45c4fe1ee`.
This is the final unified implementation tested here. It was merged into a third
stacked integration branch; local `main` was not moved or edited. Backend business
logic and migrations have no diff against that verified upstream backend tree.

| Capability | Unified runtime evidence | Frontend action |
|---|---|---|
| Retry endpoint | POST `/api/v1/analysis/runs/{id}/retry`, 202, required Idempotency-Key, no body | Existing client preserved |
| Retry semantics | Replayed key does not enqueue; new accepted intent increments attempt; ownership and state guards | Persistent scoped key, explicit check/retry, loading lock |
| Analysis failure_category | Nullable five-category allowlist; safe server reasons | Explicit readable label plus known diagnostic code |
| Run attempt_no | Nullable in schema; server returns actual generation | Display value or unavailable, never fabricate |
| Telegram success | `delivery.status`, values not_sent/sending/sent/failed | Only validated sent displays Sent; no invented delivery_status |
| Approved text | `delivery.approved_text` persisted before send | Retain exact bytes and request key across refresh |
| Failure metadata | failure_category, delivery_uncertain, failure_http_status, retry_after_at | Validate recovery metadata before enabling recovery |
| Failed replay | Same key/text may return HTTP 200 with failed | Failed remains Failed, never Sent |
| Rate limit/uncertainty | Persisted 429 cooldown; uncertain blocks new attempts | Cooldown enables explicit action only; operator reconciliation |
| Response/feedback/analytics | All existing endpoints retained | Active clients now use one generated unified source |

The actual application schema equals root OpenAPI after the existing exporter's
422-description normalization; generated types reproduce without content diff.
The old handoff snapshot remains archived, not imported by active clients.
Generic LeadDetail still has no declared source discriminator; its optional legacy
source adapter is preserved. Telegram's dedicated endpoint declares its source.
No response/feedback/analytics endpoint was removed.

## Updated checklist

| Requirement | Current evidence | Remaining gap | Action |
|---|---|---|---|
| Safe Analysis failed and explicit category | AnalysisFailure.tsx; known readable labels and exact safe code; absent/unknown tests | Future unknown categories intentionally not echoed | Safe fallback, no raw exceptions |
| Safe failed explanations throughout UI | LeadConversation.tsx, LeadQueue.tsx, app/leads/[id]/page.tsx | None found in tested failed CSV views | Suppress failed reason/decision/limitations; preserve source/context/snapshot |
| Server attempts and discoverable retry | Existing FailedReview link, RunRecovery.tsx; attempt 1 -> 2 HTTP acceptance | None in tested local path | Existing navigation retained, no duplicate link |
| Reload differs from retry | RunRecovery test records POST count, key replay, busy lock | None in tested local path | Reload performs GET; deliberate retry only |
| Unknown acknowledgement preserves key | Server/unreadable/invalid response tests | None identified | Same key across refresh/ambiguity; fresh key for acknowledged new attempt |
| Preserve successes/snapshot/usage | Final test_failure_recovery.py and connected browser acceptance | PostgreSQL check skipped without test DB | Run release DB check before publishing |
| HTTP 200 delivery interpretation | Telegram test matrix and actual failed replay/sent acceptance | No real Telegram destination used | Sending/Sent/Uncertain/new-send guards retained |
| Exact approved text after refresh | Hook uses pending intent; whitespace/newline tests and actual persisted approved text | sessionStorage is scoped to browser tab/session | Block new sends while intent unresolved |
| Definite failure recovery | Typed metadata, matching approved text acknowledgement, cooldown and new-key tests | Operator process is manual | No automatic reconciliation/resend |
| Editing/saving/generating never send | Existing reply tests and exact send-request counters | No paid provider/outreach check requested | Explicit approval boundary preserved |
| Desktop/mobile accessibility | Screenshot inspection, keyboard focus, reduced-motion/overflow tests | Deployed host presentation not checked | Existing layout/components retained |
| Unified runtime integration | Actual FastAPI HTTP handlers plus connected browser profile | Production infrastructure remains unverified | Local acceptance evidence does not imply release readiness |

## Changes and branch order

Apply analysis recovery, then Telegram delivery, then unified-contract integration.
The last branch includes both UI branches and the incoming backend merge. No push,
merge into local main, deploy, force push, squash or amend was performed. Remote main
advanced because PR #7 was merged upstream during this task. User `.vscode/` remains
untouched.

| Branch | Base | Focused commits |
|---|---|---|
| fix/ui-final-analysis-recovery | local main@258d841 | fecf750 category labels; 5dd5187 invalid retry acknowledgement; d24125c suppress raw failure fields and retain existing navigation; 6c02508 recovery behavior coverage |
| fix/ui-final-telegram-delivery | analysis branch@6c02508 | fe04a54 durable approval; 7b9946f validated failure metadata and matching text; 2508d51 HTTP state/replay tests |
| fix/ui-final-unified-contract | Telegram branch@2508d51, then merge origin/main@7629e1b | 00ef015 incoming backend merge; 09ff007 single-source active API types; 44ab050 connected browser HTTP acceptance; final audit documentation commit |

## Actual verification

Commands below use existing local dependencies. Frontend commands run from
`frontend`; backend commands from `backend`.

- `npm.cmd run typecheck`: passed on unified types.
- `npm.cmd run build`: passed on unified backend/clients.
- `npm.cmd run generate:api`: passed; generated declarations match unified export.
- `backend/.venv/Scripts/python.exe -X utf8 scripts/export_openapi.py`, from root:
  passed; unified root contract unchanged.
- `npm.cmd run generate:handoff`: reproduced the archived types; no content diff.
- `npm.cmd test -- failure-recovery.spec.ts`: 8 passed after fixes.
- `npm.cmd test -- telegram-recovery.spec.ts telegram-delivery.spec.ts telegram-reply.spec.ts telegram-leads.spec.ts failure-recovery.spec.ts`:
  51 passed before switching active type imports to the equal unified structures.
- `npm.cmd test -- inbox.spec.ts reply-review.spec.ts analysis-modal.spec.ts evidence.spec.ts telegram-proxy.spec.ts analysis.spec.ts`:
  36 passed before the unified-source switch, confirming successful UI preservation.
- Final backend `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_failure_recovery.py tests/test_telegram_flow.py tests/test_auth.py tests/test_flow.py tests/test_responses.py tests/test_analytics.py tests/test_migrations.py tests/test_postgres_failure_recovery.py -q`:
  **76 passed, 1 skipped**, one existing Starlette/httpx deprecation warning.
  The skip is exactly `TEST_POSTGRES_URL is not configured`.
- Those backend tests use actual FastAPI HTTP routes via TestClient/ASGI, isolated
  SQLite users and controlled provider/Telegram adapters. They cover authentication,
  failed results, retry keys/generations, stable results/usage, delivery failure,
  definitive 429 retry, response/feedback/analytics and SQLite migration 0007.
- `npx.cmd playwright test --config playwright.integration.config.ts`: connected
  browser acceptance against final actual FastAPI on localhost:8000 and Next.js on
  localhost:3100. Isolated temporary SQLite and offline HTTP transports; no browser
  route interception, real provider request, real Telegram send or production DB.
  The test driver explicitly advances worker processing; it does not deploy a worker.
  **4 passed**, including product editing before retry and preserved original snapshot.
  `npm.cmd run test:integration` also passed all four on the final profile, with
  screenshots/traces retained separately under `frontend/playwright-report/connected/`.
- `npm.cmd test` on the final unified clients: **131 passed** (complete existing
  frontend suite plus new behavioral cases).
- `git diff --check` and backend-tree equality against `origin/main@7629e1b`: passed.
- Screenshots under ignored `frontend/test-results/` were visually inspected for
  failed categories and existing Telegram desktop/mobile review/recovery. Keyboard
  focus, reduced-motion behavior and page overflow checks passed in focused suites.
  The actual connected run desktop screenshot and uncertain Telegram mobile
  screenshot in `frontend/playwright-report/connected/` were also inspected.
- No frontend lint script/configuration exists; lint was not claimed as passed.

Earlier evidence: old main backend 258d841 had 52 relevant tests pass; historical
handoff 96b7fa0 had 75 pass in detached sibling worktree
`C:/Users/FATIMA/GitHub/SignalX-failure-audit-96b7fa0`. These are supplementary history,
not the final integration evidence. The final backend above supersedes the earlier
404 retry probe and unavailable unified-contract dependency.

## Release gate

**Local unified UI/API integration: Verified with controlled adapters.**
**Deployment readiness: Blocked pending release verification.** This does not
verify live provider operation or real Telegram delivery.
PostgreSQL migration/concurrency was not checked because TEST_POSTGRES_URL was
absent; deployed HTTPS/cookie/CORS/Origin, actual worker operation and operator
reconciliation remain release-owned checks. No deployed runtime URL was supplied.
No backend business logic/migration was changed to conceal a mismatch, and no
paid requests, real outreach or deployment occurred.
