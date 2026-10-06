Step 5 adds one OpenAI Responses adapter alongside the deterministic Mock.
It requests strict JSON-schema output and then locally validates the frozen
QualificationResult, all six signals, exact evidence quotes and source IDs.
The provider never computes a final lead score or decision.

Set these **process environment variables** before constructing the provider:

- `OPENAI_API_KEY`: private API key; never commit it.
- `OPENAI_MODEL`: explicit model supporting Responses strict structured outputs.
- `OPENAI_TIMEOUT_SECONDS`: optional, default 30, at most 120.
- `OPENAI_MAX_OUTPUT_TOKENS`: optional, default 2000, range 100..10000.

Configuration reads process environment only; it does not load `.env` itself.
Credentials are read only from `OPENAI_API_KEY`, including when non-secret
settings or an HTTP client are injected. The settings model accepts no API key.
Call `get_provider("real")` from `app.agents.providers.factory`. Calling
`get_provider("mock")` still selects Mock explicitly. Unsupported modes or
missing/invalid real configuration fail; there is no fallback.
An embedding application may select the factory argument from `PROVIDER_MODE`.
Existing HTTP routes and worker integration have not been changed to enable real
mode. Auth/user isolation and deployment remain pending outside this Agent task.

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

Only dependency change: promote existing httpx (locked at 0.28.1) from dev to
runtime. Its existing dev-lock pins were copied into the runtime lock; full
offline pip-compile regeneration could not resolve existing packages from cache.
No OpenAI SDK or extra real providers were added. Unit tests use httpx.MockTransport;
no live provider validation has been performed.

Request format reference:
https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses
