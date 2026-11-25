import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, OwnedMixin, TimestampMixin, VersionMixin
from app.core.time import utc_now


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(CITEXT(), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64))
    locale: Mapped[str] = mapped_column(String(16), default="en-IN")
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20), default="active")
    deletion_requested_at: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'disabled', 'pending_deletion')", name="status_valid"
        ),
        CheckConstraint("char_length(currency) = 3", name="currency_len"),
    )


class AuthIdentity(IdMixin, TimestampMixin, OwnedMixin, Base):
    """A sign-in method linked to a user (e.g. a Google account `sub`)."""

    __tablename__ = "auth_identities"

    provider: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(255))
    email_at_link: Mapped[str | None] = mapped_column(CITEXT(), default=None)
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        UniqueConstraint("provider", "subject"),
        Index("ix_auth_identities_user_id", "user_id"),
    )


class AuthSession(IdMixin, OwnedMixin, Base):
    """An opaque session. Only the SHA-256 of the token is stored."""

    __tablename__ = "auth_sessions"

    client: Mapped[str] = mapped_column(String(10))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    refresh_hash: Mapped[bytes | None] = mapped_column(LargeBinary, unique=True, default=None)
    refresh_family: Mapped[uuid.UUID | None] = mapped_column(default=None)
    device_label: Mapped[str | None] = mapped_column(String(120), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(400), default=None)
    ip_prefix: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(default=utc_now)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    revoked_reason: Mapped[str | None] = mapped_column(String(40), default=None)
    step_up_at: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        CheckConstraint("client IN ('web', 'mobile')", name="client_valid"),
        Index(
            "ix_auth_sessions_user_active",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_auth_sessions_refresh_family", "refresh_family"),
    )


class UserSettings(VersionMixin, Base):
    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class Consent(IdMixin, TimestampMixin, OwnedMixin, Base):
    """Current consent state per category. Every change is also written to audit_logs."""

    __tablename__ = "consents"

    category: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(10))
    policy_version: Mapped[str] = mapped_column(String(20))
    granted_at: Mapped[datetime | None] = mapped_column(default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        UniqueConstraint("user_id", "category"),
        CheckConstraint("status IN ('granted', 'revoked')", name="status_valid"),
    )


class AuditLog(IdMixin, Base):
    """Append-only record of security-relevant actions. Holds ids and counts, never content."""

    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), default=None
    )
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[str | None] = mapped_column(String(64), default=None)
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str | None] = mapped_column(String(40), default=None)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    request_id: Mapped[str | None] = mapped_column(String(64), default=None)
    ip_prefix: Mapped[str | None] = mapped_column(String(64), default=None)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(default=utc_now)

    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('user', 'ai', 'system', 'integration')", name="actor_type_valid"
        ),
        Index("ix_audit_logs_user_occurred", "user_id", text("occurred_at DESC")),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
    )
