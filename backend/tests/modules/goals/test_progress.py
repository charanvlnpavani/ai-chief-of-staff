"""Goal progress engine: pure functions, no database."""

from datetime import date
from decimal import Decimal

from app.modules.goals import progress

START = date(2026, 1, 1)
TARGET = date(2026, 12, 31)  # 364 days


def test_numeric_fraction_increasing_and_clamped() -> None:
    assert progress.numeric_fraction(Decimal(0), Decimal(24), Decimal(6)) == 0.25
    assert progress.numeric_fraction(Decimal(0), Decimal(24), Decimal(30)) == 1.0
    assert progress.numeric_fraction(Decimal(0), Decimal(24), Decimal(-3)) == 0.0


def test_numeric_fraction_decreasing_target() -> None:
    # Weight 80 -> 72: at 78 a quarter of the way there.
    assert progress.numeric_fraction(Decimal(80), Decimal(72), Decimal(78)) == 0.25
    assert progress.numeric_fraction(Decimal(80), Decimal(72), Decimal(82)) == 0.0


def test_milestone_fraction() -> None:
    assert progress.milestone_fraction(1, 4) == 0.25
    assert progress.milestone_fraction(0, 0) is None


def test_expected_fraction() -> None:
    assert progress.expected_fraction(START, None, date(2026, 6, 1)) is None
    assert progress.expected_fraction(START, TARGET, START) == 0.0
    assert progress.expected_fraction(START, TARGET, date(2027, 3, 1)) == 1.0
    mid = progress.expected_fraction(START, TARGET, date(2026, 7, 2))
    assert mid is not None
    assert abs(mid - 0.5) < 0.01


def test_health_on_track_within_tolerance() -> None:
    today = date(2026, 7, 2)  # ~50% of the time elapsed
    assert progress.health("active", 0.45, START, TARGET, today).health == "on_track"
    assert progress.health("active", 0.30, START, TARGET, today).health == "at_risk"


def test_health_past_target_date() -> None:
    late = date(2027, 1, 5)
    assert progress.health("active", 0.9, START, TARGET, late).health == "at_risk"
    assert progress.health("active", 1.0, START, TARGET, late).health == "on_track"


def test_health_follows_stored_status_and_no_deadline() -> None:
    today = date(2026, 11, 1)
    assert progress.health("paused", 0.0, START, TARGET, today).health == "paused"
    assert progress.health("completed", 0.2, START, TARGET, today).health == "completed"
    assert progress.health("active", 0.0, START, None, today).health == "on_track"
