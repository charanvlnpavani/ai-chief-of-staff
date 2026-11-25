"""Roadmap planner: daily plan, slide-forward, streak and finish date (pure functions)."""

from dataclasses import dataclass
from datetime import date, timedelta

from app.modules.roadmaps import planner

TODAY = date(2026, 11, 25)


@dataclass
class T:
    day: int
    level: str = "basic"
    completed_on: date | None = None


def roadmap(days: int, per_day: int = 2) -> list[T]:
    levels = ["basic", "intermediate", "advanced", "pro"]
    return [
        T(day=d, level=levels[min((d - 1) * 4 // days, 3)])
        for d in range(1, days + 1)
        for _ in range(per_day)
    ]


def test_fresh_roadmap_starts_on_day_one() -> None:
    result = planner.plan(roadmap(10), TODAY)
    assert result.days_today == [1]
    assert result.today_complete is False
    assert result.current_level == "basic"
    assert result.projected_finish == TODAY + timedelta(days=9)


def test_skipped_days_slide_forward_instead_of_piling_up() -> None:
    tasks = roadmap(10)
    for t in tasks[:2]:
        t.completed_on = TODAY - timedelta(days=5)  # day 1 done five days ago, then nothing
    result = planner.plan(tasks, TODAY)
    assert result.days_today == [2]  # no backlog of days 2-6
    assert result.projected_finish == TODAY + timedelta(days=8)  # 9 days left, starting today
    assert result.streak_days == 0


def test_finishing_today_unlocks_going_ahead() -> None:
    tasks = roadmap(10)
    for t in tasks[:2]:
        t.completed_on = TODAY
    result = planner.plan(tasks, TODAY)
    assert result.days_today == [1]  # ticked tasks stay visible today
    assert result.today_complete is True
    assert result.can_go_ahead is True
    assert result.projected_finish == TODAY + timedelta(days=9)  # next day starts tomorrow
    ahead = planner.plan(tasks, TODAY, ahead=True)
    assert ahead.days_today == [1, 2]
    assert ahead.can_go_ahead is False


def test_partly_done_day_stays_today() -> None:
    tasks = roadmap(10)
    tasks[0].completed_on = TODAY
    result = planner.plan(tasks, TODAY)
    assert result.days_today == [1]
    assert result.today_complete is False


def test_progress_by_level_and_finish() -> None:
    tasks = roadmap(4, per_day=1)
    for t in tasks:
        t.completed_on = TODAY
    result = planner.plan(tasks, TODAY)
    assert result.finished is True
    assert result.projected_finish is None
    assert [(lv.level, lv.done, lv.total) for lv in result.levels] == [
        ("basic", 1, 1),
        ("intermediate", 1, 1),
        ("advanced", 1, 1),
        ("pro", 1, 1),
    ]


def test_streak_counts_consecutive_days() -> None:
    days = {TODAY - timedelta(days=n) for n in (1, 2, 3, 5)}
    assert planner.streak(days, TODAY) == 3  # nothing yet today still keeps yesterday's run
    assert planner.streak(days | {TODAY}, TODAY) == 4
    assert planner.streak(set(), TODAY) == 0
