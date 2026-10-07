# Cross-business real-provider acceptance

This is a manually invoked nine-analysis acceptance run through the production
`analyze_agent(AgentInput)` entry point, not a production behavior change.
[Fixture profiles/messages](cross_business_cases.json) contain the user's three
businesses and three unchanged target messages. Each target is analyzed against
each business, in business-major order, using independent inputs and empty context.
Expected business labels are used only for reporting; never sent to the model.
No qualification history, other product profile or other target enters a request.

## Completed live acceptance run

**Nine-case live acceptance run passed.** The operator reported a manual AvalAI
run using `gpt-5.6-luna` at `https://api.avalai.ir/v1/responses`: all nine analyses
completed with one request each, no repairs, and final status `automated_pass`.
All three matched-business ranking checks, evidence grounding and the bounded
cross-business leakage check passed.

| Target | Highest-fit business | Product fit | Score | Decision |
| --- | --- | --- | --- | --- |
| Message 1 | Python Starter Course | 0.98 | 83 | RESPOND |
| Message 2 | PawCare Veterinary Clinic | 0.95 | 86 | RESPOND |
| Message 3 | LedgerFlow | 0.92 | 82 | RESPOND |

These are reported observations from this acceptance run, not fixed expected
outputs, threshold-tuning data or a statistical accuracy benchmark. The bounded
automated leakage check still requires the semantic human review described below.
Finalization uses offline checks only; this live run is not rerun.

## Manual invocation

Select Gemini in the existing PowerShell session where `GEMINI_API_KEY` is already set:

```powershell
Set-Location 'C:\git\shared\SignalX\backend'
$env:LLM_PROVIDER = 'gemini'
$env:GEMINI_MODEL = 'gemini-3.5-flash-lite'
$env:GEMINI_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/openai/'
.\.venv\Scripts\python.exe -m app.agents.cross_business --provider gemini
```

Or select AvalAI in the existing session where `OPENAI_API_KEY` is already set:

```powershell
Set-Location 'C:\git\shared\SignalX\backend'
$env:LLM_PROVIDER = 'avalai'
$env:OPENAI_BASE_URL = 'https://api.avalai.ir/v1'
$env:OPENAI_MODEL = 'gpt-5.6-luna'
.\.venv\Scripts\python.exe -m app.agents.cross_business --provider avalai
```

Both commands execute the **same nine-case matrix** and ranking checks through
the production factory. `LLM_PROVIDER` must match the explicit CLI selection.
Only the selected provider's environment variables are required; AvalAI does
not require `GEMINI_*`. The default CLI choice remains Gemini. AvalAI requires
its own endpoint explicitly, preventing a mislabeled OpenAI run. The actual
selected provider, reported model and configured endpoint appear in each row.

Do not paste a secret into this command or print environment variables.
`--json-only` omits the text comparison table while retaining results/rankings.
Importing the module or using `--help` does not make requests. Running the command
without `--help` explicitly requests paid-capable real calls; tests use fake HTTP.

## Request safety

Exactly nine analysis operations; normally nine selected-provider HTTP requests, at most
18 if each independently needs its single existing repair. One scoped client
uses the existing acceptance pacer: an initial 65-second wait and at least 65
seconds between **every** attempt, including repairs. There is no parallelism.
Expect about ten minutes normally, up to about twenty minutes with every repair.
Avoid other simultaneous manual calls; pacing does not coordinate account-wide
traffic or guarantee quota. HTTP/auth/quota/rate-limit/provider failures stop the
matrix immediately with completed results, failed-attempt usage and dispatched
request count. There is no automatic 429 retry, Mock or alternative-provider fallback, suggested
reply call, message sending, database access or persistence. Interrupted calls
may still be processed by the provider; counts do not establish account charges.

## PASS / FAIL and interpretation

The automated result is `automated_pass` (exit 0) only if all nine valid runs have
strictly greater matched-business `product_fit` than both unrelated businesses:

- Message 1: Python Starter Course.
- Message 2: PawCare Veterinary Clinic.
- Message 3: LedgerFlow.

Fit ties fail, even when score sorting displays the matching business first.
There is no prescribed score, forced decision, tuned minimum gap or threshold
change. Fit margins and score margins are printed. Higher matched scores and
need strengths are diagnostic comparisons; inspect negative or tiny margins.
Need strength can legitimately reflect the author's actual need across profiles.
Unrelated REVIEW decisions are inspectable, rather than arbitrarily rejected.

Each run must retain screening, bounded qualification signals, supplied-source
evidence, the selected provider's existing prompt version (`qualify_gemini_v1`
for Gemini, `qualify_real_v1` for AvalAI), `score_v1`, correct real attempt metadata and an exact
match to the existing deterministic scorer **including guards and decision reason**.
Evidence uses only the supplied target/context IDs and exact quotes. Unknown
cost stays null/unknown. AvalAI estimates use the existing optional environment
rates (`OPENAI_INPUT_USD_PER_MILLION`, `OPENAI_OUTPUT_USD_PER_MILLION`,
`OPENAI_PRICE_VERSION`) only when the production provider can price the returned
usage. Cached input, model mismatch or missing usage remains unpriced. Estimates
are not exact account charges. Gemini cost remains unknown. No LLM score or
decision is accepted.

Checks reject unsupported numeric claims and recognizable invented monetary
amounts in need/intent/evidence reasons/limitations. A supplied `12-person`
headcount is allowed; it does not authorize an invented `$12` price. Foreign
business names or whole profile fields absent from the current sources are
rejected. `no_cross_business_fact_leakage=true` denotes this bounded automated
check, **not a proof against paraphrased or other semantic hallucinations**.

The report includes all six signals, intent, need, limitations, exact evidence,
decision reason and per-attempt usage. Final human acceptance additionally
requires reviewing those fields for invented prices (including spelled-out
amounts), capabilities and cross-business facts; `human_review_required=true`
stays explicit. The runner never turns a failed check into success. Ranking
failure or local validation exits 2; provider failure exits 1 with partial results.

Offline regression results measure runner/Agent plumbing, source isolation,
ranking logic, grounding, scoring and error handling using synthetic responses.
They do **not** establish either provider's genericity, accuracy or expected live scores.
These nine live examples likewise cannot establish population model accuracy.

## Diagnosing provider failures

For Gemini, `provider_diagnostics` reports the request stage/attempt, HTTP status when a
response was available, body presence, transport/timeout/client/HTTP failure
kind, safe exception type and known DNS/TLS/connection cause category. It also
reports the configured timeout. Recognized Google codes/statuses are preserved;
Google message text is reduced to a fixed category summary, never echoed. Quota,
rate-limit, auth/permission, request/schema, model/endpoint and server categories
remain failures. Unknown categories are reported as unknown, not guessed.

AvalAI uses existing RealProvider errors and attempt usage without translation
or fallback. HTTP failures report a sanitized status/category; timeout and
transport failures remain errors. Google-specific diagnostics are not invented
for AvalAI responses.

The matrix and smoke CLI use the same real factory, config, endpoint, prompt,
schema and httpx options; only fixture data, run count and request budgets differ.
Neither diagnostic path changes acceptance criteria, transport settings or retry
policy. In particular, the first reported 65.595-second failure includes the
initial pacing wait: it does not by itself prove a 30-second network timeout.
The old generic non-timeout request error discarded the exception category, so
the exact historical DNS/TLS/proxy/network cause cannot be recovered from that
report. Repeating the **same** full matrix manually captures the new diagnostics
if it fails again, without a one-case shortcut or extra automatic paid request.
