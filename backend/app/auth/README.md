# Backend authentication

The backend exposes `POST /api/v1/auth/register`, `POST /api/v1/auth/login`,
`POST /api/v1/auth/logout`, and `GET /api/v1/auth/me`.

- Emails are trimmed, case-folded, and unique.
- Passwords are stored as salted `scrypt` hashes; plaintext passwords are never
  persisted or logged.
- Login issues an opaque random session token in an HttpOnly cookie. The
  database stores only its SHA-256 digest. Logout revokes the server-side
  session. Expired or revoked session rows are pruned at login and hourly by the
  worker. Session lifetime defaults to seven days.
- `AUTH_COOKIE_SAMESITE=lax` is suitable for local development and same-site
  deployments. For a cross-site frontend/API deployment, set
  `AUTH_COOKIE_SAMESITE=none` and `AUTH_COOKIE_SECURE=true` behind HTTPS. The
  settings reject `none` without Secure. Keep `CORS_ORIGINS` limited to trusted
  frontend origins and enable credentialed requests in the frontend client.
- Mutating auth and product/import/run requests reject an unconfigured browser
  `Origin`. Requests without an `Origin` remain available for non-browser API
  clients.
- Product, import batch, and analysis run records created after migration are
  owned by the authenticated user. Message, analysis, and usage access is
  scoped through those owned records. Import checksum and run idempotency keys
  are unique per user.

Migration `0002` leaves pre-authentication rows unowned rather than inventing a
user for them; authenticated APIs do not expose those rows. The session cookie
is returned only by login and is excluded from the JSON response body.

The login/register UI and API client credential handling remain Fatima's
frontend work. The AgentInput/AgentOutput schema is unchanged by this auth work.
