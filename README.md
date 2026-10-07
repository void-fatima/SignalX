# singnalX

The backend includes account/session endpoints, user-scoped data access, Agent
provider adapters (AvalAI and Gemini), response/feedback persistence and run
analytics. The login/register pages remain UI shells until Fatima connects them
to the API. Gemini hosting configuration and deployed live verification remain
pending. See [file readiness](docs/file-skeleton.md).

Runnable Mock foundation aligned with the revised SignalX five-day architecture, created directly in
the cloned SignalX repository. English UI supports Persian/English messages.
Next.js + TypeScript + Tailwind; FastAPI + Pydantic; SQLAlchemy + Alembic;
PostgreSQL in Compose; separate Python worker using a database-backed run queue.

## Docker Compose (recommended)

Start Docker Desktop with Linux containers, then from the repository root:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open http://localhost:3000. API documentation: http://localhost:8000/docs.
Migration runs automatically before API/worker start. PostgreSQL data survives
`docker compose down`; use `docker compose stop` to pause services. Exactly one
worker is supported. Compose binds ports to localhost for this local MVP.
No API key is needed for the local Compose default; PROVIDER_MODE is explicitly
mock. Real mode requires provider configuration and fails clearly when it is absent.

## Local Windows / PowerShell

Prerequisites: Python 3.12+ and Node 24. This alternative uses SQLite for local
development; PostgreSQL remains the Compose database. Use three terminals.

Terminal 1, from the repository root:

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
$env:DATABASE_URL = 'sqlite:///./singnalx.db'
$env:PROVIDER_MODE = 'mock'
Set-Location backend
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2, from the repository root (same DATABASE_URL as API):

```powershell
$env:DATABASE_URL = 'sqlite:///./singnalx.db'
$env:PROVIDER_MODE = 'mock'
Set-Location backend
.\.venv\Scripts\python.exe -m app.worker
```

Terminal 3:

```powershell
Set-Location frontend
npm ci
$env:NEXT_PUBLIC_API_URL = 'http://localhost:8000/api/v1'
npm run dev
```

For local PostgreSQL instead, set DATABASE_URL to the example PostgreSQL URL
in both Python terminals and start a database first. Python settings read .env
from the process working directory; Compose reads the root .env automatically.
Never place provider secrets in NEXT_PUBLIC variables.

## Demo

Save the prefilled product → import data/demo_messages.csv → Start Mock analysis
→ watch worker progress → open Results and a result detail. The Persian explicit
course request scores 84. Price objections retain conversation context. See
[the demo walkthrough](docs/demo-script.md).

CSV is UTF-8/BOM, maximum 5 MB / 500 rows; content limit is 4000 characters.
All rows validate before any insert. Timestamps require a timezone. Same file
bytes/community/user reuse the batch. Idempotency-Key reuses a run within the
current user; changed payload with the same key is a conflict. Product/config
snapshots are immutable per run.
Failures are isolated per message; stale running jobs become interrupted on
worker restart and are not retried automatically. Offline context includes up to
three earlier and two later messages from the same batch/conversation.

## Checks and contracts

From the root:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.lock
Set-Location backend
.\.venv\Scripts\python.exe -m pytest
Set-Location ..
.\backend\.venv\Scripts\python.exe scripts/export_openapi.py
Set-Location frontend
npm run generate:api
npm run typecheck
npm run build
```

With the API and worker running, verify the actual HTTP flow from the root:

```powershell
.\backend\.venv\Scripts\python.exe scripts/smoke.py
```

This smoke script creates a synthetic product/import/run and reports the result;
it does not modify contract fixtures or other repository files.

Backend lockfiles pin all transitive dependencies. Regenerate after intentional
dependency changes (from backend):

```powershell
.\.venv\Scripts\pip-compile.exe --output-file=requirements.lock pyproject.toml
.\.venv\Scripts\pip-compile.exe --extra=dev --output-file=requirements-dev.lock pyproject.toml
```

`npm ci` uses frontend/package-lock.json. The API contract and generated frontend
types must change together; [ownership](docs/team-plan.md),
[API conventions](docs/api-contract.md), [architecture](docs/architecture.md).

## Current scope

Mock output is synthetic demonstration data, not real LLM analysis or measured
accuracy. Recorded Mock usage has no real tokens, cost zero and cost_status=mock.
Screened-out messages have null scores; failed messages have null decisions.
No automatic message sending. Real provider adapters, response drafts, feedback
and run analytics are implemented locally; live Gemini Worker persistence on the
selected host is still pending. Paid usage/budget control, evaluation datasets,
deployment and presentation media remain outstanding. Backend authentication and
user isolation are implemented locally. The auth UI and browser credential
handling remain with Fatima.
Pre-authentication records are unowned and inaccessible through authenticated APIs.

Pure cost utilities and an offline evaluation CLI are now implemented; real
provider accounting, budget enforcement and measured evaluation remain pending.
[Architecture comparison](docs/architecture-comparison.md) explains what was
kept and improved. [Setayesh's five-day tasks](docs/setayesh-plan.md) track the
current AI work; Roham owns backend/auth/deploy and Fatima owns all UI.

See docs/verification.md for checks actually run in the bootstrap environment and
remaining limits. No cloud deployment has been performed.
