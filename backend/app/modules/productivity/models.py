import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, OwnedMixin, SoftDeleteMixin, TimestampMixin, VersionMixin

TASK_DOMAINS = (
    "general",
    "growth",
    "professional",
    "finance",
    "health",
    "habits",
    "jobs",
    "social",
    "news",
)


class TaskList(IdMixin, TimestampMixin, OwnedMixin, Base):
    __tablename__ = "task_lists"

    name: Mapped[str] = mapped_column(String(80))
    color: Mapped[str | None] = mapped_column(String(20), default=None)
    sort_order: Mapped[int] = mapped_column(default=0)
    archived_at: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        Index(
            "uq_task_lists_user_name",
            "user_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )


class Task(IdMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, OwnedMixin, Base):
    __tablename__ = "tasks"

    list_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task_lists.id", ondelete="SET NULL"), default=None
    )
    title: Mapped[str] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(12), default="todo")
    priority: Mapped[int] = mapped_column(SmallInteger, default=3)
    due_on: Mapped[date | None] = mapped_column(default=None)
    due_at: Mapped[datetime | None] = mapped_column(default=None)
    domain: Mapped[str] = mapped_column(String(20), default="general")
    related_type: Mapped[str | None] = mapped_column(String(40), default=None)
    related_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    recurrence_rule: Mapped[str | None] = mapped_column(String(200), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    source: Mapped[str] = mapped_column(String(20), default="manual")

    __table_args__ = (
        CheckConstraint(
            "status IN ('todo', 'in_progress', 'done', 'cancelled')", name="status_valid"
        ),
        CheckConstraint("priority BETWEEN 1 AND 4", name="priority_range"),
        CheckConstraint(
            "domain IN (" + ", ".join(f"'{d}'" for d in TASK_DOMAINS) + ")", name="domain_valid"
        ),
        Index(
            "ix_tasks_user_status_due",
            "user_id",
            "status",
            "due_on",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_tasks_related", "related_type", "related_id"),
    )
