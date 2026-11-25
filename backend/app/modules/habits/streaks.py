"""Habit streak and consistency engine: pure functions, no I/O.

Rules
- Each tracked day has one status: met, missed, excused, rest, pending or untracked.
- rest: the habit is not scheduled that day (e.g. a Mon/Wed/Fri habit on a Tuesday).
  Rest days never break a streak.
- excused: the day falls inside a break (vacation, illness, planned rest). Excused days never
  break a streak and are left out of consistency, so legitimate breaks are not punished.
- pending: today, not done yet. Today cannot break a streak until it is over.
- Day-based habits (every day / specific weekdays) count streaks in days.
- Quota habits (N times per week or month) count streaks in periods. A period is met when the
  required count is reached; excused days lower the requirement.
- Every day is judged by the schedule in force on that day, so editing a schedule never
  rewrites history.
- Everything works on the user's local calendar dates (captured at check-in), so time-zone
  changes and daylight-saving transitions cannot shift a completion to the wrong day.
"""

import calendar
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Literal

QUOTA_FREQUENCIES = frozenset({"n_per_week", "n_per_month"})
StreakUnit = Literal["day", "week", "month"]


class DayStatus(StrEnum):
    MET = "met"
    MISSED = "missed"
    EXCUSED = "excused"
    REST = "rest"
    PENDING = "pending"
    UNTRACKED = "untracked"


@dataclass(frozen=True, slots=True)
class Schedule:
    valid_from: date
    valid_to: date | None  # exclusive
    frequency: str
    days_of_week: tuple[int, ...] = ()  # ISO weekdays, 1 = Monday
    times_per_period: int | None = None

    def covers(self, day: date) -> bool:
        return self.valid_from <= day and (self.valid_to is None or day < self.valid_to)

    def is_scheduled(self, day: date) -> bool:
        if self.frequency == "days_of_week":
            return day.isoweekday() in self.days_of_week
        return True  # daily, and every day is eligible for quota habits


@dataclass(frozen=True, slots=True)
class Excuse:
    start: date
    end: date  # inclusive

    def covers(self, day: date) -> bool:
        return self.start <= day <= self.end


@dataclass(frozen=True, slots=True)
class HabitHistory:
    schedules: Sequence[Schedule]
    values: Mapping[date, Decimal]
    target: Decimal
    excuses: Sequence[Excuse] = ()

    def schedule_on(self, day: date) -> Schedule | None:
        return next((s for s in self.schedules if s.covers(day)), None)

    def is_excused(self, day: date) -> bool:
        return any(e.covers(day) for e in self.excuses)

    def is_met(self, day: date) -> bool:
        return self.values.get(day, Decimal(0)) >= self.target

    @property
    def first_day(self) -> date | None:
        return min((s.valid_from for s in self.schedules), default=None)


@dataclass(frozen=True, slots=True)
class HabitStats:
    current_streak: int
    longest_streak: int
    streak_unit: StreakUnit
    consistency: float | None  # 0..1, None when there is nothing to measure yet
    met: int
    missed: int
    excused: int


def _days(start: date, end: date) -> Iterator[date]:
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


# ------------------------------------------------------------------ days


def day_status(history: HabitHistory, day: date, today: date) -> DayStatus:
    if day > today:
        return DayStatus.UNTRACKED
    schedule = history.schedule_on(day)
    if schedule is None:
        return DayStatus.UNTRACKED
    met = history.is_met(day)
    if schedule.frequency in QUOTA_FREQUENCIES:
        # Individual days of a quota habit never "miss"; the period decides.
        if met:
            return DayStatus.MET
        if history.is_excused(day):
            return DayStatus.EXCUSED
        return DayStatus.PENDING if day == today else DayStatus.REST
    if not schedule.is_scheduled(day):
        return DayStatus.REST
    if met:
        return DayStatus.MET
    if history.is_excused(day):
        return DayStatus.EXCUSED
    return DayStatus.PENDING if day == today else DayStatus.MISSED


def _day_based_stats(history: HabitHistory, today: date, window_start: date) -> HabitStats:
    first = history.first_day
    run = longest = met = missed = excused = 0
    if first is not None:
        for day in _days(first, today):
            status = day_status(history, day, today)
            if status is DayStatus.MET:
                run += 1
                longest = max(longest, run)
            elif status is DayStatus.MISSED:
                run = 0
            if day >= window_start:
                met += status is DayStatus.MET
                missed += status is DayStatus.MISSED
                excused += status is DayStatus.EXCUSED
    measured = met + missed
    return HabitStats(
        current_streak=run,  # MET days since the last MISSED day
        longest_streak=longest,
        streak_unit="day",
        consistency=(met / measured) if measured else None,
        met=met,
        missed=missed,
        excused=excused,
    )


# ------------------------------------------------------------------ periods


def period_start(day: date, unit: Literal["week", "month"]) -> date:
    if unit == "week":
        return day - timedelta(days=day.weekday())  # Monday
    return day.replace(day=1)


def period_end(start: date, unit: Literal["week", "month"]) -> date:
    if unit == "week":
        return start + timedelta(days=6)
    return start.replace(day=calendar.monthrange(start.year, start.month)[1])


def period_status(
    history: HabitHistory, start: date, unit: Literal["week", "month"], today: date
) -> DayStatus:
    end = period_end(start, unit)
    if start > today:
        return DayStatus.UNTRACKED
    covered = [d for d in _days(start, end) if history.schedule_on(d) is not None]
    tracked_so_far = [d for d in covered if d <= today]
    if not tracked_so_far:
        return DayStatus.UNTRACKED
    schedule = history.schedule_on(tracked_so_far[-1])
    if schedule is None:  # unreachable: tracked days are covered by definition
        return DayStatus.UNTRACKED
    if schedule.frequency in QUOTA_FREQUENCIES:
        eligible = [d for d in covered if not history.is_excused(d)]
        required = min(schedule.times_per_period or 1, len(eligible))
        done = sum(1 for d in tracked_so_far if history.is_met(d))
    else:
        due = [
            d
            for d in covered
            if (s := history.schedule_on(d)) and s.is_scheduled(d) and not history.is_excused(d)
        ]
        required = len(due)
        done = sum(1 for d in due if d <= today and history.is_met(d))
    if required == 0:
        return DayStatus.EXCUSED
    if done >= required:
        return DayStatus.MET
    return DayStatus.PENDING if end >= today else DayStatus.MISSED


def _next_period(start: date, unit: Literal["week", "month"]) -> date:
    return period_end(start, unit) + timedelta(days=1)


def _period_stats(
    history: HabitHistory, today: date, window_start: date, unit: Literal["week", "month"]
) -> HabitStats:
    first = history.first_day
    run = longest = met = missed = excused = 0
    if first is not None:
        start = period_start(first, unit)
        while start <= today:
            status = period_status(history, start, unit, today)
            if status is DayStatus.MET:
                run += 1
                longest = max(longest, run)
            elif status is DayStatus.MISSED:
                run = 0
            if period_end(start, unit) >= window_start:
                met += status is DayStatus.MET
                missed += status is DayStatus.MISSED
                excused += status is DayStatus.EXCUSED
            start = _next_period(start, unit)
    measured = met + missed
    return HabitStats(
        current_streak=run,
        longest_streak=longest,
        streak_unit=unit,
        consistency=(met / measured) if measured else None,
        met=met,
        missed=missed,
        excused=excused,
    )


# ------------------------------------------------------------------ public API


def compute_stats(history: HabitHistory, today: date, window_days: int = 30) -> HabitStats:
    window_start = today - timedelta(days=window_days - 1)
    current = history.schedule_on(today) or (history.schedules[-1] if history.schedules else None)
    if current is not None and current.frequency == "n_per_week":
        return _period_stats(history, today, window_start, "week")
    if current is not None and current.frequency == "n_per_month":
        return _period_stats(history, today, window_start, "month")
    return _day_based_stats(history, today, window_start)


def daily_statuses(
    history: HabitHistory, start: date, end: date, today: date
) -> list[tuple[date, DayStatus]]:
    return [(day, day_status(history, day, today)) for day in _days(start, end)]
