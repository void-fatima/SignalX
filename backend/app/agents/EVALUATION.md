# Offline lead-discovery evaluation (Step 8)

This framework evaluates **lead discovery**, not automatic outreach. No HTTP,
provider construction, database access, sending or threshold search occurs.
Production screening, qualification, grounding and `score_v1` remain unchanged.
Step 8 preserved the AgentInput/AgentOutput contracts. Step 9 subsequently adds
optional decision/version metadata; see [contract alignment](CONTRACT_ALIGNMENT.md).
Historical datasets and baseline recordings are preserved without backfilled versions.

## Labels and independent split

[eval_data/cases.json](eval_data/cases.json) contains 64 typed inputs with **no
labels**: 63 explicitly authored examples and one observed development input.
[eval_data/labels.json](eval_data/labels.json) contains the separate labels,
rationales, acceptable decisions and policy-sensitive flags. There are 40 dev
cases (39 conversations) and 24 held-out cases (23 conversations), with 32
English and 32 Persian targets overall. Both splits cover purchases,
recommendations, contextual objections, ambiguity, technical questions, noise,
third-party needs, injection attempts, product fit and not-fit. Paired positive
and negative turns in the same conversation stay together.

Labels are **assistant-authored provisional judgments**, not independently
adjudicated human gold. The split is independent by conversation/family group;
it is not a statistically independent or representative sample of community
traffic. Setayesh should review labels blind to predictions before using these
numbers for product decisions. The known smoke-test conversation is dev-only.

Rubric `review_worthy_lead_v1`:

- Positive: plausible personal product/problem interest that should reach human
  review or a suggested-response workflow. A confirmed purchase is not required.
  Relevant contextual ambiguity is positive but policy-sensitive, usually REVIEW.
- Negative: unrelated/no-need content, technical discussion alone, another
  person's need without the author's buying action, attack instructions alone,
  clear personal rejection or explicit incompatible requirements.
- A price objection with relevant context can warrant REVIEW. Expense about
  unrelated tickets/travel, or an explicit refusal to buy, is negative. Price
  mentions do not universally require REVIEW or establish product fit.
- REVIEW is retention for human triage, never approval or permission to send.
  `acceptable_decisions` is a separate policy assessment, not scoring input.

Dataset artifacts are versioned and SHA-256 frozen in
[manifest.json](eval_data/manifest.json), using canonical LF endings so Windows
Git checkout conversion does not invalidate content. Validation rejects missing/duplicate
labels, conversation/family overlap, inconsistent source IDs, duplicate source
content under different IDs, target inclusion, duplicate context IDs and future
context. Public ContextMessage lacks conversation_id; consistent authored
source membership can be checked, but unknown external membership cannot be
recovered from that frozen schema.

All labels and splits were authored before prediction runs. Scoring/thresholds
were not tuned on dev or test. Never tune on the holdout. After consulting test
errors, use new independently labeled conversations for any future confirmation
of changes; do not relabel the current test to match predictions. Authoring code
requires a new empty destination and cannot overwrite existing frozen artifacts.

Four not-fit probes explicitly use the existing extended legacy ProductSnapshot
with `best_fit`, `problems_solved`, and `not_fit`. They are labeled
`extended_legacy_profile`, separated in report breakdowns and not silently added
to public inputs. The public frozen ProductInput has no such fields. All other
cases use `public_contract`. Recorded-real replay rejects extended profiles to
avoid comparing a recording against facts the model never received.
Because this bundled holdout contains extended-profile probes, a complete
comparable real benchmark needs a separately frozen public-only dataset or a
coordinated profile-capable contract. Do not silently drop these rows after
seeing their outcomes; no such full real benchmark is claimed here.

## Three distinct evidence sources

| Mode | What runs | What the result supports |
| --- | --- | --- |
| `offline_heuristic` | Existing screen → deterministic qualify → strict evidence validation → existing scorer | Behavior of current deterministic heuristics on these provisional labels |
| `recorded_real_provider` | Paired real snapshot replay; strict input association, grounding, screening and score verification | The observed decisions in the provided recordings only; zero new calls |
| Live LLM quality evaluation | Not implemented or executed by this offline CLI | Requires explicit authorization, a predeclared complete independent sample and real provider requests |

Offline heuristic results **do not measure Luna accuracy**. MockProvider is not
used to substitute real results. Heuristic outputs have empty usage; tokens and
costs are not fabricated. Replay preserves original usage/cost and never
requalifies. Historical prompt/score versions absent from old recorded outputs
remain null; current code fingerprints and scoring verification version are
reported separately. User-run provenance is observational, not a signed API
receipt or proof of exact account charges.

Recorded dev subsets report their population coverage. Partial held-out
recordings are rejected: all labeled test cases must have predictions before
an independent recorded test report can be generated. Missing, failed and
screened-out cases may not be dropped to improve metrics.

Completed recordings use `snapshot` and default `status="completed"`. A
screened-out snapshot has null qualification/scoring and empty usage, as returned
by the production orchestrator. Failures use `status="failed"`, `failed_input`,
actual `failed_usage`, and optional recorded `failed_screening`, with no snapshot.
This private record format represents errors without inventing successful public
AgentOutput objects or provider measurements. Unknown screening remains unknown.

## Metrics

The primary `discovery` report defines positive prediction as **REVIEW or
RESPOND**. Precision = TP/(TP+FP); recall = TP/(TP+FN). The secondary
`respond_only` report preserves the legacy RESPOND-only metric and does not
imply every true lead should be RESPOND.

Confusion matrices include TP/FP/FN/TN, with explicit FP and FN case IDs.
Screening recall = retained labeled positives / all labeled positives. Unknown
screening on a positive makes this metric null; unknown screening on a negative
does not prevent computing it. Screened-out positives and delivery failures
remain false negatives. Failures on negative rows are operational non-retentions,
not proof that their classification was correct; failed counts stay visible.
Undefined denominators are null, never an invented zero or perfect accuracy.

REVIEW coverage = REVIEW/all cases. Positive REVIEW coverage = positively
labeled cases sent to REVIEW/all labeled positives. Decision breakdown includes
IGNORE, REVIEW, RESPOND and failed. Language, category and input-surface
breakdowns expose uneven performance. Acceptable-decision coverage is reported
separately. Labels never enter qualification or provider inputs.

## Reproduce without credentials or paid calls

From the backend directory:

```powershell
Set-Location 'C:\git\shared\SignalX\backend'
.\.venv\Scripts\python.exe -m app.agents.evaluate_offline --mode heuristic --split dev
.\.venv\Scripts\python.exe -m app.agents.evaluate_offline --mode heuristic --split test
.\.venv\Scripts\python.exe -m app.agents.evaluate_offline --mode recorded --split dev --records app/agents/eval_data/recorded_context.json
```

Use `--output <new-path.json>` to save a new UTF-8 report; existing files are
never overwritten. Errors suppress raw exception values, headers and keys. An
environment key echoed anywhere in a report is redacted before serialization.

The pure legacy `evaluation.evaluate(labels, predictions)` and existing
`scripts/evaluate.py` remain compatible and default to RESPOND-only positives.
New discovery metrics require `positive_decisions=("review", "respond")`.

## Baseline results — no scoring changes

Saved artifacts include dataset hashes and current screen/qualify/score file
fingerprints. These are descriptive **offline heuristic** numbers:

| Split | N | TP / FP / FN / TN | Precision | Recall | Screening recall | REVIEW coverage | IGNORE / REVIEW / RESPOND |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| Development | 40 | 15 / 2 / 3 / 20 | 88.24% | 83.33% | 100% | 32.50% | 23 / 13 / 4 |
| Held-out test | 24 | 9 / 2 / 2 / 11 | 81.82% | 81.82% | 100% | 33.33% | 13 / 8 / 3 |

See [development report](eval_data/heuristic_dev_report.json),
[held-out report](eval_data/heuristic_test_report.json) and
[recorded context report](eval_data/recorded_context_report.json). Zero evaluation
failures occurred. RESPOND-only precision/recall were 100%/22.22% on dev and
100%/27.27% on test; these small descriptive samples cannot establish safe
production response quality. All four discovery false positives were explicit
not-fit legacy-profile probes routed to REVIEW, not RESPOND.

Development false negatives: relevant short English/Persian ambiguous replies
(32, IGNORE), and a Persian learning-option comparison (36, IGNORE). Holdout
false negatives: English/Persian contextual suitability questions (32, IGNORE).
Screening retained all of them. This locates losses after screening; it does
not justify screening changes or tuning test thresholds. Persian lexical fit
and uncertain-intent interpretation deserve future dev-only investigation.

## The actual real context result

[recorded_context.json](eval_data/recorded_context.json) archives the supplied
user-run snapshot with its original file checksum. Target: “آره ولی خیلی گرونه.”
Context: “کسی دوره Python Starter رو امتحان کرده؟ برای مبتدی‌ها مناسبه؟” The
sources have distinct IDs and aware timestamps; production assigns supplied
context to the same conversation. The target quote is exact and grounded.

The real model recognized a price concern but explicitly declined to infer the
author's personal Python-learning need, skill level or purchase commitment from
another author's context. That caution is reasonable. Its signals are purchase
0.25, fit 0.20, need 0.20, urgency 0.05, confidence 0.86 and response opportunity
0.70. The current formula yields **29.1 → 29 → IGNORE**; no arithmetic or guard
error occurred. The snapshot's actual usage is 1,170 input / **390 output**
tokens, distinct from the earlier failed attempt's reported 438 output tokens.
Recorded estimate is USD 0.000702; no new cost or tokens were generated.

Under this provisional high-recall discovery rubric, **REVIEW is preferable for
this specific unresolved course-price concern**: context makes the referent
relevant and a clarifying response might help, while purchase/fit remain unknown.
It is therefore one policy-sensitive recorded false negative (coverage 1/40 dev
cases), not evidence of population model recall. Under a stricter confirmed-buying
definition IGNORE could reasonably be correct. Setayesh should adjudicate this
product policy before calibration.

No weights, signals, scores, thresholds, production guards or prompts were
changed. Raising fit or urgency without source support would be wrong. A single
recorded example and a small synthetic set do not justify a global threshold
reduction or promoting every price objection. A future targeted uncertainty
policy or qualification prompt trial needs reviewed dev labels, negative controls
for explicit rejection/unrelated expense, and new independent recorded test
conversations. This framework measures that tradeoff without deploying it.

## Remaining limits

Small, single-product, authored data; provisional policy-sensitive labels;
limited wording diversity; no blind bilingual human adjudication; four legacy
profiles with a wider input surface; one selected real recording; missing
historical prompt/score fingerprints; no representative live corpus, performance
benchmark or statistical confidence claim. User-reported successful English,
Persian, context and reply smoke calls establish functionality, not population
precision/recall. More independently labeled real conversations and recorded
full-test predictions are required before production-quality claims.
