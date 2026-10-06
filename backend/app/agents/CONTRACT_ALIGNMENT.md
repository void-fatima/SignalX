# AgentOutput alignment (Step 9)

Backend calls `app.agents.orchestrator.analyze_agent(AgentInput)` and persists
the returned output using `output.model_dump(mode="json")`. AgentInput, required
output fields, qualification, scoring and per-attempt usage shapes are unchanged.
AgentOutput adds these optional nullable strings, each defaulting to `None`:

| Field | Source | Null cases |
| --- | --- | --- |
| `decision_reason` | The actual deterministic scoring execution, or screening rejection reason | An old output, or qualification-only provider output before scoring |
| `prompt_version` | The executed real qualification provider's `prompt_version`, currently `qualify_real_v1` from `prompts/qualification.py` | Mock, pure heuristics, screening-only, or old recordings without recorded version metadata |
| `scoring_version` | `scoring.SCORING_VERSION`, currently `score_v1` | No scoring execution, or an old output lacking version metadata |

The current prompt already has an explicit version; Step 9 does not rename it or
change its instructions. The LLM qualification schema contains none of these
metadata fields and still forbids score/decision. Real provider selection remains
explicit, with no fallback. Provider failures propagate with actual attempt usage.

`scoring.calculate_score_with_reason` runs the existing scorer once and exposes
its explanation. The weights, Python rounding, 40/70 thresholds, and guard order
are unchanged. The first applicable guard controls the explanation:

- Below 40: IGNORE; 40-69: REVIEW; 70-100: RESPOND if no guard applies.
- A numerical RESPOND is capped to REVIEW by confidence < 0.60, then product_fit
  < 0.50, then unavailable valid target purchase evidence. The legacy scorer also
  supports an explicit human-review flag; the public orchestrator has no such
  qualification field and does not invent one.
- Invented quotes and unknown source IDs raise ProviderError before scoring.
  They do not become a successful REVIEW. The evidence downgrade concerns missing
  or context-only target purchase evidence, not acceptance of fabricated evidence.
- Screening rejection includes the actual deterministic screening reason and
  leaves qualification/scoring/versions null. There is no invented score.

The legacy `score()` reason codes and legacy pipeline behavior remain compatible.
Direct `RealProvider.analyze()` is qualification-only: it supplies a prompt version
after qualification, but no scoring version or final-decision explanation.
Direct Mock analysis supplies a scoring version and explanation, never a real
prompt version. On-demand replies preserve all three analysis metadata values;
`prompt_version` identifies qualification, not a subsequently generated reply.

## Frozen models and compatibility

Inspection found AgentOutput was not configured as frozen in the pre-Step-9 code.
It now explicitly uses Pydantic `frozen=True`, inheriting strict extra-field
rejection and finite-number validation. Field reassignment raises ValidationError.
Pydantic freezing is shallow: nested objects/lists retain their existing semantics;
consumers must treat stored analysis as immutable and use new validated objects.
Other models/configurations and the AgentInput shape are unchanged.

Old JSON fixtures without these optional fields still parse, with null defaults.
New JSON contains three additional keys. A consumer pinned to the old strict
`extra="forbid"` output schema must upgrade its model before reading new outputs.
Never backfill absent historical prompt/scoring versions using today's constants.
Step 8 dataset labels, checksum manifest and saved baseline artifacts remain intact;
new heuristic evaluations include a scoring version, while replay retains missing
historical metadata as null. Neither mode claims to have made an LLM call.

## Persistence semantics owned by Backend

- `qualification.need` describes the customer's apparent need/problem.
- `decision_reason` explains why Agent selected the final decision. It is not
  interchangeable with `qualification.need`.
- Mapping Lead `reason` to `qualification.need` is acceptable only when that
  database field represents a need summary. Persist `decision_reason` separately
  if a decision explanation is required, along with nullable prompt/scoring versions.
- Preserve unknown budget as `"unknown"` where the Backend/legacy schema needs it.
  A price objection does not establish budget or invent a product price.
- Preserve actual attempt records, including failures/repair and reply stages.
  Unknown tokens remain null. Missing/null cached_tokens, cached tokens > 0,
  unmatched billed model, or missing applicable rates keep estimated_cost null
  and cost_status `"unknown"`. Only explicit integer cached_tokens=0 permits the
  existing two-rate calculation when model/rates/token counts are valid.
  Estimates are not exact account charges. No cost/usage fields were changed.
- Screening-only outputs have no scoring decision. Backend may map a rejected
  screening result to its existing IGNORE persistence representation without
  fabricating a score/version or overwriting the Agent explanation.

The current repository exposes separate Backend API schemas rather than
AgentInput/AgentOutput in OpenAPI. This Agent-only addition does not change that
API shape. Backend must coordinate any future API exposure and regenerate
OpenAPI/TypeScript with the team. Worker, database, routes and frontend were not
modified here. User-reported online Worker integration is not independently
verified by offline Agent tests; persistence and authorization remain Backend-owned.

In this checkout, `backend/app/models/__init__.py` already has a nullable
`decision_reason` column, but `prompt_version` and `scoring_version` are non-null
strings with historical defaults. `backend/app/schemas/api.py` likewise requires
string versions and still declares an API mock-only provider mode. The local
`analysis_service.py` uses the legacy pipeline, rather than the teammate's reported
new Worker integration. Roham must review a nullable-version migration and API/schema
alignment (or verify those changes on the integration branch), so Mock and
screening-only nulls are stored truthfully. Do not replace them with default
versions for prompts/scoring that never ran. No new decision-reason column is
needed where the existing analysis column can be used correctly.

## Shareable integration fixture

[fixtures/backend_integration.json](fixtures/backend_integration.json) is
Agent-owned. Each example contains a valid `agent_input`, a complete `analysis`,
and synthetic provider usage inputs for offline fake-HTTP reproduction. Cases:

1. Grounded qualified lead: score 80, RESPOND, null cached_tokens and unknown cost.
2. Confidence-guarded lead: score 76, REVIEW, missing cached_tokens and unknown cost.
3. Screening-only noise: no qualification, score, prompt, scoring version or usage.

These are authored fixtures with real-shaped telemetry, **not recorded paid API
results**. Metadata, scores, evidence and usage are checked against actual production
entry points with fake HTTP. Product/message/run identifiers are UUID strings;
cases use distinct run IDs to avoid conflating separate analysis executions.
Even with valid rates, null/missing cache metadata
keeps their costs unknown. No authorization header or key is stored.

The canonical Backend-owned response example is `contracts/examples/lead.json`;
it represents a different HTTP/persistence shape and was not edited. Backend can
adopt the Agent-owned input/output pairs for Worker → Agent → Persistence tests,
mapping decisions to its lowercase storage enum as needed and keeping nulls intact.
Contract alignment is ready on the Agent side; safe end-to-end adoption requires
Backend tests confirming independent need/reason/version persistence and usage
round-tripping. No new paid calls are necessary to exercise these fixtures.
