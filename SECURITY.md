# Security

Personal OS stores private data (and later finance and health records), so security is part of
every milestone, not an afterthought.

## Reporting a problem

Please do not open a public issue for a vulnerability. Contact the repository owner privately
through GitHub, with steps to reproduce.

## What is in place (Release 1)

- **Sessions:** opaque random tokens, stored only as SHA-256 hashes; HttpOnly, SameSite=Lax
  cookies (`__Host-` prefix and Secure in production); idle and absolute expiry; per-device revoke.
- **CSRF:** state-changing requests that carry the session cookie must come from the app's own
  origin (`Sec-Fetch-Site` / `Origin` checks).
- **Sign-in:** Google OpenID Connect with PKCE, state and nonce, and an email allowlist. The local
  development sign-in is disabled in production by configuration validation.
- **Authorization:** every query is scoped to the signed-in user; API tests include a second user
  for every resource. Other users' objects return 404.
- **Encryption:** AI conversations are encrypted with AES-256-GCM (versioned keys, row-bound
  associated data). Rotate keys by putting a new key first in `ENCRYPTION_KEYS`.
- **Audit:** security-relevant actions are written to `audit_logs`, which a database trigger
  makes append-only.
- **AI safety:** typed, read-only tools validated server-side; unknown or disallowed tools are
  refused and audited; consent required; monthly budget enforced. See
  `docs/architecture/overview.md`.
- **Headers:** nosniff, frame denial, referrer policy, permissions policy, COOP, HSTS in production.
- **Logs:** structured, with automatic redaction of token/cookie/secret-like fields; request
  bodies and query strings are never logged.
- **Supply chain:** lockfiles, pnpm minimum-release-age policy, GitHub Actions pinned to commit
  SHAs, Dependabot, gitleaks in pre-commit and CI.

## Rules for contributors

- Never commit `.env` files, keys, tokens or real personal data (fixtures must be synthetic).
- New endpoints need an ownership test with a second user.
- New AI tools must be read or suggest level; write tools may only propose; the user confirms before anything is saved (see docs/vision.md, section 9).

## Known gaps (tracked in docs/roadmap.md)

- Content-Security-Policy with nonces (M9).
- Row-level security in Postgres, formal threat-model review and penetration-style testing (M9).
- Rate limiting is in-memory (single instance); moves to Redis with the background worker (M6).
