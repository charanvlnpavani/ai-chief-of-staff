import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, OwnedMixin, SoftDeleteMixin, TimestampMixin
from app.core.time import utc_now


class AIConversation(IdMixin, TimestampMixin, SoftDeleteMixin, OwnedMixin, Base):
    __tablename__ = "ai_conversations"

    title: Mapped[str | None] = mapped_column(String(120), default=None)
    status: Mapped[str] = mapped_column(String(10), default="active")
    last_message_at: Mapped[datetime] = mapped_column(default=utc_now)
    retention_until: Mapped[datetime]

    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="status_valid"),
        Index(
            "ix_ai_conversations_user_recent",
            "user_id",
            text("last_message_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class AIMessage(IdMixin, OwnedMixin, Base):
    """One API turn, stored verbatim (encrypted) and append-only.

    Claude Opus 5.5 checks that replayed history is unedited, so content blocks (including
    thinking blocks) are kept exactly as returned.
    """

    __tablename__ = "ai_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE")
    )
    seq: Mapped[int]
    role: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(16), default="message")
    content_enc: Mapped[bytes] = mapped_column(LargeBinary)
    model: Mapped[str | None] = mapped_column(String(64), default=None)
    stop_reason: Mapped[str | None] = mapped_column(String(32), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    __table_args__ = (
        UniqueConstraint("conversation_id", "seq"),
        CheckConstraint("role IN ('user', 'assistant')", name="role_valid"),
        CheckConstraint("kind IN ('message', 'tool_results')", name="kind_valid"),
    )


class AIToolExecution(IdMixin, OwnedMixin, Base):
    """Audit row for every tool call the model asked for, allowed or not."""

    __tablename__ = "ai_tool_executions"

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), default=None
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_messages.id", ondelete="SET NULL"), default=None
    )
    tool_id: Mapped[str] = mapped_column(String(64))
    tool_version: Mapped[str] = mapped_column(String(16), default="1")
    permission_level: Mapped[int] = mapped_column(SmallInteger, default=1)
    decision: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(10))
    args_redacted: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    args_hash: Mapped[bytes] = mapped_column(LargeBinary)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    latency_ms: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None] = mapped_column(String(40), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    __table_args__ = (
        CheckConstraint(
            "decision IN ('allowed', 'denied', 'needs_consent', 'needs_approval', 'invalid')",
            name="decision_valid",
        ),
        CheckConstraint("status IN ('ok', 'error', 'timeout', 'denied')", name="status_valid"),
        Index("ix_ai_tool_executions_user_created", "user_id", text("created_at DESC")),
        Index("ix_ai_tool_executions_tool", "tool_id", "created_at"),
    )


class AIUsageLedger(IdMixin, OwnedMixin, Base):
    """Tokens and cost for every API call; the monthly budget is enforced from this table."""

    __tablename__ = "ai_usage_ledger"

    route: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(64))
    api_request_id: Mapped[str | None] = mapped_column(String(80), default=None)
    batch: Mapped[bool] = mapped_column(default=False)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cache_read_tokens: Mapped[int] = mapped_column(default=0)
    cache_write_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    __table_args__ = (
        CheckConstraint(
            "route IN ('chat', 'briefing', 'news', 'gmail', 'report', 'eval')", name="route_valid"
        ),
        Index("ix_ai_usage_ledger_user_created", "user_id", "created_at"),
    )
