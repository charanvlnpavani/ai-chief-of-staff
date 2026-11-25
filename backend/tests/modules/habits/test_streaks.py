"""Streak engine rules (pure functions). Dates are fixed so results are deterministic."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.core.time import local_today
from app.modules.habits.streaks import (
    DayStatus,
    Excuse,
    HabitHistory,
    Schedule,
    compute_stats,
    day_status,
    period_status,
)

MONDAY = date(2026, 11, 2)  # a Monday
DAILY = Schedule(valid_from=MONDAY, valid_to=None, frequency="daily")


def done(*days: date, value: str = "1") -> dict[date, Decimal]:
    return {d: Decimal(value) for d in days}


def d(offset: int) -> date:
    return MONDAY + timedelta(days=offset)


def test_consecutive_days_build_a_streak() -> None:
    history = HabitHistory([DAILY], done(d(0), d(1), d(2)), Decimal(1))
    stats = compute_stats(history, today=d(2))
    assert (stats.current_streak, stats.longest_streak) == (3, 3)
    assert stats.streak_unit == "day"


def test_missed_day_resets_current_but_keeps_longest() -> None:
    history = HabitHistory([DAILY], done(d(0), d(1), d(2), d(4)), Decimal(1))
    stats = compute_stats(history, today=d(4))
    assert stats.current_streak == 1
    assert stats.longest_streak == 3
    assert day_status(history, d(3), d(4)) is DayStatus.MISSED


def test_today_pending_does_not_break_the_streak() -> None:
    history = HabitHistory([DAILY], done(d(0), d(1)), Decimal(1))
    assert day_status(history, d(2), today=d(2)) is DayStatus.PENDING
    assert compute_stats(history, today=d(2)).current_streak == 2


def test_rest_days_do_not_break_a_weekday_habit() -> None:
    mon_wed_fri = Schedule(MONDAY, None, "days_of_week", days_of_week=(1, 3, 5))
    history = HabitHistory([mon_wed_fri], done(d(0), d(2), d(4)), Decimal(1))  # Mon, Wed, Fri
    assert day_status(history, d(1), d(6)) is DayStatus.REST  # Tuesday
    assert compute_stats(history, today=d(6)).current_streak == 3


def test_excused_days_neither_break_streaks_nor_count_against_consistency() -> None:
    sick = Excuse(start=d(2), end=d(3))
    history = HabitHistory([DAILY], done(d(0), d(1), d(4)), Decimal(1), excuses=[sick])
    stats = compute_stats(history, today=d(4))
    assert stats.current_streak == 3
    assert stats.excused == 2
    assert stats.missed == 0
    assert stats.consistency == 1.0


def test_count_habit_needs_the_target_value() -> None:
    history = HabitHistory([DAILY], {d(0): Decimal(6), d(1): Decimal(8)}, Decimal(8))
    assert day_status(history, d(0), d(1)) is DayStatus.MISSED
    assert day_status(history, d(1), d(1)) is DayStatus.MET


def test_schedule_change_keeps_past_days_on_the_old_schedule() -> None:
    # Daily for the first week, then Mon/Wed/Fri from the second Monday.
    first = Schedule(MONDAY, d(7), "daily")
    second = Schedule(d(7), None, "days_of_week", days_of_week=(1, 3, 5))
    values = done(*(d(i) for i in range(7)), d(7), d(9))  # whole first week, then Mon + Wed
    history = HabitHistory([first, second], values, Decimal(1))
    assert day_status(history, d(1), d(9)) is DayStatus.MET  # Tuesday under the daily rule
    assert day_status(history, d(8), d(9)) is DayStatus.REST  # Tuesday under the new rule
    assert compute_stats(history, today=d(9)).current_streak == 9


def test_weekly_quota_counts_streaks_in_weeks() -> None:
    three_a_week = Schedule(MONDAY, None, "n_per_week", times_per_period=3)
    values = done(d(0), d(2), d(4), d(7), d(8), d(10))  # week 1: 3x, week 2: 3x
    history = HabitHistory([three_a_week], values, Decimal(1))
    stats = compute_stats(history, today=d(15))  # Tuesday of week 3, nothing yet
    assert stats.streak_unit == "week"
    assert stats.current_streak == 2
    assert period_status(history, d(14), "week", d(15)) is DayStatus.PENDING


def test_weekly_quota_missed_week_resets() -> None:
    twice = Schedule(MONDAY, None, "n_per_week", times_per_period=2)
    history = HabitHistory([twice], done(d(0), d(1), d(8)), Decimal(1))  # week 2 only once
    assert period_status(history, d(7), "week", d(14)) is DayStatus.MISSED
    assert compute_stats(history, today=d(14)).current_streak == 0


def test_excused_days_lower_a_weekly_quota() -> None:
    five = Schedule(MONDAY, None, "n_per_week", times_per_period=5)
    vacation = Excuse(start=d(2), end=d(6))  # Wed-Sun off, only Mon-Tue eligible
    history = HabitHistory([five], done(d(0), d(1)), Decimal(1), excuses=[vacation])
    assert period_status(history, MONDAY, "week", d(7)) is DayStatus.MET


def test_consistency_is_met_over_measured_days() -> None:
    history = HabitHistory([DAILY], done(d(0), d(2)), Decimal(1))  # d1 missed, d3 today
    stats = compute_stats(history, today=d(3))
    assert stats.met == 2
    assert stats.missed == 1
    assert stats.consistency is not None
    assert round(stats.consistency, 3) == 0.667


def test_untracked_before_start_and_in_future() -> None:
    history = HabitHistory([DAILY], {}, Decimal(1))
    assert day_status(history, MONDAY - timedelta(days=1), MONDAY) is DayStatus.UNTRACKED
    assert day_status(history, d(5), today=d(1)) is DayStatus.UNTRACKED


def test_local_today_around_a_dst_transition() -> None:
    # US clocks jump forward at 02:00 local on 2026-03-08 (07:00 UTC).
    just_before = datetime(2026, 3, 8, 4, 59, tzinfo=UTC)  # 23:59 on Mar 7 in New York
    just_after = datetime(2026, 3, 8, 5, 0, tzinfo=UTC)  # 00:00 on Mar 8 in New York
    assert local_today("America/New_York", just_before) == date(2026, 3, 7)
    assert local_today("America/New_York", just_after) == date(2026, 3, 8)


def test_completions_are_keyed_by_local_date_so_travel_does_not_shift_them() -> None:
    # 23:30 in Kolkata on Nov 5 is still Nov 5 there; the user's local date is what's stored.
    instant = datetime(2026, 11, 5, 18, 0, tzinfo=UTC)
    assert local_today("Asia/Kolkata", instant) == date(2026, 11, 5)
    assert local_today("America/Los_Angeles", instant) == date(2026, 11, 5)
    history = HabitHistory([DAILY], done(date(2026, 11, 5)), Decimal(1))
    assert day_status(history, date(2026, 11, 5), date(2026, 11, 6)) is DayStatus.MET
