"""Google sign-in (OpenID Connect, authorization-code flow with PKCE).

The ID token arrives directly from Google's token endpoint over TLS in exchange for a
one-time code, so per OpenID Connect Core section 3.1.3.7 TLS server validation stands in
for signature validation. We still check issuer, audience, expiry, nonce and that the
email is verified.
"""

import base64
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
# S105 false positive: this is a public URL, not a credential.
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105
VALID_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
SCOPES = "openid email profile"


class GoogleAuthError(Exception):
    """Raised for any failure in the Google flow; `code` is safe to show in the UI."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    subject: str
    email: str
    name: str | None


def redirect_uri(settings: Settings) -> str:
    return f"{settings.web_origin.rstrip('/')}/api/v1/auth/google/callback"


def authorization_url(settings: Settings, *, state: str, nonce: str, code_challenge: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri(settings),
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
        "access_type": "online",
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


async def exchange_code(
    settings: Settings, *, code: str, code_verifier: str, client: httpx.AsyncClient
) -> dict[str, Any]:
    try:
        response = await client.post(
            TOKEN_ENDPOINT,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret.get_secret_value(),
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri(settings),
            },
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise GoogleAuthError("google_unreachable", "Could not reach Google.") from exc
    if response.status_code != 200:
        raise GoogleAuthError("google_token_rejected", "Google rejected the sign-in code.")
    data: dict[str, Any] = response.json()
    return data


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    try:
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        claims: dict[str, Any] = json.loads(base64.urlsafe_b64decode(padded))
    except (IndexError, ValueError, json.JSONDecodeError) as exc:
        raise GoogleAuthError(
            "invalid_id_token", "Google returned an unreadable ID token."
        ) from exc
    return claims


def identity_from_id_token(
    id_token: str, *, client_id: str, nonce: str, now: float | None = None
) -> GoogleIdentity:
    claims = _decode_jwt_payload(id_token)
    current = time.time() if now is None else now
    if claims.get("iss") not in VALID_ISSUERS:
        raise GoogleAuthError("invalid_id_token", "Unexpected token issuer.")
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if client_id not in audiences:
        raise GoogleAuthError("invalid_id_token", "Token was issued for another app.")
    if float(claims.get("exp", 0)) < current - 60:
        raise GoogleAuthError("invalid_id_token", "Token has expired.")
    if claims.get("nonce") != nonce:
        raise GoogleAuthError("invalid_id_token", "Token nonce does not match.")
    if claims.get("email_verified") is not True or not claims.get("email"):
        raise GoogleAuthError("email_not_verified", "Your Google email address is not verified.")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise GoogleAuthError("invalid_id_token", "Token has no subject.")
    name = claims.get("name")
    return GoogleIdentity(
        subject=subject,
        email=str(claims["email"]).lower(),
        name=name if isinstance(name, str) else None,
    )
