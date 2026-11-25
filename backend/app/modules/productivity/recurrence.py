"""Recurring tasks use iCalendar RRULE strings, e.g. "FREQ=WEEKLY;BYDAY=MO,WE"."""

from datetime import date, datetime, time

from dateutil.rrule import rrulestr

_FORBIDDEN = ("DTSTART", "\n", "\r")


def validate_rule(rule: str) -> str:
    cleaned = rule.strip().upper()
    if cleaned.startswith("RRULE:"):
        cleaned = cleaned[len("RRULE:") :]
    if any(token in cleaned for token in _FORBIDDEN) or not cleaned.startswith("FREQ="):
        raise ValueError("must be an RRULE such as FREQ=WEEKLY;BYDAY=MO,WE")
    try:
        rrulestr(cleaned, dtstart=datetime(2000, 1, 1))  # noqa: DTZ001 (date-only rules)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid recurrence rule: {exc}") from exc
    return cleaned


def next_occurrence(rule: str, after: date) -> date | None:
    """The first date the rule produces strictly after `after` (anchored at `after`)."""
    start = datetime.combine(after, time())
    occurrence = rrulestr(rule, dtstart=start).after(start, inc=False)
    return occurrence.date() if occurrence else None
