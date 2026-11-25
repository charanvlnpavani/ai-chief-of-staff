import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator

from app.core.schemas import APIModel

SkillCategory = Literal[
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
]
Platform = Literal["leetcode", "gfg", "codeforces", "hackerrank", "codechef", "other"]
Difficulty = Literal["easy", "medium", "hard"]
ProblemStatus = Literal["todo", "attempted", "solved", "revisit"]
AttemptOutcome = Literal["solved", "partial", "failed"]

_SLUG = re.compile(r"^[a-z0-9][a-z0-9\-]{0,119}$")


def _normalise_topic_list(value: list[str]) -> list[str]:
    seen: list[str] = []
    for topic in value:
        cleaned = topic.strip().lower()[:40]
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def _validate_url(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if not value.startswith(("https://", "http://")):
        raise ValueError("must start with http:// or https://")
    return value


# ------------------------------------------------------------------ skills


class SkillIn(APIModel):
    name: str = Field(min_length=1, max_length=80)
    category: SkillCategory = "other"
    level: int = Field(default=0, ge=0, le=5)
    target_level: int | None = Field(default=None, ge=0, le=5)
    notes: str | None = Field(default=None, max_length=2000)


class SkillUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    category: SkillCategory | None = None
    level: int | None = Field(default=None, ge=0, le=5)
    target_level: int | None = Field(default=None, ge=0, le=5)
    notes: str | None = Field(default=None, max_length=2000)


class SkillOut(APIModel):
    id: uuid.UUID
    name: str
    category: SkillCategory
    level: int
    target_level: int | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    minutes_last_30_days: int = 0


# ------------------------------------------------------------------ sessions


class LearningSessionIn(APIModel):
    local_date: date | None = Field(default=None, description="Defaults to today.")
    started_at: datetime | None = None
    duration_min: int = Field(ge=1, le=1440)
    skill_id: uuid.UUID | None = None
    topic: str = Field(min_length=1, max_length=200)
    resource_url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    focus: int | None = Field(default=None, ge=1, le=5)
    client_mutation_id: uuid.UUID | None = None

    @field_validator("resource_url")
    @classmethod
    def _valid_url(cls, value: str | None) -> str | None:
        return _validate_url(value)


class LearningSessionUpdate(APIModel):
    local_date: date | None = None
    duration_min: int | None = Field(default=None, ge=1, le=1440)
    skill_id: uuid.UUID | None = None
    topic: str | None = Field(default=None, min_length=1, max_length=200)
    resource_url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    focus: int | None = Field(default=None, ge=1, le=5)

    @field_validator("resource_url")
    @classmethod
    def _valid_url(cls, value: str | None) -> str | None:
        return _validate_url(value)


class LearningSessionOut(APIModel):
    id: uuid.UUID
    local_date: date
    started_at: datetime | None
    duration_min: int
    skill_id: uuid.UUID | None
    topic: str
    resource_url: str | None
    notes: str | None
    focus: int | None
    created_at: datetime


class DailyMinutes(APIModel):
    date: date
    minutes: int


class SkillMinutes(APIModel):
    skill_id: uuid.UUID | None
    skill_name: str
    minutes: int


class LearningSummaryOut(APIModel):
    start: date
    end: date
    goal_minutes_per_day: int
    total_minutes: int
    today_minutes: int
    days_with_sessions: int
    goal_days_met: int
    average_minutes_per_day: float
    current_goal_streak: int
    daily: list[DailyMinutes]
    by_skill: list[SkillMinutes]


# ------------------------------------------------------------------ problems


class ProblemIn(APIModel):
    platform: Platform = "leetcode"
    slug: str = Field(min_length=1, max_length=120, description="e.g. two-sum")
    title: str = Field(min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=500)
    difficulty: Difficulty = "medium"
    topics: list[str] = Field(default_factory=list, max_length=12)
    status: ProblemStatus = "todo"
    notes: str | None = Field(default=None, max_length=10_000)

    @field_validator("slug")
    @classmethod
    def _normalise_slug(cls, value: str) -> str:
        slug = re.sub(r"[^a-z0-9\-]+", "-", value.strip().lower()).strip("-")
        if not _SLUG.match(slug):
            raise ValueError("use lowercase letters, digits and dashes, e.g. two-sum")
        return slug

    @field_validator("topics")
    @classmethod
    def _normalise_topics(cls, value: list[str]) -> list[str]:
        return _normalise_topic_list(value)

    @field_validator("url")
    @classmethod
    def _valid_url(cls, value: str | None) -> str | None:
        return _validate_url(value)


class ProblemUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=500)
    difficulty: Difficulty | None = None
    topics: list[str] | None = Field(default=None, max_length=12)
    status: ProblemStatus | None = None
    next_review_on: date | None = None
    notes: str | None = Field(default=None, max_length=10_000)

    @field_validator("topics")
    @classmethod
    def _normalise_topics(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _normalise_topic_list(value)

    @field_validator("url")
    @classmethod
    def _valid_url(cls, value: str | None) -> str | None:
        return _validate_url(value)


class AttemptIn(APIModel):
    outcome: AttemptOutcome
    minutes: int = Field(default=0, ge=0, le=600)


class ProblemOut(APIModel):
    id: uuid.UUID
    platform: Platform
    slug: str
    title: str
    url: str | None
    difficulty: Difficulty
    topics: list[str]
    status: ProblemStatus
    attempts: int
    time_spent_min: int
    review_stage: int
    first_solved_at: datetime | None
    last_attempted_at: datetime | None
    next_review_on: date | None
    notes: str | None
    created_at: datetime


class TopicCount(APIModel):
    topic: str
    count: int


class ProblemStatsOut(APIModel):
    total: int
    by_status: dict[str, int]
    solved_by_difficulty: dict[str, int]
    solved_this_week: int
    due_for_review: int
    top_topics: list[TopicCount]
