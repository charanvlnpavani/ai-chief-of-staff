# ADR-0002: Opaque sessions and Google sign-in

- Status: accepted (2026-11-17)

## Decision

- Sign-in with Google (OpenID Connect, authorization code + PKCE, state and nonce), limited to
  emails in `ALLOWED_LOGIN_EMAILS`. Only `openid email profile` scopes, so no Google verification
  is needed.
- The backend issues its own **opaque session tokens** (256-bit random) and stores only their
  SHA-256 hash. Web uses an HttpOnly, SameSite=Lax cookie (`__Host-` prefix in production);
  mobile (Release 5) will use short-lived bearer tokens with rotating refresh tokens.
- The ID token is received directly from Google's token endpoint over TLS, so per OIDC Core
  3.1.3.7 we validate issuer, audience, expiry, nonce and `email_verified` instead of the
  signature.
- A local-development sign-in exists for running without Google; configuration validation
  refuses to start production with it enabled.

## Why not JWTs?

There is one backend, so stateless verification brings no benefit, while opaque tokens can be
revoked instantly (logout, "sign out other devices").

## Why not passwords?

No password storage, reset or verification flows to build; MFA comes from the Google account.
Email + password (Argon2id) + TOTP remains an option if a non-Google login is ever needed.
