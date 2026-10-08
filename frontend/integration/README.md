# Connected backend acceptance tests

Build the current frontend, then run `npm.cmd run test:integration` from
`frontend` (or `npx.cmd playwright test --config playwright.integration.config.ts`).
Use the existing backend `.venv` and frontend dependencies. On non-Windows systems
the profile uses `.venv/bin/python`; Windows uses `.venv/Scripts/python.exe`.
Ports 3100 and 8000 must be free. Playwright refuses to reuse an existing server.
The production build must use the default localhost:8000 API URL for this profile.

This profile starts the actual final backend application and production frontend.
Browser API requests are not intercepted. It uses the same temporary SQLite,
SQLAlchemy metadata and session dependency pattern as the existing backend tests.
Provider Responses and Telegram transports are intercepted inside the test runtime
with `httpx.MockTransport`. Credentials and tokens are synthetic fixtures; there
are no paid requests, external message sends, production data or migrations.
Telegram's nominal real-provider mode is exercised with the real adapter and an
injected offline HTTP client; it is never silently switched to Mock.

`runtime.py` adds loopback-only `/__test/` fixture/control endpoints to this test
process. Never import or deploy this runtime as application code. Test controls
explicitly advance a queued job or expire a persisted test cooldown. Cooldown
expiry does not invoke sending, and no background retry loop is installed.

The tests cover browser cookie login, failed CSV category/retry, server attempts,
unchanged successful analyses and original product snapshot after product editing,
exact approved Telegram text, successful acknowledgement, a 429 followed by a
200/failed key replay, explicit new-key retry, and uncertain timeout after mobile
refresh. Screenshots and traces are ignored local artifacts in
`playwright-report/connected/`; the normal UI tests use `test-results/`.

This verifies local UI/API integration. PostgreSQL, deployed cookies/CORS/Origin,
independent worker operation, live-provider configuration and operator delivery
reconciliation are separate release checks.
