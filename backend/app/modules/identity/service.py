"""Identity service: users, sessions, preferences and consents."""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFound
from app.core.ratelimit import client_ip
from app.core.security import hash_token, ip_prefix, new_token
from app.core.time import utc_now
from app.modules.identity.audit import record_audit
from app.modules.identity.models import AuthIdentity, AuthSession, Consent, User, UserSettings
from app.modules.identity.schemas import (
    CONSENT_POLICY_VERSION,
    ConsentCategory,
    ConsentOut,
    Preferences,
    PreferencesUpdate,
    UserUpdate,
)

TOUCH_INTERVAL = timedelta(minutes=5)
ALL_CONSENT_CATEGORIES: tuple[ConsentCategory, ...] = (
    "ai_processing",
    "ai_health",
    "ai_finance",
    "ai_email_content",
)


@dataclass(slots=True)
class AuthContext:
    user: User
    session: AuthSession


# ------------------------------------------------------------------ users


def is_email_allowed(email: str, settings: Settings) -> bool:
    return email.lower() in settings.allowed_login_emails


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFound("User not found.")
    return user


async def _provision_user(
    session: AsyncSession, *, email: str, display_name: str, settings: Settings
) -> User:
    user = User(
        email=email.lower(),
        display_name=display_name[:120] or email.split("@")[0],
        timezone=settings.default_timezone,
        currency=settings.default_currency,
    )
    session.add(user)
    await session.flush()
    session.add(UserSettings(user_id=user.id, preferences=Preferences().model_dump(by_alias=False)))
    return user


async def login_with_identity(
    session: AsyncSession,
    *,
    provider: str,
    subject: str,
    email: str,
    display_name: str | None,
    settings: Settings,
) -> User:
    """Find the user for an external identity, linking or creating as needed."""
    identity = await session.scalar(
        select(AuthIdentity).where(
            AuthIdentity.provider == provider, AuthIdentity.subject == subject
        )
    )
    now = utc_now()
    if identity is not None:
        identity.last_login_at = now
        return await get_user(session, identity.user_id)

    user = await session.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        user = await _provision_user(
            session, email=email, display_name=display_name or "", settings=settings
        )
    session.add(
        AuthIdentity(
            user_id=user.id,
            provider=provider,
            subject=subject,
            email_at_link=email.lower(),
            last_login_at=now,
        )
    )
    return user


async def update_profile(session: AsyncSession, user: User, update: UserUpdate) -> User:
    changes = update.model_dump(exclude_unset=True, by_alias=False)
    for field, value in changes.items():
        if value is not None:
            setattr(user, field, value)
    record_audit(
        session,
        user_id=user.id,
        action="user.profile.update",
        entity_type="user",
        entity_id=user.id,
        details={"fields": sorted(changes)},
    )
    await session.commit()
    return user


# ------------------------------------------------------------------ sessions


async def create_session(
    session: AsyncSession,
    *,
    user: User,
    client: str,
    request: Request,
    settings: Settings,
) -> tuple[str, AuthSession]:
    token = new_token()
    now = utc_now()
    user_agent = request.headers.get("user-agent")
    auth_session = AuthSession(
        user_id=user.id,
        client=client,
        token_hash=hash_token(token),
        user_agent=user_agent[:400] if user_agent else None,
        ip_prefix=ip_prefix(client_ip(request)),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=settings.session_absolute_days),
        step_up_at=now,
    )
    session.add(auth_session)
    record_audit(
        session,
        user_id=user.id,
        action="auth.session.create",
        entity_type="auth_session",
        entity_id=auth_session.id,
        details={"client": client},
        request=request,
    )
    await session.commit()
    return token, auth_session


async def resolve_session(
    session: AsyncSession, token: str, settings: Settings
) -> AuthContext | None:
    row = await session.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.token_hash == hash_token(token), AuthSession.revoked_at.is_(None))
    )
    found = row.first()
    if found is None:
        return None
    auth_session, user = found
    now = utc_now()
    idle_limit = now - timedelta(days=settings.session_idle_days)
    if auth_session.expires_at <= now or auth_session.last_seen_at <= idle_limit:
        return None
    if user.status != "active":
        return None
    if now - auth_session.last_seen_at > TOUCH_INTERVAL:
        auth_session.last_seen_at = now
        await session.commit()
    return AuthContext(user=user, session=auth_session)


async def list_sessions(session: AsyncSession, user_id: uuid.UUID) -> list[AuthSession]:
    now = utc_now()
    result = await session.scalars(
        select(AuthSession)
        .where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
        .order_by(AuthSession.last_seen_at.desc())
    )
    return list(result)


async def revoke_session(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    reason: str,
    request: Request | None = None,
) -> None:
    auth_session = await session.scalar(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
    )
    if auth_session is None:
        raise NotFound("Session not found.")
    auth_session.revoked_at = utc_now()
    auth_session.revoked_reason = reason
    record_audit(
        session,
        user_id=user_id,
        action="auth.session.revoke",
        entity_type="auth_session",
        entity_id=session_id,
        details={"reason": reason},
        request=request,
    )
    await session.commit()


# ------------------------------------------------------------------ preferences


async def _settings_row(session: AsyncSession, user_id: uuid.UUID) -> UserSettings:
    row = await session.get(UserSettings, user_id)
    if row is None:
        row = UserSettings(user_id=user_id, preferences=Preferences().model_dump(by_alias=False))
        session.add(row)
        await session.flush()
    return row


async def get_preferences(session: AsyncSession, user_id: uuid.UUID) -> tuple[Preferences, int]:
    row = await _settings_row(session, user_id)
    return Preferences.model_validate(row.preferences), row.version


def _merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        elif value is not None:
            merged[key] = value
    return merged


async def update_preferences(
    session: AsyncSession, user_id: uuid.UUID, update: PreferencesUpdate
) -> tuple[Preferences, int]:
    row = await _settings_row(session, user_id)
    patch = update.model_dump(exclude_unset=True, by_alias=False)
    merged = Preferences.model_validate(_merge(row.preferences, patch))
    row.preferences = merged.model_dump(by_alias=False)
    row.version += 1
    record_audit(
        session,
        user_id=user_id,
        action="user.settings.update",
        entity_type="user_settings",
        details={"fields": sorted(patch)},
    )
    await session.commit()
    return merged, row.version


# ------------------------------------------------------------------ consents


async def list_consents(session: AsyncSession, user_id: uuid.UUID) -> list[ConsentOut]:
    rows = {
        c.category: c
        for c in await session.scalars(select(Consent).where(Consent.user_id == user_id))
    }
    result: list[ConsentOut] = []
    for category in ALL_CONSENT_CATEGORIES:
        row = rows.get(category)
        if row is None:
            result.append(ConsentOut(category=category, status="not_set"))
        else:
            result.append(ConsentOut.model_validate(row))
    return result


async def has_consent(session: AsyncSession, user_id: uuid.UUID, category: ConsentCategory) -> bool:
    status = await session.scalar(
        select(Consent.status).where(Consent.user_id == user_id, Consent.category == category)
    )
    return status == "granted"


async def set_consent(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    category: ConsentCategory,
    granted: bool,
    request: Request | None = None,
) -> ConsentOut:
    row = await session.scalar(
        select(Consent).where(Consent.user_id == user_id, Consent.category == category)
    )
    now = utc_now()
    if row is None:
        row = Consent(user_id=user_id, category=category, status="revoked", policy_version="")
        session.add(row)
    row.status = "granted" if granted else "revoked"
    row.policy_version = CONSENT_POLICY_VERSION
    if granted:
        row.granted_at = now
    else:
        row.revoked_at = now
    record_audit(
        session,
        user_id=user_id,
        action="consent.grant" if granted else "consent.revoke",
        entity_type="consent",
        details={"category": category, "policy_version": CONSENT_POLICY_VERSION},
        request=request,
    )
    await session.commit()
    return ConsentOut.model_validate(row)


def audit_event(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    action: str,
    entity_type: str | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Public entry point for other modules to add an audit row in their own transaction."""
    record_audit(
        session,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        details=details,
        request=request,
    )
