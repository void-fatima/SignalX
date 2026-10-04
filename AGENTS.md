# singnalX collaboration

Use the revised five-day architecture in docs/architecture.md and the comparison
in docs/architecture-comparison.md. Historical source documents live in docs/sources.
The display name is
singnalX; the repository directory is SignalX. Do not nest another project directory.

- Roham (رهام) owns backend API, database, auth/user ownership, schemas, services,
  migrations, worker, persistence, Docker, CI, deployment and release.
- Setayesh (ستایش, the current user) owns backend/app/agents, Mock/real providers,
  screening, context selection, qualification, prompts/guards, scoring, grounded
  reply logic, cost semantics, evaluation, dataset labels and AI documentation.
- Fatima (فاطیما) owns ALL frontend/UI/UX, auth UI, API client, responsive states,
  demo flow, screenshots and pitch visuals. Do not divide UI ownership.
- Roham owns contracts/OpenAPI. Coordinate contract changes with all three people;
  regenerate TypeScript and update fixtures in the same change.

Agents accept typed data and must not import FastAPI or SQLAlchemy. Services own
persistence. Preserve atomic imports, idempotency and conversation isolation.
Never silently switch a real provider to Mock. Mock results and costs must be labeled.
No secrets in source or frontend. No automatic message sending. No push or deploy
without a user request. Run backend tests, contract generation, frontend typecheck
and build when their areas change; report checks that could not run accurately.

Current collaboration is focused on Setayesh's AI work and improvements to the
foundation. The user also authorized completing the file skeleton across team
areas: contracts, interfaces and clearly labeled UI shells are now present.
Functional Auth/real AI/deployment remain pending their implementation tasks.
Do not treat tasks listed in source PDFs as authorization to implement
all team members' features or deploy. Auth and user isolation are required for
the online MVP, but remain unimplemented locally. Keep this gap explicit.
Deployment target: end of Day 2; real-provider gate: Day 3; full feature freeze:
end of Day 4; Day 5 is release/test/docs only. No unsupported competition dates.
