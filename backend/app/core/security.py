"""Tokens, hashing, PKCE and signed short-lived payloads."""

import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
import time
from typing import Any


def new_token(nbytes: int = 32) -> str:
    """A URL-safe random token with `nbytes` of entropy (256 bits by default)."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> bytes:
    """Session tokens are high-entropy, so a fast hash is appropriate (not a password hash)."""
    return hashlib.sha256(token.encode()).digest()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def pkce_pair() -> tuple[str, str]:
    """Returns (code_verifier, S256 code_challenge) per RFC 7636."""
    verifier = secrets.token_urlsafe(48)
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def sign_payload(payload: dict[str, Any], secret: str, ttl_seconds: int) -> str:
    if not secret:
        raise RuntimeError("SECRET_KEY is not configured")
    body = dict(payload, exp=int(time.time()) + ttl_seconds)
    encoded = _b64url(json.dumps(body, separators=(",", ":")).encode())
    signature = _b64url(hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def verify_payload(token: str, secret: str) -> dict[str, Any]:
    """Raises ValueError if the token is malformed, tampered with or expired."""
    if not secret:
        raise RuntimeError("SECRET_KEY is not configured")
    try:
        encoded, signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("malformed token") from exc
    expected = _b64url(hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, signature):
        raise ValueError("bad signature")
    try:
        body: dict[str, Any] = json.loads(_b64url_decode(encoded))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("malformed payload") from exc
    if int(body.get("exp", 0)) < int(time.time()):
        raise ValueError("expired")
    return body


def ip_prefix(ip: str | None) -> str | None:
    """Truncate an IP for privacy: IPv4 to /24, IPv6 to /48."""
    if not ip:
        return None
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return None
    prefix = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{address}/{prefix}", strict=False))
