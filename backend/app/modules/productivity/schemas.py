import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator

from app.core.schemas import APIModel
from app.modules.productivity.recurrence import validate_rule

TaskStatus = Literal["todo", "in_progress", "done", "cancelled"]
TaskDomain = Literal[
    "general", "growth", "professional", "finance", "health", "habits", "jobs", "social", "news"
]
TaskView = Literal["all", "today", "upcoming", "overdue", "completed"]
COLOR_PATTERN = r"^(#[0-9a-fA-F]{6}|[a-z]{3,20})$"


class TaskListIn(APIModel):
    name: str = Field(min_length=1, max_length=80)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    sort_order: int = Field(default=0, ge=0, le=10_000)


class TaskListUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    sort_order: int | None = Field(default=None, ge=0, le=10_000)
    archived: bool | None = None


class TaskListOut(APIModel):
    id: uuid.UUID
    name: str
    color: str | None
    sort_order: int
    archived_at: datetime | None
    created_at: datetime


class _RecurrenceMixin(APIModel):
    @field_validator("recurrence_rule", check_fields=False)
    @classmethod
    def _valid_rule(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return validate_rule(value)


class TaskIn(_RecurrenceMixin):
    title: str = Field(min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=10_000)
    list_id: uuid.UUID | None = None
    status: TaskStatus = "todo"
    priority: int = Field(default=3, ge=1, le=4)
    due_on: date | None = None
    due_at: datetime | None = None
    domain: TaskDomain = "general"
    recurrence_rule: str | None = Field(default=None, max_length=200)


class TaskUpdate(_RecurrenceMixin):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=10_000)
    list_id: uuid.UUID | None = None
    status: TaskStatus | None = None
    priority: int | None = Field(default=None, ge=1, le=4)
    due_on: date | None = None
    due_at: datetime | None = None
    domain: TaskDomain | None = None
    recurrence_rule: str | None = Field(default=None, max_length=200)
    version: int | None = Field(
        default=None, description="Send the version you edited to detect conflicts."
    )


class TaskOut(APIModel):
    id: uuid.UUID
    list_id: uuid.UUID | None
    title: str
    notes: str | None
    status: TaskStatus
    priority: int
    due_on: date | None
    due_at: datetime | None
    domain: TaskDomain
    recurrence_rule: str | None
    completed_at: datetime | None
    source: str
    version: int
    created_at: datetime
    updated_at: datetime


class TaskCompleteOut(APIModel):
    task: TaskOut
    next_task: TaskOut | None = None


class TaskCounts(APIModel):
    due_today: int
    overdue: int
    completed_today: int
    open_total: int
