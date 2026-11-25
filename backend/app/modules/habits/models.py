import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, OwnedMixin, SoftDeleteMixin, TimestampMixin, VersionMixin
from app.core.time import utc_now


class Habit(IdMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, OwnedMixin, Base):
    __tablename__ = "habits"

    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(40), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    measure: Mapped[str] = mapped_column(String(10), default="check")
    target_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal(1))
    unit: Mapped[str | None] = mapped_column(String(20), default=None)
    icon: Mapped[str | None] = mapped_column(String(40), default=None)
    color: Mapped[str | None] = mapped_column(String(20), default=None)
    sort_order: Mapped[int] = mapped_column(default=0)
    archived_at: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        CheckConstraint("measure IN ('check', 'count', 'duration')", name="measure_valid"),
        CheckConstraint("target_value > 0", name="target_positive"),
        Index(
            "ix_habits_user_active",
            "user_id",
            postgresql_where=text("deleted_at IS NULL AND archived_at IS NULL"),
        ),
    )


class HabitScheduleVersion(IdMixin, OwnedMixin, Base):
    """Schedules are versioned: a change closes the current version and opens a new one."""

    __tablename__ = "habit_schedule_versions"

    habit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("habits.id", ondelete="CASCADE"))
    valid_from: Mapped[date]
    valid_to: Mapped[date | None] = mapped_column(default=None)  # exclusive
    frequency: Mapped[str] = mapped_column(String(16))
    days_of_week: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger), default=None)
    times_per_period: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    __table_args__ = (
        CheckConstraint(
            "frequency IN ('daily', 'days_of_week', 'n_per_week', 'n_per_month')",
            name="frequency_valid",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="range_valid"),
        ExcludeConstraint(
            (literal_column("habit_id"), "="),
            (func.daterange(literal_column("valid_from"), literal_column("valid_to")), "&&"),
            name="ex_habit_schedule_versions_no_overlap",
            using="gist",
        ),
        Index("ix_habit_schedule_versions_habit", "habit_id", "valid_from"),
    )


class HabitCompletion(IdMixin, OwnedMixin, Base):
    """One row per habit per local day. Undo sets deleted_at (a tombstone for future sync)."""

    __tablename__ = "habit_completions"

    habit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("habits.id", ondelete="CASCADE"))
    local_date: Mapped[date]
    value: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal(1))
    recorded_at: Mapped[datetime] = mapped_column(default=utc_now)
    tz: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16), default="web")
    client_mutation_id: Mapped[uuid.UUID | None] = mapped_column(unique=True, default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        UniqueConstraint("habit_id", "local_date"),
        CheckConstraint("value >= 0", name="value_non_negative"),
        Index("ix_habit_completions_user_date", "user_id", "local_date"),
    )


class HabitException(IdMixin, TimestampMixin, OwnedMixin, Base):
    """A break (vacation, illness, rest). habit_id NULL means it applies to every habit."""

    __tablename__ = "habit_exceptions"

    habit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("habits.id", ondelete="CASCADE"), default=None
    )
    start_date: Mapped[date]
    end_date: Mapped[date]
    kind: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(300), default=None)

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="range_valid"),
        CheckConstraint(
            "kind IN ('vacation', 'sick', 'rest', 'travel', 'other')", name="kind_valid"
        ),
        Index("ix_habit_exceptions_user_range", "user_id", "start_date", "end_date"),
    )
