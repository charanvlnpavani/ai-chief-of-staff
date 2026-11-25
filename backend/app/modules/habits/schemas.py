import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, model_validator

from app.core.schemas import APIModel

HabitMeasure = Literal["check", "count", "duration"]
Frequency = Literal["daily", "days_of_week", "n_per_week", "n_per_month"]
ExceptionKind = Literal["vacation", "sick", "rest", "travel", "other"]
COLOR_PATTERN = r"^(#[0-9a-fA-F]{6}|[a-z]{3,20})$"


class ScheduleIn(APIModel):
    frequency: Frequency = "daily"
    days_of_week: list[int] | None = Field(default=None, description="ISO weekdays, 1 = Monday")
    times_per_period: int | None = Field(default=None, ge=1, le=31)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.frequency == "days_of_week":
            days = self.days_of_week or []
            if not days or any(d < 1 or d > 7 for d in days) or len(set(days)) != len(days):
                raise ValueError("days_of_week needs unique weekdays between 1 and 7")
            self.days_of_week = sorted(days)
        else:
            self.days_of_week = None
        if self.frequency in ("n_per_week", "n_per_month"):
            limit = 7 if self.frequency == "n_per_week" else 31
            if self.times_per_period is None or self.times_per_period > limit:
                raise ValueError(f"times_per_period must be between 1 and {limit}")
        else:
            self.times_per_period = None
        return self


class ScheduleOut(APIModel):
    id: uuid.UUID
    valid_from: date
    valid_to: date | None
    frequency: Frequency
    days_of_week: list[int] | None
    times_per_period: int | None


class HabitStatsOut(APIModel):
    current_streak: int
    longest_streak: int
    streak_unit: Literal["day", "week", "month"]
    consistency: float | None
    met: int
    missed: int
    excused: int
    window_days: int


class HabitIn(APIModel):
    name: str = Field(min_length=1, max_length=80)
    category: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=1000)
    measure: HabitMeasure = "check"
    target_value: Decimal = Field(default=Decimal(1), gt=0, le=100_000)
    unit: str | None = Field(default=None, max_length=20)
    icon: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    schedule: ScheduleIn = Field(default_factory=ScheduleIn)
    start_date: date | None = Field(default=None, description="Defaults to today.")


class HabitUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    category: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=1000)
    measure: HabitMeasure | None = None
    target_value: Decimal | None = Field(default=None, gt=0, le=100_000)
    unit: str | None = Field(default=None, max_length=20)
    icon: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    sort_order: int | None = Field(default=None, ge=0, le=10_000)
    archived: bool | None = None
    version: int | None = None


class ScheduleChangeIn(APIModel):
    schedule: ScheduleIn
    effective_from: date | None = Field(default=None, description="Defaults to today.")


class HabitOut(APIModel):
    id: uuid.UUID
    name: str
    category: str | None
    description: str | None
    measure: HabitMeasure
    target_value: float
    unit: str | None
    icon: str | None
    color: str | None
    sort_order: int
    archived_at: datetime | None
    version: int
    created_at: datetime
    schedule: ScheduleOut | None = None
    stats: HabitStatsOut | None = None


class HabitTodayItem(APIModel):
    habit_id: uuid.UUID
    name: str
    icon: str | None
    color: str | None
    measure: HabitMeasure
    target_value: float
    unit: str | None
    scheduled_today: bool
    value_today: float
    done: bool
    status: str
    current_streak: int
    streak_unit: Literal["day", "week", "month"]


class HabitTodayOut(APIModel):
    date: date
    scheduled: int
    completed: int
    items: list[HabitTodayItem]


class CompletionIn(APIModel):
    value: Decimal | None = Field(
        default=None, ge=0, le=100_000, description="Defaults to the target."
    )
    client_mutation_id: uuid.UUID | None = None


class CompletionOut(APIModel):
    habit_id: uuid.UUID
    local_date: date
    value: float
    recorded_at: datetime


class HistoryDay(APIModel):
    date: date
    status: str
    value: float


class HabitHistoryOut(APIModel):
    habit_id: uuid.UUID
    start: date
    end: date
    days: list[HistoryDay]
    stats: HabitStatsOut


class ExceptionIn(APIModel):
    habit_id: uuid.UUID | None = Field(default=None, description="Omit to pause every habit.")
    start_date: date
    end_date: date
    kind: ExceptionKind = "rest"
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _valid_range(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("a break can last at most one year")
        return self


class ExceptionOut(APIModel):
    id: uuid.UUID
    habit_id: uuid.UUID | None
    start_date: date
    end_date: date
    kind: ExceptionKind
    note: str | None
    created_at: datetime


class HabitsSummary(APIModel):
    scheduled: int
    completed: int
    at_risk: list[str]
    items: list[HabitTodayItem]
