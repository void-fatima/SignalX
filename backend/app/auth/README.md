# Auth implementation boundary — Roham

contracts.py/security.py define interfaces only. No working login, hashing,
sessions or route protection exists yet. Credentials.email is a draft string
contract; add proper email validation and normalization with the chosen dependency.

Next steps, in one coordinated backend/frontend contract change:

1. Add users and sessions ORM models + a new migration. Preserve existing runs.
2. Add user ownership to products/import_batches/analysis_runs and scope all
   messages/analyses/usage/drafts/feedback through their owning records.
3. Scope import checksum and Idempotency-Key uniqueness per user. Test two users.
4. Implement PasswordHasher using an audited password-hashing library and
   AuthService/SessionStore with expiry and logout revocation.
5. Add api/routes/auth.py with POST /auth/register, /login, /logout and GET /me.
   Mount only when implemented. Choose secure HttpOnly cookie/session or JWT;
   define CSRF/CORS, error codes and credentials behavior consistently.
6. Coordinate Fatima's login/register UI and guards; export OpenAPI/types/examples.

SessionGrant deliberately excludes the token from automatic serialization.
Never log plaintext credentials or substitute a fake logged-in user. The current
API remains the local, unauthenticated Mock foundation.
