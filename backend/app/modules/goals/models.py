import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, OwnedMixin, SoftDeleteMixin, TimestampMixin, VersionMixin
from app.core.time import utc_now


class Goal(IdMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, OwnedMixin, Base):
    """A long-term goal. Progress comes from milestones or from numeric check-ins."""

    __tablename__ = "goals"

    title: Mapped[str] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(40), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    importance: Mapped[str] = mapped_column(String(10), default="medium")
    success_metric: Mapped[str | None] = mapped_column(String(200), default=None)
    status: Mapped[str] = mapped_column(String(10), default="active")
    start_date: Mapped[date]
    target_date: Mapped[date | None] = mapped_column(default=None)
    progress_rule: Mapped[str] = mapped_column(String(12), default="milestones")
    start_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal(0))
    target_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    unit: Mapped[str | None] = mapped_column(String(20), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        CheckConstraint("importance IN ('low', 'medium', 'high')", name="importance_valid"),
        CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'archived')", name="status_valid"
        ),
        CheckConstraint("progress_rule IN ('milestones', 'numeric')", name="progress_rule_valid"),
        CheckConstraint(
            "progress_rule <> 'numeric' OR "
            "(target_value IS NOT NULL AND target_value <> start_value)",
            name="numeric_target_valid",
        ),
        CheckConstraint(
            "target_date IS NULL OR target_date >= start_date", name="target_date_valid"
        ),
        Index("ix_goals_user_active", "user_id", postgresql_where=text("deleted_at IS NULL")),
    )


class GoalMilestone(IdMixin, TimestampMixin, OwnedMixin, Base):
    __tablename__ = "goal_milestones"

    goal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(default=None)
    sort_order: Mapped[int] = mapped_column(default=0)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (Index("ix_goal_milestones_goal", "goal_id", "sort_order"),)


class GoalEntry(IdMixin, OwnedMixin, Base):
    """Append-only progress history: check-ins, notes and target changes.

    Rows are never updated or deleted by the app, so editing a goal's target keeps every
    earlier value. `target_value` is a snapshot of the target when the entry was written.
    """

    __tablename__ = "goal_entries"

    goal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    local_date: Mapped[date]
    value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    target_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    note: Mapped[str | None] = mapped_column(String(1000), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('check_in', 'target_change', 'status_change')", name="kind_valid"
        ),
        Index("ix_goal_entries_goal_date", "goal_id", "local_date", "created_at"),
    )
