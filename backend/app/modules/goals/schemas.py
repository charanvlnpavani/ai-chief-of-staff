import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.core.schemas import APIModel

Importance = Literal["low", "medium", "high"]
GoalStatus = Literal["active", "paused", "completed", "archived"]
ProgressRule = Literal["milestones", "numeric"]
Health = Literal["on_track", "at_risk", "not_started", "paused", "completed", "archived"]
EntryKind = Literal["check_in", "target_change", "status_change"]
VALUE_LIMIT = Decimal("999999999999")
MAX_MILESTONES = 50
ENTRY_PAGE_SIZE = 50

# Matches the Numeric(14, 2) columns, so a value is never rounded (or rejected) by Postgres.
Value = Annotated[Decimal, Field(ge=-VALUE_LIMIT, le=VALUE_LIMIT, max_digits=14, decimal_places=2)]


class MilestoneIn(APIModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: date | None = None


class MilestoneUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_date: date | None = None
    done: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10_000)


class MilestoneOut(APIModel):
    id: uuid.UUID
    title: str
    due_date: date | None
    sort_order: int
    completed_at: datetime | None


class GoalIn(APIModel):
    title: str = Field(min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=2000)
    importance: Importance = "medium"
    success_metric: str | None = Field(default=None, max_length=200)
    start_date: date | None = Field(default=None, description="Defaults to today.")
    target_date: date | None = None
    progress_rule: ProgressRule = "milestones"
    start_value: Value = Decimal(0)
    target_value: Value | None = None
    unit: str | None = Field(default=None, max_length=20)
    milestones: list[MilestoneIn] = Field(default_factory=list, max_length=MAX_MILESTONES)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.progress_rule == "numeric":
            if self.target_value is None:
                raise ValueError("a numeric goal needs a target value")
            if self.target_value == self.start_value:
                raise ValueError("the target value must differ from the start value")
        if self.start_date and self.target_date and self.target_date < self.start_date:
            raise ValueError("target_date must be on or after start_date")
        return self


class GoalUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=2000)
    importance: Importance | None = None
    success_metric: str | None = Field(default=None, max_length=200)
    status: GoalStatus | None = None
    target_date: date | None = None
    progress_rule: ProgressRule | None = None
    start_value: Value | None = None
    target_value: Value | None = None
    unit: str | None = Field(default=None, max_length=20)
    version: int | None = None


class CheckInIn(APIModel):
    value: Value | None = Field(
        default=None, description="The current total (not an increment). Numeric goals only."
    )
    note: str | None = Field(default=None, max_length=1000)
    local_date: date | None = Field(default=None, description="Defaults to today.")

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if self.value is None and not (self.note and self.note.strip()):
            raise ValueError("a check-in needs a value or a note")
        return self


class EntryOut(APIModel):
    id: uuid.UUID
    kind: EntryKind
    local_date: date
    value: float | None
    target_value: float | None
    note: str | None
    created_at: datetime


class GoalProgressOut(APIModel):
    percent: float | None = Field(description="0..1, calculated from recorded activity.")
    expected: float | None = Field(description="Share of the planned time already elapsed.")
    health: Health
    current_value: float | None
    milestones_done: int
    milestones_total: int
    days_left: int | None
    last_check_in: date | None


class GoalOut(APIModel):
    id: uuid.UUID
    title: str
    category: str | None
    description: str | None
    importance: Importance
    success_metric: str | None
    status: GoalStatus
    start_date: date
    target_date: date | None
    progress_rule: ProgressRule
    start_value: float
    target_value: float | None
    unit: str | None
    completed_at: datetime | None
    version: int
    created_at: datetime
    progress: GoalProgressOut


class GoalDetailOut(GoalOut):
    milestones: list[MilestoneOut]
    entries: list[EntryOut] = Field(description=f"The {ENTRY_PAGE_SIZE} newest history entries.")
    entries_next_cursor: str | None = Field(
        default=None, description="Pass to GET /goals/{id}/entries for older history."
    )
