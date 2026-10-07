# Shared authentication - Roham

The original AuthService interface now has a database-backed implementation in
`service.py` and shared session dependencies in `dependencies.py`. Login and
registration use HttpOnly cookies; tokens are stored hashed, expire after 24 hours
and are revoked on logout. The existing Telegram AuthService bridge remains
compatible, and product access always verifies database ownership.

See [Business Setup](../../../docs/business-setup.md) for endpoints, cookie/CORS
settings, migration ordering, historical ownership backfill and team handoff.
Roham should reconcile this implementation with any separate auth branch before
merging. Hosting must apply login/register rate limiting and HTTPS cookie settings.

Credentials and SessionGrant preserve the original protocol shape; passwords are
excluded from repr and tokens from automatic JSON serialization. Never log raw
credentials or substitute a simulated authenticated user.
