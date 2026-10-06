# Deployment handoff — Roham

The local compose.yaml is the starting point. Online hosting is not configured
or performed. Choose the container host and database together before adding
provider-specific deployment files.

Backend auth and ownership routes now exist locally. Before the online release,
connect the auth UI/API client, verify credentialed browser requests, run migration
0002 on PostgreSQL, and check two-user isolation there. Also require migrations
before API/worker startup; one worker; persistent PostgreSQL; HTTPS and secure
session settings; origin/CORS configuration; server-only secrets; explicit
provider mode; health/readiness checks; known model rates and bounded paid usage;
and restart smoke tests. Build the frontend with the reachable API URL, not localhost.

Confirm the URL lifetime and competition requirements from the actual rules.
The revised plan targets first online Mock slice at end of Day 2. This file is a
handoff plan, not a deployable host configuration or a deployed URL.
