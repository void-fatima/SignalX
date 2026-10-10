# Discover Leads

Discovery is separate from CSV imports and conversation leads. Search, preview and save do not call an LLM, generate contacts, approve replies or send messages. Public-source matches do not prove purchase intent.

## Deployment and credentials

Apply additive migration `0009` **after Telegram recovery `0008`**, using the existing backend Alembic deployment procedure (`python -m alembic upgrade head`). It creates only `discovery_searches`, `discovery_prospects` and `discovery_budgets`; existing records and migration history remain unchanged. Deploy the migration before the new API; readiness checks require the new tables. Downgrading removes discovery records only. No application or production database migration was executed during implementation; PostgreSQL tests use their own unique schemas in an isolated test database.

Set secrets on the backend, never in Next.js variables:

| Source | Configuration | Coverage |
| --- | --- | --- |
| Brave | `BRAVE_SEARCH_API_KEY`, `DISCOVERY_BRAVE_STORAGE_ALLOWED=true` | Public web search. Enable storage only after verifying the subscribed plan permits it. |
| Greenhouse | No API key; one known company board slug | Public postings from that company, not universal company discovery. |
| Lever | No API key; one known company site slug | Public postings from the global Lever endpoint. EU-instance boards are not implemented. |
| Google Places | `GOOGLE_PLACES_API_KEY`, `DISCOVERY_PLACES_ENABLED=true` | Optional billed Text Search. **IDs only**: listing names, addresses and other Places content are neither requested nor retained. Open the original Maps listing to inspect the business. |

Places is deliberately limited to the place-ID storage exception. Operators must review Google billing, attribution, terms and quota requirements before enabling it; this implementation does not claim full local-directory coverage. Retained IDs cannot be AI-qualified because they provide no source excerpt.

Optional AI evaluation uses the existing production Agent, with `PROVIDER_MODE=real`, `LLM_PROVIDER=avalai`, `OPENAI_BASE_URL=https://api.avalai.ir/v1`, `OPENAI_MODEL` and `OPENAI_API_KEY`. Existing price-version/rate environment settings are optional; unavailable, cached-token or mismatched-model costs remain null/unknown. `OPENAI_MAX_OUTPUT_TOKENS` must be at most 2000 for this endpoint. No Gemini or Mock fallback is permitted. Deployment secrets and endpoint connectivity were **not** inspected or tested live.

## Workflow and API

Authenticated user selects an owned product, public source, keywords, location and bounded result count. Job APIs require a company slug and support local keyword/location filtering of a bounded first response. Unsupported job industry/country fields are rejected rather than silently ignored. Brave and Places receive industry/geographic query terms; these are search constraints, not verified location facts.

- `GET /api/v1/discovery/sources`: configuration availability, never keys.
- `POST /api/v1/discovery/searches`: `SearchInput` plus required `Idempotency-Key`.
- `GET /api/v1/discovery/searches[?limit=20&offset=0]`: owned history.
- `GET /api/v1/discovery/searches/{id}`: owned stored result.
- `POST /api/v1/discovery/prospects`: select source IDs from an owned completed search.
- `GET /api/v1/discovery/prospects[?limit=20&offset=0]`: owned saved prospects.
- `POST /api/v1/discovery/prospects/{id}/qualify`: separate, explicit paid action; required request key. One saved prospect only, never a batch.

All writes retain existing session authentication and Origin validation. Foreign IDs return 404. Contracts are exported to `contracts/openapi.json` and `frontend/lib/generated/api.d.ts` together.

## Budgets, caching and failure recovery

Default 10 results, maximum 20. One fixed-host source HTTP request per search, 12-second timeout, maximum 2 MB response, no redirects/pagination/network retry. Greenhouse normalization scans at most 500 returned jobs; Lever requests its first 20. Provider errors persist a failed search with safe error code; HTTP success of the local endpoint does not imply search success. Clients must inspect `status`.

Each user can initiate at most 5 searches/hour, with 60 seconds between different searches; each source has a global 100/hour budget and 2-second spacing. PostgreSQL row locks reserve budgets and user keys before external I/O. These concurrency guarantees require PostgreSQL; SQLite fixtures cover sequential unit behavior only. Identical completed searches cache for 15 minutes within the same owner and exact product snapshot. Places stores only IDs and does not use this content cache. Source URL normalization removes tracking parameters; saved prospects deduplicate per owner/product/source/source ID.

AI evaluation allows 3 explicit operations/user/hour, 60-second spacing and a global 10/hour budget. At most 1 qualification plus the existing single repair attempt per operation. Only one title (240 chars) and excerpt (800 chars), no context or crawled pages, with a 20,000-character total input ceiling. The historical four-field product snapshot is used, never a different current business. Existing strict grounding and scoring run unchanged, but **message score/decision is not presented as business buying intent**. Grounded fit/confidence can yield `relevant_company` or `possible_need`; `explicit_buying_intent` is reserved and never inferred automatically from job listings or directory matches. Full Agent output is retained privately for audit. Actual per-attempt usage is stored separately on the prospect and displayed with unknown costs intact, including failures. A screened-out operation can finish without a provider attempt and remains `not_evaluated`.

Pending and failed operations with the same key return stored state without retrying external requests. Different keys cannot re-evaluate an already requested prospect. Browser session storage retains uncertain request keys; checks require explicit clicks. Lost keys/pending operations require operator investigation, not automatic paid reruns. There is no scheduled search or automatic outreach.

## Security and verification

API endpoints are fixed trusted hosts; result URLs are **never fetched**. HTTPS links reject credentials, IP literals and obvious private hostnames. This prevents server-side arbitrary URL fetching; it does not claim DNS-based verification of every linked website. Excerpts are plain normalized text rendered with React escaping. No login scraping, contact enrichment or arbitrary proxy is provided. Provider bodies/errors and keys are not logged. Brave/Places credential echoes in responses are rejected.

Offline coverage includes adapters, ownership, origin protection, idempotency, cache/quota handling, grounded real-provider fake HTTP, bounded repair, usage retention, migration reversibility and PostgreSQL concurrent request replay. Frontend tests mock network responses; no external provider/search calls are executed. Live source connectivity and live model quality still require separately authorized testing and valid operator credentials.

Official integration references: [Brave web API](https://api-dashboard.search.brave.com/api-reference/web/search/get), [Brave API plans/storage](https://brave.com/search/api/), [Greenhouse Job Board](https://docs.greenhouse.io/job-board.html), [Lever postings](https://github.com/lever/postings-api), [Places Text Search](https://developers.google.com/maps/documentation/places/web-service/text-search), [Places policies](https://developers.google.com/maps/documentation/places/web-service/policies).
