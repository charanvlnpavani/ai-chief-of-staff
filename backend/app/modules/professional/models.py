import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, OwnedMixin, SoftDeleteMixin, TimestampMixin

SKILL_CATEGORIES = (
    "dsa",
    "system_design",
    "frontend",
    "backend",
    "python",
    "databases",
    "ai",
    "cloud_devops",
    "security",
    "career",
    "other",
)
PLATFORMS = ("leetcode", "gfg", "codeforces", "hackerrank", "codechef", "other")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class Skill(IdMixin, TimestampMixin, SoftDeleteMixin, OwnedMixin, Base):
    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(30), default="other")
    level: Mapped[int] = mapped_column(SmallInteger, default=0)
    target_level: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        CheckConstraint("level BETWEEN 0 AND 5", name="level_range"),
        CheckConstraint(
            "target_level IS NULL OR target_level BETWEEN 0 AND 5", name="target_range"
        ),
        CheckConstraint(_in("category", SKILL_CATEGORIES), name="category_valid"),
        Index(
            "uq_skills_user_name",
            "user_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class LearningSession(IdMixin, TimestampMixin, SoftDeleteMixin, OwnedMixin, Base):
    __tablename__ = "learning_sessions"

    local_date: Mapped[date]
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    duration_min: Mapped[int]
    skill_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL"), default=None
    )
    topic: Mapped[str] = mapped_column(String(200))
    resource_url: Mapped[str | None] = mapped_column(String(500), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    focus: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    client_mutation_id: Mapped[uuid.UUID | None] = mapped_column(unique=True, default=None)

    __table_args__ = (
        CheckConstraint("duration_min BETWEEN 1 AND 1440", name="duration_range"),
        CheckConstraint("focus IS NULL OR focus BETWEEN 1 AND 5", name="focus_range"),
        Index(
            "ix_learning_sessions_user_date",
            "user_id",
            text("local_date DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_learning_sessions_user_skill", "user_id", "skill_id", "local_date"),
    )


class PracticeProblem(IdMixin, TimestampMixin, SoftDeleteMixin, OwnedMixin, Base):
    __tablename__ = "practice_problems"

    platform: Mapped[str] = mapped_column(String(20), default="leetcode")
    slug: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(500), default=None)
    difficulty: Mapped[str] = mapped_column(String(10), default="medium")
    topics: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    status: Mapped[str] = mapped_column(String(10), default="todo")
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    time_spent_min: Mapped[int] = mapped_column(default=0)
    review_stage: Mapped[int] = mapped_column(SmallInteger, default=0)
    first_solved_at: Mapped[datetime | None] = mapped_column(default=None)
    last_attempted_at: Mapped[datetime | None] = mapped_column(default=None)
    next_review_on: Mapped[date | None] = mapped_column(default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        CheckConstraint(_in("platform", PLATFORMS), name="platform_valid"),
        CheckConstraint("difficulty IN ('easy', 'medium', 'hard')", name="difficulty_valid"),
        CheckConstraint(
            "status IN ('todo', 'attempted', 'solved', 'revisit')", name="status_valid"
        ),
        Index(
            "uq_practice_problems_user_platform_slug",
            "user_id",
            "platform",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_practice_problems_topics", "topics", postgresql_using="gin"),
        Index(
            "ix_practice_problems_review",
            "user_id",
            "next_review_on",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
