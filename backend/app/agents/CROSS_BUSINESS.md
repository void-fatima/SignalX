# AvalAI cross-business acceptance

Restored and adapted from commit
[`3a84276`](https://github.com/void-fatima/SignalX/commit/3a84276a6528bc9eb188291d61ca7f09ccad6c84),
originally authored by **Setayesh Samani <setayesh.samani.dev@gmail.com>**.
This adaptation retains the original dataset and acceptance rules while using
current main's AvalAI Responses provider. Gemini is a historical reference only;
this tool adds no provider, fallback, production configuration or contract change.

## Scope and criteria

The [original dataset](cross_business_cases.json) contains Python Starter Course,
PawCare Veterinary Clinic and LedgerFlow, with the same three target messages.
Every target is analyzed independently against every product: **nine analyses**,
in business-major order. Each input has its selected profile, one target, empty
context and a separate run ID. Expected matches stay local to ranking reports;
they are never sent to the model. Analysis uses production `analyze_agent` and
the existing `RealProvider` factory via a scoped, caller-owned HTTP client.

`automated_pass` requires all nine complete, valid results and strictly greater
matched-business `product_fit` than both unrelated businesses. **Ties fail**,
including ties broken by score for display. No fixed score, decision, minimum
margin or threshold tuning is introduced. Score and need-strength comparisons
remain diagnostics rather than forced acceptance decisions.

Each result must have grounded, exact supplied-source evidence, bounded signals,
real qualification usage, `qualify_real_v1`, `score_v1`, and score/decision/reason
matching the existing deterministic scorer and its guards. Unsupported numeric
or recognizable monetary claims and foreign business names/whole profile fields
absent from the current sources fail validation. Supplied headcounts do not
authorize fabricated prices. These bounded lexical checks **do not prove semantic
safety**: inspect intent, need, evidence reasons and limitations for paraphrased
cross-business claims, invented capabilities or prices. Human review stays required.

## Optional manual live invocation

Import and `--help` are offline. The following command explicitly requests a
paid-capable live run; automated tests never execute it. Set the key through your
existing secure process environment. The runner never loads `.env`, prints keys,
generates suggested replies, sends messages or accesses the database.

```powershell
Set-Location 'C:\git\shared\SignalX\backend'
$env:OPENAI_BASE_URL = 'https://api.avalai.ir/v1'
$env:OPENAI_MODEL = 'gpt-5.6-luna'
.\.venv\Scripts\python.exe -X utf8 -m app.agents.cross_business --provider avalai
```

`OPENAI_API_KEY`, `OPENAI_MODEL` and an explicit AvalAI `OPENAI_BASE_URL` are
required. `LLM_PROVIDER` is not required by main's Responses factory; if supplied,
the runner requires `avalai` to reject contradictory selections. No Gemini
configuration is needed. `--json-only` suppresses the comparison table but retains
full results, rankings, evidence and usage. Configuration errors fail before HTTP.

The existing acceptance pacer waits initially and spaces **every request** by at
least 65 seconds, including repairs. Execution is sequential: normally nine
requests, maximum 18 if every analysis needs its single existing repair. Expect
roughly ten to twenty minutes plus provider latency. Pacing does not coordinate
other processes or guarantee account quota. Auth, quota, rate-limit, transport and
provider errors stop remaining cases; there is no HTTP-error retry or fallback.
Interrupted/dispatched requests may still incur charges.

Usage preserves actual reported model/tokens/latency and per-attempt outcomes.
Unknown tokens and cost remain null/unknown. Optional existing environment rates
(`OPENAI_PRICE_VERSION`, `OPENAI_INPUT_USD_PER_MILLION`,
`OPENAI_OUTPUT_USD_PER_MILLION`) price only usage supported by the provider's
existing rules; cached/unknown-cache usage and model mismatches stay unpriced.
The existing report converts USD estimates at 270000 toman/USD for reporting;
this is not a live exchange quote or an exact account charge.

Exit codes: 0 automated pass; 1 provider failure; 2 ranking/configuration/local
validation failure; 3 unexpected local failure; 130 interruption. Failures retain
completed rows and available failed-attempt usage without becoming warnings.

## Offline validation and historical evidence

```powershell
Set-Location 'C:\git\shared\SignalX\backend'
.\.venv\Scripts\python.exe -m pytest tests/test_cross_business.py -q
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip check
```

Tests use synthetic HTTP and a fake clock through the production Agent path.
They verify source isolation, strict ranking, grounding, scoring, usage/cost,
bounded repair, pacing and failure propagation. They **do not measure real-model
quality**. Use a disposable working directory/process without local environment
files when running application-wide tests; existing application settings may load
an `.env` relative to their working directory.

The original commit records an operator-reported **nine-case live acceptance run
passed** using AvalAI `gpt-5.6-luna`, one request per analysis, no repairs. That
historical result is not a rerun of this adaptation, a statistical accuracy
benchmark, a deployment verification or a fixed expected output. No live requests
are made as part of this restoration. A future live run requires separate explicit
operator invocation and semantic review.
