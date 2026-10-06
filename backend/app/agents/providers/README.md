The RealProvider is an OpenAI-compatible Responses adapter alongside the deterministic Mock.
It requests strict JSON-schema output and then locally validates the frozen
QualificationResult, all six signals, exact evidence quotes and source IDs.
The provider never computes a final lead score or decision.

Set these **process environment variables** before constructing the provider:

- `OPENAI_API_KEY`: private API key; never commit it.
- `OPENAI_MODEL`: explicit model supporting Responses strict structured outputs.
- `OPENAI_BASE_URL`: optional; defaults to `https://api.openai.com/v1` when unset.
  The only other trusted endpoint is `https://api.avalai.ir/v1`. One trailing
  slash and surrounding whitespace are normalized. Blank or untrusted values
  fail closed before sending a request; there is no endpoint fallback.
- `OPENAI_TIMEOUT_SECONDS`: optional, default 30, at most 120.
- `OPENAI_MAX_OUTPUT_TOKENS`: optional, default 2000, range 100..10000.

Configuration reads process environment only; it does not load `.env` itself.
Credentials are read only from `OPENAI_API_KEY`, including when non-secret
settings or an HTTP client are injected. The settings model accepts no API key.
Qualification, its repair attempt, and explicitly requested reply generation
all send to `{OPENAI_BASE_URL}/responses` with `Authorization: Bearer <key>`.
The trusted URL is checked again for every request and redirects stay disabled.
No arbitrary hosts, HTTP endpoints, credentials in URLs, query strings, fragments,
ports or extra paths are accepted. No contract fields or extra SDK were added.
Call `get_provider("real")` from `app.agents.providers.factory`. Calling
`get_provider("mock")` still selects Mock explicitly. Unsupported modes or
missing/invalid real configuration fail; there is no fallback.
An embedding application may select the factory argument from `PROVIDER_MODE`.
Existing HTTP routes and worker integration have not been changed to enable real
mode. Auth/user isolation and deployment remain pending outside this Agent task.

AvalAI configuration (set privately in the process environment):

```dotenv
OPENAI_API_KEY=<your private AvalAI key>
OPENAI_MODEL=gpt-5.6-luna
OPENAI_BASE_URL=https://api.avalai.ir/v1
```

The exact outgoing endpoint is `https://api.avalai.ir/v1/responses`. Set
`AgentInput.metadata.provider_mode="real"` when invoking the public orchestrator
or reply entry point. `PROVIDER_MODE=real` only applies to embedding code that
reads that variable; the Agent uses the supplied typed metadata. No separate
`AVALAI_API_KEY` variable is read by SignalX.

[AvalAI documents Responses compatibility and its base URL](https://docs.avalai.ir/en/libraries).
The user reports successful English, Persian, context and suggested-reply smoke
tests with `gpt-5.6-luna`. Other model/account configurations still require their
own authorized live verification. No paid request was made automatically while
implementing or auditing endpoint selection.

Standalone qualification:

```python
from app.agents.providers.factory import get_provider

provider = get_provider("real")
qualification, usage = provider.qualify_structured(product, target, selected_context)
```

Inputs above are ProductSnapshot, TargetMessage and a list of TargetMessage.
Selected context must belong to the target conversation, exclude the target
and have unique IDs. The provider checks these constraints before a call.
`analyze(AgentInput)` also accepts the frozen public boundary; it screens then
qualifies, leaving `scoring` and `suggested_reply` unset. ContextMessage has no
conversation ID, so that public boundary relies on the caller supplying scoped
context. The legacy `qualify(...)` adapter returns Qualification and UsageEvent;
the existing Agent pipeline validates evidence and calls `score_v1` separately.
The pipeline rejects real mode with a Mock provider and rejects a Real provider
under mock mode before screening or any provider call.

One invalid schema/JSON/evidence response permits one regeneration with the same
sources and a trusted repair instruction. Raw output and validation error text
are never inserted into trusted instructions. A second invalid response raises
ProviderError with both usage records. HTTP/network errors, timeouts, refusals
and explicitly incomplete responses fail immediately; they are not retried.
Production HTTP transport has no automatic retries; requests use `store=False`.
Injected test clients remain caller-owned.

Every attempted call records stage (`qualification` or `qualification_repair`),
attempt number, real mode, reported model (or requested model when unavailable),
reported token counts, measured latency and outcome. ProviderError preserves
those records even if no valid qualification is returned. Missing/invalid token
measurements remain null. No calls means an empty usage list.

Cost is unknown/null by default. To estimate USD cost, provide all three optional
environment variables together: `OPENAI_PRICE_VERSION`,
`OPENAI_INPUT_USD_PER_MILLION`, `OPENAI_OUTPUT_USD_PER_MILLION`.
Rates must be finite and non-negative. They apply only to the exact configured
and explicitly reported model, known input/output counts, and a reported
non-negative integer cache count of zero. Missing/invalid cache details or a
missing billed model leave cost unknown. Cached input cannot be priced by this
two-rate calculator and leaves cost unknown. No prices are fetched or
invented. Each attempt has its own Decimal estimate; failed/repair attempts are
not discarded. Legacy UsageEvent uses `cost_usd=null` and `price_version="unknown"`
where its schema cannot represent a null price version. Public UsageInfo retains
null. Mock cost stays explicitly zero with `cost_status="mock"`.
Rates must match the selected endpoint's actual USD billing, not just the model
name. Verified Luna acceptance configuration and per-attempt reporting are in
[the manual acceptance guide](../ACCEPTANCE.md). Other models require their own
verified rates or all three pricing variables left unset.
Switching endpoints requires clearing or replacing any existing rate variables;
SignalX cannot infer whether manually configured rates belong to OpenAI or AvalAI.
The provider does not perform billing lookups, currency conversion or published
price fetching. The manual acceptance runner reports estimated toman only.
Missing token/cache metadata or model aliases that differ from the
configured model continue to leave estimated cost null/unknown.

Only dependency change: promote existing httpx (locked at 0.28.1) from dev to
runtime. Its existing dev-lock pins were copied into the runtime lock; full
offline pip-compile regeneration could not resolve existing packages from cache.
No OpenAI SDK or extra real providers were added. Unit tests use httpx.MockTransport;
the user's English/Persian/context qualification and reply acceptance calls have
succeeded. These smoke checks establish functionality, not population model accuracy.

Request format reference:
https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses

## First manual AvalAI smoke test

Run this yourself in the same PowerShell session where OPENAI_API_KEY is already
set. Configuration reads process environment, not a PowerShell variable without
the `$env:` prefix, and does not load `.env` automatically:

```powershell
Set-Location 'C:\git\shared\SignalX\backend'
$env:OPENAI_BASE_URL = 'https://api.avalai.ir/v1'
$env:OPENAI_MODEL = 'gpt-5.6-luna'
.\.venv\Scripts\python.exe -m app.agents.smoke_test
```

By default the module calls `app.agents.orchestrator.analyze_agent` exactly once with real
mode, no context and one English message: "I'm looking for a Python course for
beginners. How much does it cost?" Product name is "Python Starter Course",
description "Beginner-friendly Python programming course.", audience "Beginners".
It runs production screening, qualification, evidence checks and deterministic
scoring. There is no Mock, batch, reply generation, persistence or sending.
Importing the module or using `--help` does not perform a provider request.

One analysis can make **up to two paid HTTP requests** because the production
provider permits one qualification repair. All attempts are printed separately.
The script does not retry the analysis or switch models/endpoints after failure.
Exit codes: 0 success, 1 provider/incomplete-analysis failure, 2 configuration or
validation failure, 3 unexpected local failure, 130 interruption.

JSON output includes intent, all six signals, score, decision, exact evidence and
every usage record (model, tokens, cost_status, estimate, latency and outcome).
Unknown measurements stay null/unknown. Leave pricing variables unset unless
verified for AvalAI and this model. Provider failures include sanitized HTTP
status/fixed diagnostics; raw API error messages and the API key are never printed.
The script also redacts the environment key if echoed in a result. No live call
was performed during preparation; automated tests use fake HTTP only.

Explicit `--scenario persian`, `context`, `reply`, or `acceptance` selects the
next acceptance checks. [Exact commands, verified pricing, request budgets and
rate-limit safety](../ACCEPTANCE.md) are documented separately. All dispatches,
including repairs, are spaced at least 65 seconds apart, with an initial delay.
The optional paired snapshot lets reply-only execution reuse a completed real
analysis without another qualification call. Factory `real_provider_client`
scopes a caller-owned real HTTP client to this manual run and resets on exit;
default production client construction and provider selection stay unchanged.
