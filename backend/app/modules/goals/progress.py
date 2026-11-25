"""Goal progress and health, as pure functions (no database, no AI).

Progress
  milestones  share of milestones completed (None when there are none yet)
  numeric     how far the latest recorded value has moved from the start value toward the
              target, clamped to 0..1. Works for decreasing targets too (weight 80 -> 72).

Health
  paused / completed / archived  follow the stored status
  not_started         nothing to measure yet (a milestone goal with no milestones)
  on_track            no target date, or progress keeps up with the time elapsed
  at_risk             progress trails the time elapsed by more than TOLERANCE, or the target
                      date has passed without reaching the target
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

Health = Literal["on_track", "at_risk", "not_started", "paused", "completed", "archived"]
TOLERANCE = 0.10


@dataclass(frozen=True, slots=True)
class Progress:
    fraction: float | None
    expected: float | None
    health: Health


def numeric_fraction(start: Decimal, target: Decimal, current: Decimal) -> float:
    span = target - start
    if span == 0:
        return 1.0 if current == target else 0.0
    return max(0.0, min(1.0, float((current - start) / span)))


def milestone_fraction(done: int, total: int) -> float | None:
    return done / total if total else None


def expected_fraction(start: date, target: date | None, today: date) -> float | None:
    """Share of the planned time that has passed (None without a target date)."""
    if target is None:
        return None
    total = (target - start).days
    if total <= 0:
        return 1.0 if today >= target else 0.0
    return max(0.0, min(1.0, (today - start).days / total))


def health(
    status: str, fraction: float | None, start: date, target: date | None, today: date
) -> Progress:
    expected = expected_fraction(start, target, today)
    if status == "completed":
        return Progress(fraction, expected, "completed")
    if status == "paused":
        return Progress(fraction, expected, "paused")
    if status == "archived":
        return Progress(fraction, expected, "archived")
    if fraction is None:
        return Progress(fraction, expected, "not_started")
    reached = fraction >= 1.0
    if target is not None and today > target and not reached:
        return Progress(fraction, expected, "at_risk")
    if expected is None or reached:
        return Progress(fraction, expected, "on_track")
    if fraction < expected - TOLERANCE:
        return Progress(fraction, expected, "at_risk")
    return Progress(fraction, expected, "on_track")
