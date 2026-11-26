"""Daily plan and progress for a roadmap, as pure functions (no database, no AI).

Today ("slide forward")
  The current day is the first day with an unfinished task. Skipping a day never creates a
  backlog: tomorrow simply shows the same day again, and the finish date moves out by one.
  Tasks ticked today stay visible today. Once the current day is finished, the user may
  start the next day early ("ahead").

Streak
  Consecutive local days, ending today (or yesterday if nothing is ticked yet today), with
  at least one task completed.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol


class TaskLike(Protocol):
    @property
    def day(self) -> int: ...
    @property
    def level(self) -> str: ...
    @property
    def completed_on(self) -> date | None: ...


@dataclass(frozen=True, slots=True)
class LevelProgress:
    level: str
    done: int
    total: int


@dataclass(frozen=True, slots=True)
class Plan:
    days_today: list[int]
    today_complete: bool
    finished: bool
    can_go_ahead: bool
    current_day: int | None
    current_level: str | None
    done: int
    total: int
    total_days: int
    levels: list[LevelProgress]
    streak_days: int
    projected_finish: date | None


def streak(completed_days: set[date], today: date) -> int:
    day = today if today in completed_days else today - timedelta(days=1)
    count = 0
    while day in completed_days:
        count += 1
        day -= timedelta(days=1)
    return count


def plan(tasks: Sequence[TaskLike], today: date, *, ahead: bool = False) -> Plan:
    unfinished_days = sorted({t.day for t in tasks if t.completed_on is None})
    done_today_days = {t.day for t in tasks if t.completed_on == today}
    current_day = unfinished_days[0] if unfinished_days else None

    shown = set(done_today_days)
    # The current day is today's work unless today's work is already finished.
    if current_day is not None and (not done_today_days or current_day <= max(done_today_days)):
        shown.add(current_day)
    today_complete = current_day not in shown
    if ahead and today_complete and current_day is not None:
        shown.add(current_day)

    levels: dict[str, list[int]] = {}
    for t in tasks:
        counts = levels.setdefault(t.level, [0, 0])
        counts[1] += 1
        if t.completed_on is not None:
            counts[0] += 1

    remaining = len(unfinished_days)
    projected = None
    if remaining:
        projected = today + timedelta(days=remaining if today_complete else remaining - 1)

    current_level = next(
        (t.level for t in tasks if t.day == current_day and t.completed_on is None), None
    )
    return Plan(
        days_today=sorted(shown),
        today_complete=today_complete,
        finished=current_day is None,
        can_go_ahead=today_complete and current_day is not None and current_day not in shown,
        current_day=current_day,
        current_level=current_level,
        done=sum(1 for t in tasks if t.completed_on is not None),
        total=len(tasks),
        total_days=len({t.day for t in tasks}),
        levels=[LevelProgress(level, d, n) for level, (d, n) in levels.items()],
        streak_days=streak({t.completed_on for t in tasks if t.completed_on}, today),
        projected_finish=projected,
    )
