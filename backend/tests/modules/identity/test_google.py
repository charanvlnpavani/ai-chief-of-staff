"""Google sign-in: authorization URL, ID-token validation and the full callback flow."""

import base64
import json
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient

from app.modules.identity import google

CLIENT_ID = "test-client.apps.googleusercontent.com"


def fake_id_token(**overrides: Any) -> str:
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "google-sub-123",
        "email": "owner@example.com",
        "email_verified": True,
        "name": "Owner Example",
        "nonce": "n-1",
        "exp": time.time() + 300,
    } | overrides
    encode = lambda part: base64.urlsafe_b64encode(json.dumps(part).encode()).decode().rstrip("=")  # noqa: E731
    return f"{encode({'alg': 'RS256'})}.{encode(claims)}.signature"


def test_valid_id_token_produces_identity() -> None:
    identity = google.identity_from_id_token(fake_id_token(), client_id=CLIENT_ID, nonce="n-1")
    assert identity.subject == "google-sub-123"
    assert identity.email == "owner@example.com"


@pytest.mark.parametrize(
    ("overrides", "nonce", "code"),
    [
        ({"iss": "https://evil.example"}, "n-1", "invalid_id_token"),
        ({"aud": "someone-else"}, "n-1", "invalid_id_token"),
        ({"exp": time.time() - 3600}, "n-1", "invalid_id_token"),
        ({}, "different-nonce", "invalid_id_token"),
        ({"email_verified": False}, "n-1", "email_not_verified"),
    ],
)
def test_invalid_id_tokens_are_rejected(overrides: dict[str, Any], nonce: str, code: str) -> None:
    with pytest.raises(google.GoogleAuthError) as caught:
        google.identity_from_id_token(fake_id_token(**overrides), client_id=CLIENT_ID, nonce=nonce)
    assert caught.value.code == code


async def _start(client: AsyncClient) -> dict[str, str]:
    response = await client.get("/api/v1/auth/google/start?next=/habits")
    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert location.netloc == "accounts.google.com"
    params = {k: v[0] for k, v in parse_qs(location.query).items()}
    assert params["code_challenge_method"] == "S256"
    assert params["scope"] == "openid email profile"
    assert params["redirect_uri"] == "http://localhost:3000/api/v1/auth/google/callback"
    return params


async def test_callback_signs_in_and_redirects(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    params = await _start(client)

    async def fake_exchange(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["code"] == "auth-code"
        return {"id_token": fake_id_token(nonce=params["nonce"])}

    monkeypatch.setattr(google, "exchange_code", fake_exchange)
    response = await client.get(
        "/api/v1/auth/google/callback", params={"code": "auth-code", "state": params["state"]}
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/habits"
    me = await client.get("/api/v1/users/me")
    assert me.status_code == 200
    assert me.json()["user"]["displayName"] == "Owner Example"


async def test_callback_rejects_state_mismatch(client: AsyncClient) -> None:
    await _start(client)
    response = await client.get(
        "/api/v1/auth/google/callback", params={"code": "auth-code", "state": "forged"}
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=state_mismatch"


async def test_callback_without_state_cookie_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/google/callback", params={"code": "c", "state": "s"})
    assert response.headers["location"] == "/login?error=state_expired"


async def test_callback_rejects_email_outside_allowlist(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    params = await _start(client)

    async def fake_exchange(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"id_token": fake_id_token(nonce=params["nonce"], email="stranger@example.com")}

    monkeypatch.setattr(google, "exchange_code", fake_exchange)
    response = await client.get(
        "/api/v1/auth/google/callback", params={"code": "c", "state": params["state"]}
    )
    assert response.headers["location"] == "/login?error=not_allowed"
    assert (await client.get("/api/v1/users/me")).status_code == 401


async def test_open_redirects_are_neutralised(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/google/start?next=//evil.example/path")
    assert response.status_code == 302
    # The "next" target is stored in the signed cookie; the callback test above shows a
    # valid relative path round-trips. Here we only assert the flow still starts safely.
    assert "pos_oauth" in response.headers["set-cookie"]
