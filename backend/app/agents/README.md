Backend integration uses one synchronous Agent entry point:

```python
from app.agents.contracts import AgentInput
from app.agents.orchestrator import analyze_agent

agent_input = AgentInput.model_validate(payload)
agent_output = analyze_agent(agent_input)
result = agent_output.model_dump(mode="json")
```

The frozen AgentInput/AgentOutput schemas are unchanged. Backend constructs
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
in `scoring.calculate_score`. It calculates the score once and applies the
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
integration, which this change does not implement. Contract review and live
provider verification remain pending; auth/user isolation is also outside this
Agent integration and remains a requirement for the online product.

Offline integration tests inject HTTP responses into the real provider and
exercise the entire AgentInput-to-AgentOutput flow without paid API calls.
