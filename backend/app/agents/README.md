Backend integration uses one synchronous Agent entry point:

```python
from app.agents.contracts import AgentInput
from app.agents.orchestrator import analyze_agent

agent_input = AgentInput.model_validate(payload)
agent_output = analyze_agent(agent_input)
result = agent_output.model_dump(mode="json")
```

AgentInput is unchanged. Step 9 adds three optional metadata fields to frozen
AgentOutput; see [contract alignment and integration fixture](CONTRACT_ALIGNMENT.md).
Backend constructs
typed product/message data and supplies selected context from the correct
conversation and batch. ContextMessage has no conversation_id, so isolation
remains Backend's responsibility. The Agent checks at most five context messages
through the existing schema, unique context IDs, and exclusion of the target.
It preserves the supplied context and never retrieves or persists messages.

`analyze_agent` revalidates inputs, screens with context, then uses exactly
`metadata.provider_mode` to select the existing provider factory. Rejected
messages return screening with null qualification/scoring and empty usage;
no provider is constructed or called. Real mode uses RealProvider with the
environment configuration documented in [providers/README.md](providers/README.md).
Mock mode explicitly uses MockProvider and labeled synthetic results/costs;
it is intended for development and tests. No automatic fallback is permitted.

Both providers return qualification only through `qualify_structured`. The
orchestrator revalidates the structured result, verifies exact source quotes
and supplied message IDs, and calls the existing `score_v1` implementation
in `scoring.calculate_score_with_reason`. It calculates the score once and applies the
existing confidence/product-fit/purchase-evidence guards. Missing or context-only
purchase evidence downgrades a numerical RESPOND to REVIEW; invented evidence
raises ProviderError. LLM score/decision fields are forbidden by qualification.

Actual provider attempt records are preserved, including repair history,
unknown token counts and null/unknown cost. The orchestrator does not make
API calls, recalculate costs, create usage measurements, or generate suggested
replies. Every successful return leaves `suggested_reply=null`.

Input errors raise Pydantic ValidationError; duplicate/target context IDs raise
ValueError. Provider failures propagate as ProviderError, with attempt records
in `error.usage`; the orchestrator never substitutes successful fake output.
The existing legacy `pipeline.analyze` and provider `qualify` interfaces remain
available. Backend owns persistence, error-to-HTTP translation and worker/UI
integration. The user reports successful AvalAI English, Persian, context and
reply smoke tests. Step 9 persistence/schema adaptation is documented separately;
the teammate's online Worker integration has not been independently verified here.
Auth/user isolation remains Backend-owned and required for the online product.

Offline integration tests inject HTTP responses into the real provider and
exercise the entire AgentInput-to-AgentOutput flow without paid API calls.

Step 8 adds [offline lead-discovery evaluation](EVALUATION.md): versioned,
conversation-separated inputs/labels, heuristic baselines and strict recorded
real-provider replay. These modes never make provider calls or tune thresholds;
heuristic precision/recall is explicitly separate from real-model quality.

## Explicit suggested replies (Step 7)

Only a separate, explicit call generates a draft:

```python
from app.agents.contracts import AgentInput, AgentOutput
from app.agents.reply import generate_suggested_reply

# Load these exact snapshots from the same authorized stored analysis/run.
agent_input = AgentInput.model_validate(stored_input)
analysis = AgentOutput.model_validate(stored_output)
prior_usage_count = len(analysis.usage)
updated = generate_suggested_reply(agent_input, analysis)
draft_text = updated.suggested_reply
new_reply_usage = updated.usage[prior_usage_count:]
```

For **POST /leads/{id}/response**, Backend must:

1. Authorize access to the lead, product, run, messages and conversation for the
   current user. Generate only after the user's explicit draft request.
2. Reconstruct the exact original Product snapshot, target message and selected
   context associated with the stored AgentOutput. Use the stored run's provider
   mode; do not trust a client-supplied mode. Never combine different analyses.
3. Validate the stored payloads and invoke `generate_suggested_reply` outside a
   database transaction. This synchronous function performs blocking HTTP; an
   async route must run it in its normal thread executor.
4. Persist the returned draft, preserving the lead's screening, qualification,
   score and decision. Persist **only new usage records** from the slice above;
   the returned output includes the full prior history for completeness.
5. Keep a draft pending human review. REVIEW stays REVIEW and does not authorize
   outreach. Backend owns Edit/Approve/Reject state, authorization, persistence,
   idempotency and protection against concurrent/duplicate draft requests.
   Agent never sends community messages or approves leads.

Input/context validation raises ValidationError/ValueError. Eligibility failures
(IGNORE, screened out, absent qualification/scoring/evidence, inconsistent score,
missing successful qualification usage or mode mismatch) fail before any HTTP
call. Provider/configuration failures raise sanitized ProviderError. Its `usage`
contains existing analysis history followed by any failed reply attempts; Backend
must persist only `error.usage[prior_usage_count:]`, even when generation fails.
Configuration errors add no fabricated provider call. Do not log raw inputs,
validation exceptions, HTTP headers, keys or raw provider bodies.

The frozen AgentOutput cannot prove analysis identity: it has no product/message
ID, run ID, input digest or context membership field. Agent checks exact grounded
quotes/IDs against supplied sources, unique context IDs, target exclusion,
screening eligibility, successful qualification provenance, provider mode and
score_v1 consistency. An existing conservative REVIEW is permitted and preserved.
These checks cannot detect changed Product text or a different author/run with
identical evidence. Backend must enforce the persisted association and conversation
isolation. No frozen schema fields were added for this step.

### Request-aware replies (`reply_real_v2`)

Real drafting retains the environment-only credentials, configured model/timeout,
strict structured output, `store=false`, and absence of tools or sending. The
public AgentInput/AgentOutput schemas, qualification prompts and score_v1 are unchanged.

A deterministic local plan prioritizes pricing, demos, product/integration questions,
comparisons, follow-ups and objections. It uses the target and supplied same-author
context, retains exact company-size quotes, and tells the model not to ask again for
known requirements. It does not qualify or score the lead and cannot book appointments.

Pricing/demo requests require an exact safe acknowledgement and a relevant next-step
question. Missing prices are acknowledged, not filled from community claims. A known
price is usable only from a whole Product field, in the reply language, within the
existing 600-character fact limit. The whole field must be quoted, preserving negation
and conditions. Demo requests propose checking whether a demo can be arranged and
never imply availability or a confirmed booking. Other questions retain existing
commercial-claim guards; additional booking/appointment guards reject false commitments.
Every output remains a draft requiring human approval, including REVIEW leads.

Replies default to the target's English/Persian language. An authorized caller may
explicitly pass `language="en"` or `language="fa"` to `generate_suggested_reply`.
This optional Python argument changes neither public schema nor existing API behavior;
no browser control or Backend route has been added for it. Community instructions
cannot choose the language. Facts in a different language are omitted rather than
translated into unverified claims.

Drafting reuses the original Product snapshot and target. Context is deduplicated and
bounded to 4,000 characters of whole messages, prioritizing direct replies/evidence;
omitted source IDs are explicit. No message is truncated in a way that drops a negation.
Qualification need/intent are compact drafting hints, not product facts; duplicate
source quotes and scoring signals are not resent. Input payloads exceeding 20,000
characters fail before HTTP rather than silently trimming Product claims. These are
character budgets, not invented token measurements. Reply requests cap output at the
smaller of the configured limit and 1,200 tokens; qualification retains its own unchanged
limit. Rendered replies are at most 1,200 characters.

Offline fake-HTTP regressions validate request handling, grounding, language, repairs,
usage and budgets. They do not measure live model reply quality. A separately authorized
real review remains needed, with no paid requests performed during implementation.

Every actual call records `stage=suggested_reply` or `suggested_reply_repair`,
attempt number, real model, available tokens, latency and outcome. At most one
repair is made for invalid schema, language or grounding. Transport/API/refusal/
incomplete errors do not retry or fall back. Repair instructions never promote
raw model text into trusted instructions. Both attempts remain billable when usage
is returned, even if invalid. Unknown tokens/cost stay null/unknown; model mismatch,
missing cache metadata or cached input prevent inaccurate two-rate cost estimates.
Mock drafts are deterministic development fixtures with explicit mock mode/cost;
they are never a fallback for real mode.

No reply API route, persistence, authorization or UI was implemented here. No
paid API call was executed automatically by the coding agent; the user's manual
qualification and reply smoke tests succeeded. Configure environment credentials,
model and independently verified versioned rates for any further authorized live
testing. Full Backend wiring and auth/user isolation remain separate team work.
