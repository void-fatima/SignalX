# Manual AvalAI acceptance run

This runner calls the production `analyze_agent` and
`generate_suggested_reply` entry points with `provider_mode="real"`.
HTTP goes to `https://api.avalai.ir/v1/responses`, authenticated only from
`OPENAI_API_KEY`. No Mock substitution, application persistence, outreach,
parallel requests, endpoint/model fallback or HTTP-error retries are used.
Importing the module and `--help` never make requests. Automated tests use fake
HTTP and a fake clock; they do not prove live model quality.

## Verified price configuration

The [AvalAI Luna model reference](https://docs.avalai.org/fa/models/gpt-5.6-luna)
lists USD **0.20 per million input tokens** and **1.20 per million output
tokens** for the base context tier. The page documents different rates above
272,000 input tokens; these small fixtures use the base tier. Reporting refuses
to apply these base rates to reported input above that threshold.

In the existing PowerShell session that already has `$env:OPENAI_API_KEY`:

```powershell
Set-Location 'C:\git\shared\SignalX\backend'
$env:OPENAI_BASE_URL = 'https://api.avalai.ir/v1'
$env:OPENAI_MODEL = 'gpt-5.6-luna'
$env:OPENAI_INPUT_USD_PER_MILLION = '0.20'
$env:OPENAI_OUTPUT_USD_PER_MILLION = '1.20'
$env:OPENAI_PRICE_VERSION = 'avalai-gpt-5.6-luna-verified-2026-10-06'
$env:PYTHONIOENCODING = 'utf-8'
```

The price-version string is our verification label, not an AvalAI release ID.
Configuration reads process environment and does not automatically load `.env`.
No API key needs to be pasted into these commands. New acceptance scenarios
refuse missing/different rates before dispatching any HTTP request.

Each attempt reports actual returned tokens, model, outcome, price version,
estimated USD and reporting-only toman at **270,000 toman/USD**. Estimates are
not exact account charges. Missing tokens/cache metadata, nonzero cached input,
or a returned model that differs from the configured model leave cost
null/unknown. Missing usage is never replaced with zero. Repair usage remains
separate even when its output is invalid. Provider failures preserve attempt
records; an interrupted request may have reached AvalAI without known usage.

## Recommended: run the complete bounded sequence once

```powershell
.\.venv\Scripts\python.exe -m app.agents.smoke_test --scenario acceptance
```

Order: one Persian qualification, one context qualification, then one explicit
reply request using the Persian analysis already in memory. The reply makes no
duplicate qualification call. This is normally **three HTTP requests**, at most
**six** if each operation needs its existing single repair. On failure, the run
stops and prints completed results plus available failed-attempt usage. Do not
also run the individual commands below for the same acceptance run.

## Alternative: run the three scenarios separately

The explicit snapshot contains the paired real input and analysis, including
usage, for the reply-only command. It is a local CLI test artifact, not Backend
persistence. It never overwrites an existing file and refuses an echoed API key.
It is saved before acceptance assertions, so a failed assertion can be diagnosed
offline. A snapshot is not proof that acceptance passed. Do not edit it or
replace it with invented qualification data.

Execute the following together, after the environment configuration above:

```powershell
$analysisFile = Join-Path $env:TEMP ('signalx-persian-' + [guid]::NewGuid().ToString() + '.json')
.\.venv\Scripts\python.exe -m app.agents.smoke_test --scenario persian --save-analysis $analysisFile
if ($LASTEXITCODE -ne 0) { throw 'Persian acceptance stopped. Inspect the sanitized report.' }
.\.venv\Scripts\python.exe -m app.agents.smoke_test --scenario context
if ($LASTEXITCODE -ne 0) { throw 'Context acceptance stopped. Inspect the sanitized report.' }
.\.venv\Scripts\python.exe -m app.agents.smoke_test --scenario reply --analysis-file $analysisFile
if ($LASTEXITCODE -ne 0) { throw 'Reply acceptance stopped. Inspect the sanitized report.' }
```

Each command dispatches one operation, at most two HTTP attempts. Reply reuses
the snapshot without rerunning analysis. A later run has its own budget, so
do not blindly rerun successful scenarios after a partial failure.

## Rate limits and failure safety

The [model-specific rate table](https://docs.avalai.org/en/models/gpt-5.6-luna)
lists Basic at **one request/minute and 10,000 tokens/minute**. The
[rate-limit guide](https://docs.avalai.org/en/rate-limits) explains model limits
apply at organization level, not just to this API key. Actual account tier,
remaining quota and balance were not queried or verified by this preparation.

The scoped real HTTP client waits **65 seconds before the first request** and
at least 65 seconds between subsequent request starts, including repairs. It
waits in interruptible chunks of at most 30 seconds. Do not run simultaneous
scripts, other paid tests, or other model traffic in the same organization.
Spacing alone cannot guarantee compliance with token-per-minute limits or
shared organization traffic. Keep the normal 2,000 output-token limit for these
small fixtures and check the account dashboard before running.

HTTP 429, authentication, quota/balance, model incompatibility and network
failures stop immediately. No automatic 429 retries or unlimited loops occur.
Only an invalid structured output/evidence/draft permits one paced repair. A
second invalid response stops. The transport has a hard two-attempt budget for
individual scenarios and six for the combined run.

`paid_api_request_attempts` counts paid-capable HTTP dispatches in THIS run,
not confirmed charges. Timeouts can leave billing unknown. `latency_ms` retains
provider wall-clock measurements, which include this client's deliberate
request pacing; it is not pure network/model latency.

## What to inspect in the live reports

- Persian target: “من تازه می‌خوام پایتون یاد بگیرم و دنبال یه دوره مناسب مبتدی‌ها هستم. قیمتش چقدره؟”
  Product: Python Starter Course; Beginner Python course with practical exercises.
- Context target: “آره ولی خیلی گرونه.” Context: “کسی دوره Python Starter رو امتحان کرده؟ برای مبتدی‌ها مناسبه؟”
  IDs are distinct and timestamps are timezone-aware. Production maps both to
  `smoke-conversation`; the public ContextMessage has no conversation ID.
- Screening must retain each target. All six signals are validated in [0,1].
  Every evidence quote must be an exact substring of the supplied source ID.
  Context acceptance checks that intent/need identifies a possible price/cost
  objection. A context citation is optional; if present, its source ID and exact
  quote must pass the same strict grounding guard as every other evidence item.
  `context_evidence_present` reports the actual citation presence, not a required
  pass/fail condition. Scores and guards are checked against `scoring.py`; no
  predetermined score or decision is asserted.
- Read actual intent, need and limitations for sensible Persian interpretation
  and a contextual objection, not a fabricated known price. The runner rejects
  numeric claims in these fixtures' need field, but mechanical checks cannot
  prove complete semantic correctness or causal context use. No extra live
  counterfactual/batch calls are made.
- Reply must match the target language and preserve analysis, score, decision
  and prior usage. New events must be separate reply events. IGNORE refuses
  drafting; REVIEW remains subject to human review. All texts are drafts.
  Inspect naturalness/helpfulness and implicit unsupported claims manually.
  Existing reply grounding permits exact whole Product fields plus a cautious
  question; English product facts are omitted from a Persian draft.
- No supplied price, discount, link, availability or guarantee exists here.
  A safe clarifying question is preferable to an invented commercial answer.
  Nothing is sent or automatically approved.

## Backend handoff

Offline Agent integration is ready for Backend to wire and test using the frozen
contracts and documented entry points. The user reports successful live English
and Persian qualifications and a suggested reply. The original context attempt
failed a local acceptance check after successful provider qualification; the
exact check was not recorded. Context acceptance requires a diagnostic retest.
Unknown cached/model-alias costs
remain an explicit accounting limitation, not a zero-cost success.

Backend owns reconstructing authorized same-conversation input/analysis,
persistence, approvals, account-wide rate/quota coordination and endpoint
integration. This CLI's scoped pacing does not install a production-wide limiter
or change default provider behavior. The Agent cannot prove stored analysis
identity/conversation isolation beyond the information in the frozen contracts.
No Backend-owned code, contract, dependency, commit or push is changed here.

## Context failure diagnostics

The original context report contained one successful provider attempt (1,170
input / 438 output tokens), followed by a generic `validation_error`. No context
analysis snapshot was found, and the user confirms intent/need/evidence were not
included in the report. The historical failing branch cannot be recovered from
token counts. This is a limitation of the old report, not evidence that the model
or source-grounding guard failed.

RealProvider sets `outcome="success"` only after strict schema and exact evidence
validation. Orchestrator then revalidates, grounds and deterministically scores
the same qualification. The CLI adds its own acceptance checks. The old
mandatory-context-quote assertion rejected a valid price-objection qualification
with exact target-only evidence, although neither the frozen contract nor the
qualification prompt requires a context quote. An offline synthetic fixture
reproduces that failure shape; it is not a recovered live model response.

The corrected check validates a possible price-objection interpretation and
reports citation presence separately. Every returned evidence item remains
subject to the unchanged production source-ID and exact-substring validation.
Semantic keyword checks cannot prove causal context use or complete language
understanding; human inspection of the live intent/need remains required.

Every local `validation_error` now reports `failed_check`, `failure_category`,
and a static sanitized `explanation`. Arbitrary exception strings, validation
input values, raw provider bodies, headers and keys are never added to diagnostics.

| Condition | Diagnostic | Scope / timing |
| --- | --- | --- |
| Invalid input, duplicate context IDs, target in context | `input_validation` | Before request; also rechecked during acceptance |
| Screened out / absent qualification, scoring or usage | `screening_retained` / `analysis_complete` | Local completeness check |
| Malformed qualification | `qualification_schema` | Strict schema check; normally provider rejects/repairs first |
| Unknown evidence ID or incorrect/empty quote | `evidence_grounding` | Strict grounding; normally provider rejects/repairs first |
| Empty evidence / intent / need | `evidence_present` / `intent_and_need` | Can occur after provider success because these fields permit emptiness in the frozen schema |
| Wrong score or guarded decision | `deterministic_score_and_guards` | Compares with the existing scorer; no fixed numerical expectation |
| Mock-labeled usage | `real_usage` | Rejects mode mismatch; no fallback |
| No context / no possible price-objection interpretation | `context_supplied` / `context_price_objection` | Scenario semantics; a particular citation pattern is not required |
| Numeric/currency expression in need | `unsupported_numeric_claim` | Conservative fixture assertion retained; inspect whether it is a monetary claim or overly strict for that output |
| Snapshot path/read/write/size/schema/secret/mode failure | `snapshot_*` | Explicit file operation; unrelated to model quality |
| Replay uses a different scenario's input | `scenario_match` | Offline mismatch; no provider call |
| Reply eligibility / analysis changes / usage / language | `reply_eligibility` / `analysis_unchanged` / `reply_usage_appended` / `language_matches` | Separate on-demand reply path |
| Unexpected typed/value error during production analysis | `analysis_output_validation` | Safe phase-level classification; raw exception remains suppressed |

Configuration/pricing preflight failures return `configuration_error` (or a
sanitized configuration ProviderError) before any request. Invalid/malformed
usage or cost models may raise typed validation errors during production
analysis, classified as `analysis_output_validation`; they cannot explain a
normally returned successful usage record from this fixture. Unknown tokens,
cached input and unknown cost are allowed, not validation failures. Invalid
provider evidence/JSON after its single repair returns `provider_error`, not the
CLI's post-success `validation_error`. HTTP errors also return `provider_error`.
Invalid combinations of CLI arguments are parser errors before any request.

To retain one new real context analysis for diagnosis, with the environment above:

```powershell
$contextFile = Join-Path $env:TEMP ('signalx-context-' + [guid]::NewGuid().ToString() + '.json')
.\.venv\Scripts\python.exe -m app.agents.smoke_test --scenario context --save-analysis $contextFile
```

This uses one qualification, at most its existing single paced repair. Do not
rerun Persian or reply just to diagnose context. A later acceptance failure
still exits nonzero; saving the typed analysis never converts failure to success.

If a snapshot was saved, inspect its acceptance checks without any API key,
pricing configuration, HTTP client, new usage or paid request:

```powershell
.\.venv\Scripts\python.exe -m app.agents.smoke_test --scenario context --replay-analysis $contextFile
```

Replay is explicitly labeled `execution_mode="offline_replay"` and has
`paid_api_request_attempts=0`. Usage belongs to the recording; no new live
execution is claimed. It reuses the production grounding and scoring functions.
