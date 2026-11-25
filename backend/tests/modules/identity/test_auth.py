"""Sign-in, sessions, CSRF protection, profile, preferences and consents."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import AuditLog, AuthSession
from tests.conftest import make_client, sign_in


async def test_unauthenticated_requests_are_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


async def test_dev_login_sets_httponly_cookie_and_returns_user(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/dev/login", json={"email": "Owner@Example.com"})
    assert response.status_code == 200
    assert response.json()["email"] == "owner@example.com"
    set_cookie = response.headers["set-cookie"].lower()
    assert "pos_session=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie


async def test_session_token_is_stored_hashed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await sign_in(client, "owner@example.com")
    token = client.cookies.get("pos_session")
    assert token
    stored = await db_session.scalar(select(AuthSession.token_hash))
    assert stored is not None
    assert token.encode() not in stored


async def test_email_outside_allowlist_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/dev/login", json={"email": "stranger@example.com"})
    assert response.status_code == 403
    assert response.json()["code"] == "not_allowed"


async def test_me_returns_profile_and_default_preferences(owner: AsyncClient) -> None:
    response = await owner.get("/api/v1/users/me")
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "owner@example.com"
    assert body["user"]["timezone"] == "Asia/Kolkata"
    assert body["user"]["currency"] == "INR"
    assert body["preferences"]["dailyLearningGoalMinutes"] == 120


async def test_logout_revokes_session(owner: AsyncClient) -> None:
    token = owner.cookies.get("pos_session")
    response = await owner.post("/api/v1/auth/logout")
    assert response.status_code == 204
    # Even if the cookie were replayed, the server-side session is gone.
    owner.cookies.set("pos_session", token or "")
    replay = await owner.get("/api/v1/users/me")
    assert replay.status_code == 401


async def test_user_can_list_and_revoke_other_sessions(app: FastAPI, owner: AsyncClient) -> None:
    async with make_client(app) as second_device:
        await sign_in(second_device, "owner@example.com")
        sessions = (await owner.get("/api/v1/auth/sessions")).json()
        assert len(sessions) == 2
        assert sum(1 for s in sessions if s["current"]) == 1
        other = next(s for s in sessions if not s["current"])
        assert (await owner.delete(f"/api/v1/auth/sessions/{other['id']}")).status_code == 204
        assert (await second_device.get("/api/v1/users/me")).status_code == 401


async def test_user_cannot_revoke_another_users_session(
    owner: AsyncClient, intruder: AsyncClient
) -> None:
    owner_session = (await owner.get("/api/v1/auth/sessions")).json()[0]
    response = await intruder.delete(f"/api/v1/auth/sessions/{owner_session['id']}")
    assert response.status_code == 404
    assert (await owner.get("/api/v1/users/me")).status_code == 200


async def test_cross_site_write_with_cookie_is_blocked(owner: AsyncClient) -> None:
    response = await owner.patch(
        "/api/v1/users/me",
        json={"displayName": "Hijacked"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_rejected"


async def test_sec_fetch_site_cross_site_is_blocked(owner: AsyncClient) -> None:
    response = await owner.patch(
        "/api/v1/users/me",
        json={"displayName": "Hijacked"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 403


async def test_profile_update_validates_timezone(owner: AsyncClient) -> None:
    bad = await owner.patch("/api/v1/users/me", json={"timezone": "Mars/Olympus"})
    assert bad.status_code == 422
    good = await owner.patch(
        "/api/v1/users/me", json={"timezone": "Europe/Berlin", "displayName": "Charan"}
    )
    assert good.status_code == 200
    assert good.json()["timezone"] == "Europe/Berlin"
    assert good.json()["displayName"] == "Charan"


async def test_preferences_patch_merges_nested_values(owner: AsyncClient) -> None:
    response = await owner.patch(
        "/api/v1/users/me/settings", json={"theme": "dark", "ai": {"monthlyBudgetUsd": 10}}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["preferences"]["theme"] == "dark"
    assert body["preferences"]["ai"]["monthlyBudgetUsd"] == 10
    assert body["preferences"]["dailyLearningGoalMinutes"] == 120  # untouched
    assert body["version"] == 2


async def test_consents_default_to_not_set_and_can_be_granted(
    owner: AsyncClient, db_session: AsyncSession
) -> None:
    consents = (await owner.get("/api/v1/users/me/consents")).json()
    assert {c["status"] for c in consents} == {"not_set"}
    granted = await owner.put("/api/v1/users/me/consents/ai_processing", json={"granted": True})
    assert granted.status_code == 200
    assert granted.json()["status"] == "granted"
    revoked = await owner.put("/api/v1/users/me/consents/ai_processing", json={"granted": False})
    assert revoked.json()["status"] == "revoked"
    actions = list(await db_session.scalars(select(AuditLog.action).order_by(AuditLog.occurred_at)))
    assert "consent.grant" in actions
    assert "consent.revoke" in actions


async def test_unknown_consent_category_is_rejected(owner: AsyncClient) -> None:
    response = await owner.put("/api/v1/users/me/consents/everything", json={"granted": True})
    assert response.status_code == 422


async def test_audit_log_is_append_only(owner: AsyncClient, db_session: AsyncSession) -> None:
    entry = await db_session.scalar(select(AuditLog).limit(1))
    assert entry is not None
    nested = await db_session.begin_nested()
    with pytest.raises(DBAPIError, match="append-only"):
        await db_session.execute(
            text("UPDATE audit_logs SET action = 'tampered' WHERE id = :id"), {"id": entry.id}
        )
    await nested.rollback()
