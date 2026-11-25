import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, OwnedMixin, SoftDeleteMixin, TimestampMixin, VersionMixin

LEVELS = ("basic", "intermediate", "advanced", "pro")


class Roadmap(IdMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, OwnedMixin, Base):
    """A basic-to-pro learning plan for one subject, split into numbered days."""

    __tablename__ = "roadmaps"

    subject: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(10))
    template_key: Mapped[str | None] = mapped_column(String(40), default=None)
    status: Mapped[str] = mapped_column(String(10), default="active")
    start_date: Mapped[date]
    completed_at: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        CheckConstraint("source IN ('template', 'ai')", name="source_valid"),
        CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'archived')", name="status_valid"
        ),
        Index("ix_roadmaps_user_active", "user_id", postgresql_where=text("deleted_at IS NULL")),
    )


class RoadmapTask(IdMixin, OwnedMixin, Base):
    """One task on one planned day. `completed_on` is the user's local day it was ticked."""

    __tablename__ = "roadmap_tasks"

    roadmap_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roadmaps.id", ondelete="CASCADE"))
    day: Mapped[int] = mapped_column(SmallInteger)
    position: Mapped[int] = mapped_column(SmallInteger)
    level: Mapped[str] = mapped_column(String(12))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str | None] = mapped_column(Text, default=None)
    minutes: Mapped[int] = mapped_column(SmallInteger, default=30)
    completed_on: Mapped[date | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        CheckConstraint(
            "level IN ('basic', 'intermediate', 'advanced', 'pro')", name="level_valid"
        ),
        CheckConstraint("day >= 1", name="day_positive"),
        CheckConstraint("minutes BETWEEN 5 AND 480", name="minutes_range"),
        CheckConstraint(
            "(completed_on IS NULL) = (completed_at IS NULL)", name="completion_consistent"
        ),
        Index("ix_roadmap_tasks_roadmap_order", "roadmap_id", "day", "position"),
    )
