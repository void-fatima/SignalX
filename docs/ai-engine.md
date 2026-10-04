# AI boundary — Setayesh

The Agent is a pure Python/Pydantic boundary; no FastAPI, SQLAlchemy, database
writes or UI. Setayesh owns it. Roham supplies batch-scoped messages, snapshots
and persistence; Fatima renders results from the public API.

`ProductSnapshot + TargetMessage + batch-scoped messages + RunConfig + Provider`
→ `(AnalysisResult, list[UsageEvent])`. These inputs contain no evaluation labels.

| Module | Responsibility |
| --- | --- |
| contracts.py | Typed Agent/provider inputs and outputs |
| screening.py | Normalize and conservatively retain product/context candidates |
| context.py | Select bounded same-conversation context; future messages only offline |
| providers/base.py | Qualification + usage per attempt; ProviderError preserves attempt usage |
| providers/factory.py | Explicit provider selection, no silent fallback |
| providers/mock.py | Deterministic synthetic fixtures; no real tokens or cost |
| qualification.py | Revalidate signals and evidence grounded in target/context |
| scoring.py | Named weights, deterministic half-up score_v1, decision guards |
| pipeline.py | Compose those stages; never writes persistence |
| cost.py | Decimal accounting; caller-supplied versioned USD/million rates |
| evaluation.py | Confusion matrix over ALL labels; validate dev/test conversation split |

Mock still uses synthetic vectors, including fixture urgency values, and is not
a semantic purchase classifier. Product-specific screening is a development
heuristic, not validated recall. Prompt-injection handling in Mock demonstrates
data treatment; it does not prove a future real model is immune.

## Real adapter integration, next stage

Choose a provider/model with Setayesh before implementing its SDK/network calls.
The existing Provider protocol requires a validated Qualification and usage list;
on failure raise ProviderError with usage of every attempted call. Never discard
usage after invalid output or evidence. Target and context remain untrusted data;
the system prompt must forbid following their instructions, inventing evidence,
budget or urgency, or attributing someone else's needs to the target author.

Real mode needs explicit credentials, bounded timeout/output, up to two retries
only for transient failures, versioned prompts and rates, and budget preflight.
Unrecognized rates block paid execution; an unsuccessful call can still cost
money. cost.py computes ordinary input/output cost only; cached/reasoning tokens
need the chosen provider's actual accounting contract. No real adapter or budget
enforcement is implemented by this skeleton improvement.

API output currently admits only mock. A real adapter requires Roham to coordinate
the API provider_mode enum, config_snapshot, usage fields and stored versions;
regenerate OpenAPI/TypeScript/examples together. Do not route a real result
through an API schema or Mock badge that labels it mock.

## Grounded replies, next stage

Agent draft logic is Setayesh's responsibility; draft persistence and response
endpoints are Roham's; Generate/Edit/Approve/Reject/Copy are Fatima's. Use the
run's product snapshot and validated message/context; never promise facts absent
from that snapshot. Approval stores status and does not send a message.
