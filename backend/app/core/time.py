"""Time helpers. Store instants in UTC; derive the user's calendar day from their time zone."""

from datetime import UTC, date, datetime, time
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def utc_now() -> datetime:
    return datetime.now(UTC)


@lru_cache(maxsize=256)
def zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def is_valid_timezone(name: str) -> bool:
    if not name or len(name) > 64:
        return False
    try:
        zone(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def local_now(tz_name: str, now: datetime | None = None) -> datetime:
    return (now or utc_now()).astimezone(zone(tz_name))


def local_today(tz_name: str, now: datetime | None = None) -> date:
    """The calendar date the user is currently living in (DST-safe, uses tz rules)."""
    return local_now(tz_name, now).date()


def local_day_start(tz_name: str, day: date) -> datetime:
    """The UTC instant at which `day` begins in the given time zone."""
    return datetime.combine(day, time(), tzinfo=zone(tz_name)).astimezone(UTC)
