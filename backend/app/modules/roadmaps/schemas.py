import uuid
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import APIModel

Level = Literal["basic", "intermediate", "advanced", "pro"]
Source = Literal["template", "ai"]
RoadmapStatus = Literal["active", "paused", "completed", "archived"]
MAX_DAYS = 365
MAX_TASKS_PER_DAY = 6


# ------------------------------------------------------------------ drafts


class DraftRequest(APIModel):
    subject: str = Field(min_length=1, max_length=80)
    target_days: int = Field(default=45, ge=7, le=180, description="Used for AI drafts.")
    minutes_per_day: int = Field(default=60, ge=15, le=300, description="Used for AI drafts.")
    use_template: bool = Field(
        default=True, description="Use a built-in roadmap when one matches the subject."
    )


class DraftTask(APIModel):
    title: str = Field(min_length=1, max_length=200)
    detail: str | None = Field(default=None, max_length=1000)
    minutes: int = Field(default=30, ge=5, le=480)


class DraftDay(APIModel):
    level: Level
    tasks: list[DraftTask] = Field(min_length=1, max_length=MAX_TASKS_PER_DAY)


class RoadmapDraft(APIModel):
    """A plan that is not saved yet. Send it back to POST /roadmaps to keep it."""

    subject: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    source: Source
    template_key: str | None = Field(default=None, max_length=40)
    days: list[DraftDay] = Field(min_length=1, max_length=MAX_DAYS)

    @model_validator(mode="after")
    def _levels_in_order(self) -> Self:
        order = {"basic": 0, "intermediate": 1, "advanced": 2, "pro": 3}
        ranks = [order[d.level] for d in self.days]
        if ranks != sorted(ranks):
            raise ValueError("days must go from basic to pro without stepping back")
        return self


class TemplateOut(APIModel):
    key: str
    subject: str
    title: str
    days: int


class DraftJobError(APIModel):
    code: str
    message: str


class DraftJobOut(APIModel):
    """A roadmap being drafted in the background. Poll until status is done or failed."""

    id: uuid.UUID
    subject: str
    status: Literal["running", "done", "failed", "cancelled"]
    stage: Literal["outline", "writing", "done"] = Field(
        description="outline: planning one concept per day; writing: turning days into tasks."
    )
    days_done: int
    days_total: int = Field(description="0 until the outline is ready.")
    draft: RoadmapDraft | None = None
    error: DraftJobError | None = None


class LearnResourceOut(APIModel):
    kind: str = Field(description="official, opensource, article, video or roadmap.")
    title: str
    url: str


class LearnTopicOut(APIModel):
    title: str
    summary: str
    resources: list[LearnResourceOut]


class DayReferenceOut(APIModel):
    """roadmap.sh link for the roadmap's subject, plus matching topic notes from the user's
    own local clone (personal use only; read from this machine, never stored)."""

    roadmap_name: str | None
    roadmap_url: str | None = Field(description="https://roadmap.sh/<roadmap>, when one fits.")
    topic: LearnTopicOut | None = Field(description="Only with a local clone configured.")
    local_content: bool = Field(description="ROADMAP_SH_CONTENT_DIR is set and found.")


# ------------------------------------------------------------------ AI output schemas
# Plain types only: these are the structured-output schemas the model must follow. Every
# limit is enforced afterwards, when the replies are turned into a RoadmapDraft (drafting.py).


class PlannedOutlineLevel(BaseModel):
    level: Level
    topics: list[str]


class PlannedOutline(BaseModel):
    """Stage 1: one named concept per day, grouped by level."""

    title: str
    levels: list[PlannedOutlineLevel]


class PlannedTopicList(BaseModel):
    """Extra concepts for a level the outline left short."""

    topics: list[str]


class PlannedTask(BaseModel):
    title: str
    detail: str
    minutes: int


class PlannedDay(BaseModel):
    topic: str
    tasks: list[PlannedTask]


class PlannedDays(BaseModel):
    """Stage 2: a batch of outline concepts turned into daily tasks."""

    days: list[PlannedDay]


# ------------------------------------------------------------------ saved roadmaps


class RoadmapUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    status: RoadmapStatus | None = None
    version: int | None = None


class RoadmapTaskOut(APIModel):
    id: uuid.UUID
    day: int
    position: int
    level: Level
    title: str
    detail: str | None
    minutes: int
    completed_on: date | None


class LevelProgressOut(APIModel):
    level: Level
    done: int
    total: int


class RoadmapProgressOut(APIModel):
    done: int
    total: int
    percent: float = Field(description="0..1, from tasks ticked; never estimated by AI.")
    levels: list[LevelProgressOut]
    current_day: int | None
    current_level: Level | None
    total_days: int
    streak_days: int
    projected_finish: date | None = Field(description="Moves out when a day is skipped.")


class RoadmapOut(APIModel):
    id: uuid.UUID
    subject: str
    title: str
    source: Source
    status: RoadmapStatus
    start_date: date
    completed_at: datetime | None
    version: int
    created_at: datetime
    progress: RoadmapProgressOut


class TodayOut(APIModel):
    date: date
    days: list[int] = Field(description="Roadmap day numbers shown today.")
    tasks: list[RoadmapTaskOut]
    complete: bool = Field(description="Today's day is finished.")
    finished: bool = Field(description="The whole roadmap is finished.")
    can_go_ahead: bool = Field(description="The next day can be started early.")


class RoadmapDetailOut(RoadmapOut):
    today: TodayOut
    tasks: list[RoadmapTaskOut]
