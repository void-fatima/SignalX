# Gemini and AvalAI provider selection

Backend continues to call `analyze_agent(AgentInput) -> AgentOutput` and, only
after an explicit user request, `generate_suggested_reply(input, analysis)`.
Selection stays in the Agent factory; Backend does not branch on vendors.
`AgentInput.metadata.provider_mode` must be `real`. Explicit `mock` mode remains
available for development. No frozen contracts, scoring rules, routes or worker
behavior were changed by adding Gemini.

Set `LLM_PROVIDER=gemini` to select the separate `GeminiProvider`. Set
`LLM_PROVIDER=avalai` for the existing `RealProvider`, which still accepts
OpenAI/AvalAI Responses URLs. When the selector is **absent**, existing Responses
behavior is preserved. A blank, misspelled or unsupported selector fails closed.
The Agent reads process environment and does not load `.env` files itself.
New `.env.example` entries are empty variable names: set the selected variables
explicitly, and omit unused optional entries rather than loading them as blanks.

## Production selection

Backend/hosting must explicitly set these process environment variables:

```dotenv
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
GEMINI_API_KEY=<secret>
```

`<secret>` is a placeholder; supply the private key through the hosting secret
store. Backend continues to pass `metadata.provider_mode="real"` to the existing
Agent entry points. Leaving `LLM_PROVIDER` unset preserves legacy Responses
selection; Gemini is never enabled implicitly. AvalAI remains an explicit
alternative through `LLM_PROVIDER=avalai` and its existing `OPENAI_*` variables.
Neither provider automatically falls back to the other or to Mock.

## Configuration and transport

| Variable | Gemini behavior |
| --- | --- |
| `GEMINI_API_KEY` | Required private Google API key; never read from `OPENAI_API_KEY`. |
| `GEMINI_MODEL` | Required explicit model; initial manual scenario uses `gemini-3.5-flash-lite`. |
| `GEMINI_BASE_URL` | Official URL below; defaults to it in production when absent. Manual live runner requires it explicitly. |
| `GEMINI_TIMEOUT_SECONDS` | Optional; default 30, greater than zero and at most 120. |
| `GEMINI_MAX_OUTPUT_TOKENS` | Optional; default 2000, range 100..10000. |

Exact base URL: `https://generativelanguage.googleapis.com/v1beta/openai/`.
Exact request URL: `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`.
Authentication is `Authorization: Bearer <GEMINI_API_KEY>`. Requests use
`messages`, `max_tokens` and `response_format.type=json_schema`; Gemini is never
sent to `/responses`. Only the official HTTPS base URL is trusted, with one
optional trailing slash normalized. Redirects, custom hosts, explicit ports,
queries, credentials in URLs and extra paths are rejected before dispatch.
The URL is checked again on each attempt. Credentials stay in a redacted secret
container, are never included in request JSON, and are not printed by the Agent.

Existing httpx implements the documented compatible HTTP protocol. The OpenAI
SDK is not installed here, and no Google/OpenAI SDK or dependency was added.
Official references: [Google OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai),
[structured output](https://ai.google.dev/gemini-api/docs/structured-output),
[model catalog](https://ai.google.dev/gemini-api/docs/models).

## Structured output, evidence and provenance

Gemini receives the existing qualification instructions and untrusted source
envelope. Its provider-facing schema inlines `$defs`/`$ref`, removes descriptive
titles/defaults and unsupported string-length keywords, and preserves properties,
required fields, additional-property rejection, numeric bounds and array bounds.
Nullable reply fields retain `anyOf`. This adaptation does not mutate the source
schema or public models. Unsupported schema errors are not retried with weaker
JSON mode. No final score or decision is requested or accepted from the model.

Every payload undergoes the unchanged strict Pydantic validation, required-field
checks, signal bounds and exact message-ID/quote grounding. Replies also reuse
the existing `ReplyDraft` and `render_draft`: only whole supplied Product fields
and one cautious question are allowed, in the target language. Grounding guards
reject invented prices, product claims and unsafe questions. These checks cannot
prove semantic correctness or perfect injection resistance; returned replies
remain drafts for human review, with no sending or approval.

One invalid output permits one repair using original sources and a trusted
instruction, without injecting raw failed output or validation errors. Both
attempts retain usage. A second invalid output raises `ProviderError`.
HTTP 400, 401/403, 404, 429, 5xx, network errors, timeout, refusal or truncation
stop immediately. Errors contain fixed sanitized explanations, never provider
body text or credentials. There is no fallback to AvalAI or Mock.

Successful Gemini qualification records `prompt_version=qualify_gemini_v1`.
AvalAI retains `qualify_real_v1`. Rejected screening records no executed prompt.
Scoring remains `score_v1` and runs in the existing generic orchestrator after
evidence validation. The private reply adapter version is `reply_gemini_v2`;
the frozen output has no separate reply-version field, so reply generation
preserves the original analysis prompt, score, decision and version metadata.
Attempt stage/model identify reply usage separately. An explicit later provider
switch can generate a draft from an earlier grounded analysis; it does not
rewrite qualification provenance or rerun qualification.

## Diagnosing a failed suggested reply

The reply schema is `ReplyDraft`, not an arbitrary free-text response:
`{"parts":[{"kind":"question","text":"<one clarifying question>","product_field":null}]}`.
One to three parts are allowed; up to two optional `product_fact` parts precede
one final question. All three part fields are required; extra fields are forbidden.
Only whole Product fields can be quoted as facts. Every user-facing part must
match the target language; intent/need metadata may be English. For a Persian
target and English Product, omit facts rather than translate or repeat them.
The Agent still rejects pricing/claim words and unsafe punctuation in questions,
invented facts, plaintext, JSON strings, markdown fences and schema deviations.
A single `suggested_reply` string would remove the part-level grounding boundary,
so the existing small parts schema is retained with strict local validation.

`reply_gemini_v2` explicitly describes that output structure and supplies its
schema, target language and quoteable field names as data. Reply repair preserves
the complete system instruction in one message and names the local failed check.
It does not ask for qualification evidence or add a second system instruction.
Qualification prompts, repair and scoring remain unchanged.

Failed Gemini replies now retain private `ProviderError.diagnostics`, including
attempt/stage, `failed_check`, category, expected shape, observed types/known field
names, parsing/Pydantic flags and sanitized schema-error locations. The manual
runner prints `validation_diagnostics` for each failed attempt. Unknown property
names, text values, error inputs/context, raw response bodies and credentials are
never included. Usage stays in the existing frozen records. If repair times out
or returns an HTTP error, the first validation diagnostic and both usage records
are preserved. Errors remain failures; no validation is weakened.

The previous live Persian snapshot contains qualification only. The two failed
reply outputs were not retained, so their historical failing check is unknown.
The shared repair previously requested evidence IDs/quotes even for the parts
schema; that confirmed instruction mismatch is fixed, but is not proof of which
historical payload/check failed. Synthetic offline regressions cover the possible
failure categories without claiming to replay that missing provider output.

For one manual reply-only retest, use the existing authorized snapshot and the
same explicitly configured Gemini environment/key:

```powershell
Set-Location 'C:\git\shared\SignalX\backend'
$env:LLM_PROVIDER = 'gemini'
$env:GEMINI_MODEL = 'gemini-3.5-flash-lite'
$env:GEMINI_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/openai/'
.\.venv\Scripts\python.exe -m app.agents.smoke_test --provider gemini --scenario reply --analysis-file 'C:\Users\Partofix.com\AppData\Local\Temp\signalx-gemini-persian-45e55361-a0e2-4cbe-9628-dee70a6a0177.json'
```

No new qualification is requested. Expected reply requests: one, at most two with
one repair, paced by the existing runner. The user reports that the subsequent
live reply-only retest succeeded: analysis was unchanged, reply usage was
appended, language matched, qualification was not repeated, and no message was
sent automatically. No additional live calls were made during finalization.

## Usage, free tier and costs

`prompt_tokens` maps to `input_tokens`; `completion_tokens` maps to
`output_tokens`. Only returned nonnegative integer measurements are accepted;
missing, malformed or unavailable counts stay null. Total tokens are never used
to fabricate individual counts. Usage records contain the actual reported model
(otherwise the requested model), real mode, attempt number, stage, measured
latency and outcome. Repairs and replies have their own records. Failed calls
also retain attempt records; an undispatched configuration failure has none.

The frozen cost status permits only `known`, `unknown`, `mock`. It has no status
for a verified free-tier entitlement or no-charge billing. Neither the selected
model nor token usage proves the account tier or charge. Gemini therefore keeps
`estimated_cost=null`, `cost_status="unknown"`, `price_version=null`, including
cached usage. This is deliberately **not a claim that free tier costs zero**.
Check the account separately if a no-charge entitlement matters. AvalAI pricing
variables never apply to Gemini, and no new Gemini prices are invented. Toman
reporting likewise stays null. AvalAI's verified rate mechanism is unchanged.

## Secure PowerShell setup and one first live test

These commands are for manual execution only. `Read-Host -AsSecureString` keeps
the key out of echoed output and command history. Do not print environment
variables, paste the key into a command, or store it in repository `.env` files.

```powershell
Set-Location 'C:\git\shared\SignalX\backend'
$env:LLM_PROVIDER = 'gemini'
$env:GEMINI_MODEL = 'gemini-3.5-flash-lite'
$env:GEMINI_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/openai/'
$geminiSecret = Read-Host 'Gemini API key' -AsSecureString
$geminiPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($geminiSecret)
try {
    $env:GEMINI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($geminiPointer)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($geminiPointer)
    $geminiSecret.Dispose()
    Remove-Variable geminiSecret, geminiPointer
}
.\.venv\Scripts\python.exe -m app.agents.smoke_test --provider gemini --scenario english
```

This calls the production orchestrator once for the existing English scenario.
Expected HTTP attempts: one, at most two if local output validation needs repair.
No reply is generated by this command. The runner delays the initial call and
spaces every attempt by at least 65 seconds; this is conservative pacing, **not
a guarantee of Google account quota**. Run sequentially, avoid other concurrent
manual calls, and inspect the account's actual rate limits. Do not endlessly
retry auth, schema, model, quota or balance failures. Import/`--help` make no calls.
The user reports successful live English, Persian and context qualification,
plus suggested reply generation, with `gemini-3.5-flash-lite`. Automated tests
use fake HTTP responses; no live requests were made during finalization. These
live smoke tests verify functionality, not model accuracy across a population.

After separately authorizing further checks, the same fixtures support Persian
and contextual qualification. A new local snapshot permits reply-only execution
without duplicate qualification:

```powershell
# Each command is a separate explicit request; do not paste/run as a batch.
.\.venv\Scripts\python.exe -m app.agents.smoke_test --provider gemini --scenario context
$geminiAnalysis = Join-Path $env:TEMP ('signalx-gemini-' + [guid]::NewGuid().ToString() + '.json')
.\.venv\Scripts\python.exe -m app.agents.smoke_test --provider gemini --scenario persian --save-analysis $geminiAnalysis
.\.venv\Scripts\python.exe -m app.agents.smoke_test --provider gemini --scenario reply --analysis-file $geminiAnalysis
```

Each qualification/reply is one operation with at most one repair. Snapshots must
be new files and contain real paired inputs/outputs; they are private local
artifacts, not credentials, and require appropriate handling of community data.
Reply eligibility still rejects IGNORE and preserves REVIEW without approval.
`--replay-analysis <snapshot>` revalidates offline without credentials or calls.
Reports include the selected provider, requested model, actual attempt model,
versions, signals, evidence, usage and request count; both provider keys are
redacted if echoed. CLI `--provider` must match the environment for live runs.
Offline replay derives the adapter from the recorded prompt version, reports
the recorded attempt models, and leaves historical requested model/endpoint
null because the frozen snapshot does not contain them. `responses` provenance
cannot distinguish AvalAI from direct OpenAI without external run records.

## Explicit recovery to AvalAI

Stop the failed Gemini run, inspect the sanitized diagnostic and actual account
settings, then explicitly choose the existing provider for a separate operation:

```powershell
$env:LLM_PROVIDER = 'avalai'
$env:OPENAI_BASE_URL = 'https://api.avalai.ir/v1'
$env:OPENAI_MODEL = 'gpt-5.6-luna'
# OPENAI_API_KEY must already contain your private AvalAI key, never the Gemini key.
# Keep only verified AvalAI-specific pricing; see ../ACCEPTANCE.md.
```

No request is made by these assignments. A new explicit orchestrator/reply call
uses AvalAI; the Agent never performs this recovery automatically. The original
error and usage must remain visible to the caller. Existing AvalAI manual
commands and verified pricing are documented in [README](README.md) and
[acceptance guide](../ACCEPTANCE.md).
