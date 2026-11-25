"""Habits: definitions, versioned schedules, check-ins, breaks and statistics."""

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequest, Conflict, NotFound
from app.core.ids import uuid7
from app.core.time import utc_now
from app.modules.habits import streaks
from app.modules.habits.models import Habit, HabitCompletion, HabitException, HabitScheduleVersion
from app.modules.habits.schemas import (
    CompletionIn,
    CompletionOut,
    ExceptionIn,
    ExceptionOut,
    HabitHistoryOut,
    HabitIn,
    HabitOut,
    HabitsSummary,
    HabitStatsOut,
    HabitTodayItem,
    HabitTodayOut,
    HabitUpdate,
    HistoryDay,
    ScheduleChangeIn,
    ScheduleIn,
    ScheduleOut,
)

STATS_WINDOW_DAYS = 30
BACKFILL_DAYS = 30
MAX_HISTORY_DAYS = 400

Schedules = dict[uuid.UUID, list[HabitScheduleVersion]]
Values = dict[uuid.UUID, dict[date, Decimal]]


# ------------------------------------------------------------------ helpers


def _stats_out(stats: streaks.HabitStats) -> HabitStatsOut:
    return HabitStatsOut(
        current_streak=stats.current_streak,
        longest_streak=stats.longest_streak,
        streak_unit=stats.streak_unit,
        consistency=round(stats.consistency, 4) if stats.consistency is not None else None,
        met=stats.met,
        missed=stats.missed,
        excused=stats.excused,
        window_days=STATS_WINDOW_DAYS,
    )


async def _get_habit(session: AsyncSession, user_id: uuid.UUID, habit_id: uuid.UUID) -> Habit:
    habit = await session.scalar(
        select(Habit).where(
            Habit.id == habit_id, Habit.user_id == user_id, Habit.deleted_at.is_(None)
        )
    )
    if habit is None:
        raise NotFound("Habit not found.")
    return habit


async def _load_context(
    session: AsyncSession, user_id: uuid.UUID, habit_ids: list[uuid.UUID]
) -> tuple[Schedules, Values, list[HabitException]]:
    schedules: Schedules = defaultdict(list)
    values: Values = defaultdict(dict)
    if not habit_ids:
        return schedules, values, []
    for version in await session.scalars(
        select(HabitScheduleVersion)
        .where(HabitScheduleVersion.habit_id.in_(habit_ids))
        .order_by(HabitScheduleVersion.valid_from)
    ):
        schedules[version.habit_id].append(version)
    rows = await session.execute(
        select(HabitCompletion.habit_id, HabitCompletion.local_date, HabitCompletion.value).where(
            HabitCompletion.habit_id.in_(habit_ids), HabitCompletion.deleted_at.is_(None)
        )
    )
    for habit_id, local_date, value in rows:
        values[habit_id][local_date] = value
    exceptions = list(
        await session.scalars(
            select(HabitException).where(
                HabitException.user_id == user_id,
                or_(HabitException.habit_id.in_(habit_ids), HabitException.habit_id.is_(None)),
            )
        )
    )
    return schedules, values, exceptions


def _history(
    habit: Habit,
    schedules: Schedules,
    values: Values,
    exceptions: list[HabitException],
) -> streaks.HabitHistory:
    return streaks.HabitHistory(
        schedules=[
            streaks.Schedule(
                valid_from=v.valid_from,
                valid_to=v.valid_to,
                frequency=v.frequency,
                days_of_week=tuple(v.days_of_week or ()),
                times_per_period=v.times_per_period,
            )
            for v in schedules.get(habit.id, [])
        ],
        values=values.get(habit.id, {}),
        target=habit.target_value,
        excuses=[
            streaks.Excuse(start=e.start_date, end=e.end_date)
            for e in exceptions
            if e.habit_id is None or e.habit_id == habit.id
        ],
    )


def _current_version(versions: list[HabitScheduleVersion]) -> HabitScheduleVersion | None:
    return next((v for v in reversed(versions) if v.valid_to is None), None)


def _habit_out(
    habit: Habit, versions: list[HabitScheduleVersion], stats: streaks.HabitStats | None
) -> HabitOut:
    current = _current_version(versions)
    out = HabitOut.model_validate(habit)
    return out.model_copy(
        update={
            "schedule": ScheduleOut.model_validate(current) if current else None,
            "stats": _stats_out(stats) if stats else None,
        }
    )


def _new_version(
    user_id: uuid.UUID, habit_id: uuid.UUID, schedule: ScheduleIn, valid_from: date
) -> HabitScheduleVersion:
    return HabitScheduleVersion(
        user_id=user_id,
        habit_id=habit_id,
        valid_from=valid_from,
        frequency=schedule.frequency,
        days_of_week=schedule.days_of_week,
        times_per_period=schedule.times_per_period,
    )


# ------------------------------------------------------------------ habits


async def list_habits(
    session: AsyncSession, user_id: uuid.UUID, *, today: date, include_archived: bool = False
) -> list[HabitOut]:
    query = select(Habit).where(Habit.user_id == user_id, Habit.deleted_at.is_(None))
    if not include_archived:
        query = query.where(Habit.archived_at.is_(None))
    habits = list(await session.scalars(query.order_by(Habit.sort_order, Habit.created_at)))
    schedules, values, exceptions = await _load_context(session, user_id, [h.id for h in habits])
    return [
        _habit_out(
            h,
            schedules.get(h.id, []),
            streaks.compute_stats(
                _history(h, schedules, values, exceptions), today, STATS_WINDOW_DAYS
            ),
        )
        for h in habits
    ]


async def get_habit(
    session: AsyncSession, user_id: uuid.UUID, habit_id: uuid.UUID, *, today: date
) -> HabitOut:
    habit = await _get_habit(session, user_id, habit_id)
    schedules, values, exceptions = await _load_context(session, user_id, [habit.id])
    stats = streaks.compute_stats(
        _history(habit, schedules, values, exceptions), today, STATS_WINDOW_DAYS
    )
    return _habit_out(habit, schedules.get(habit.id, []), stats)


async def create_habit(
    session: AsyncSession, user_id: uuid.UUID, data: HabitIn, *, today: date
) -> HabitOut:
    fields = data.model_dump(by_alias=False, exclude={"schedule", "start_date"})
    habit = Habit(user_id=user_id, **fields)
    if habit.measure == "check":
        habit.target_value = Decimal(1)
    session.add(habit)
    await session.flush()
    version = _new_version(user_id, habit.id, data.schedule, data.start_date or today)
    session.add(version)
    await session.commit()
    return _habit_out(habit, [version], None)


async def update_habit(
    session: AsyncSession,
    user_id: uuid.UUID,
    habit_id: uuid.UUID,
    data: HabitUpdate,
    *,
    today: date,
) -> HabitOut:
    habit = await _get_habit(session, user_id, habit_id)
    changes = data.model_dump(exclude_unset=True, by_alias=False)
    expected = changes.pop("version", None)
    if expected is not None and expected != habit.version:
        raise Conflict("This habit changed since you loaded it.", code="version_conflict")
    archived = changes.pop("archived", None)
    nullable = {"category", "description", "unit", "icon", "color"}
    for field, value in changes.items():
        if value is None and field not in nullable:
            continue
        setattr(habit, field, value)
    if habit.measure == "check":
        habit.target_value = Decimal(1)
    if archived is not None:
        habit.archived_at = utc_now() if archived else None
    habit.version += 1
    await session.commit()
    return await get_habit(session, user_id, habit_id, today=today)


async def delete_habit(session: AsyncSession, user_id: uuid.UUID, habit_id: uuid.UUID) -> None:
    habit = await _get_habit(session, user_id, habit_id)
    habit.deleted_at = utc_now()
    await session.commit()


async def change_schedule(
    session: AsyncSession,
    user_id: uuid.UUID,
    habit_id: uuid.UUID,
    data: ScheduleChangeIn,
    *,
    today: date,
) -> HabitOut:
    """Close the current schedule and open a new one, so past days keep their old rules."""
    habit = await _get_habit(session, user_id, habit_id)
    effective = data.effective_from or today
    if effective > today + timedelta(days=366):
        raise BadRequest("A schedule can start at most a year ahead.")
    versions = list(
        await session.scalars(
            select(HabitScheduleVersion)
            .where(HabitScheduleVersion.habit_id == habit.id)
            .order_by(HabitScheduleVersion.valid_from)
        )
    )
    current = _current_version(versions)
    if current is not None and effective < current.valid_from:
        raise BadRequest(
            "The new schedule cannot start before the current one.", code="schedule_backdated"
        )
    if current is not None and effective == current.valid_from:
        current.frequency = data.schedule.frequency
        current.days_of_week = data.schedule.days_of_week
        current.times_per_period = data.schedule.times_per_period
    else:
        if current is not None:
            current.valid_to = effective
            await session.flush()  # close the old range before the new one is inserted
        session.add(_new_version(user_id, habit.id, data.schedule, effective))
    habit.version += 1
    await session.commit()
    return await get_habit(session, user_id, habit_id, today=today)


# ------------------------------------------------------------------ check-ins


async def set_completion(
    session: AsyncSession,
    user_id: uuid.UUID,
    habit_id: uuid.UUID,
    local_date: date,
    data: CompletionIn,
    *,
    tz: str,
    today: date,
    source: str = "web",
) -> CompletionOut:
    """Idempotent check-in: calling it twice for the same day keeps one completion."""
    habit = await _get_habit(session, user_id, habit_id)
    if local_date > today + timedelta(days=1):
        raise BadRequest("You cannot check in for a future day.", code="future_date")
    if local_date < today - timedelta(days=BACKFILL_DAYS):
        raise BadRequest(f"Check-ins can be backfilled up to {BACKFILL_DAYS} days.", code="too_old")
    first_start = await session.scalar(
        select(HabitScheduleVersion.valid_from)
        .where(HabitScheduleVersion.habit_id == habit.id)
        .order_by(HabitScheduleVersion.valid_from)
        .limit(1)
    )
    if first_start is not None and local_date < first_start:
        raise BadRequest("That day is before this habit started.", code="before_start")

    value = data.value if data.value is not None else habit.target_value
    insert = pg_insert(HabitCompletion).values(
        id=uuid7(),
        user_id=user_id,
        habit_id=habit.id,
        local_date=local_date,
        value=value,
        recorded_at=utc_now(),
        tz=tz,
        source=source,
        client_mutation_id=data.client_mutation_id,
    )
    upsert = insert.on_conflict_do_update(
        index_elements=[HabitCompletion.habit_id, HabitCompletion.local_date],
        set_={
            "value": insert.excluded.value,
            "recorded_at": insert.excluded.recorded_at,
            "tz": insert.excluded.tz,
            "source": insert.excluded.source,
            "deleted_at": None,
        },
    ).returning(HabitCompletion)
    try:
        result = await session.execute(upsert, execution_options={"populate_existing": True})
        completion = result.scalar_one()
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflict("This change was already applied.", code="duplicate_mutation") from exc
    return CompletionOut.model_validate(completion)


async def clear_completion(
    session: AsyncSession, user_id: uuid.UUID, habit_id: uuid.UUID, local_date: date
) -> None:
    habit = await _get_habit(session, user_id, habit_id)
    completion = await session.scalar(
        select(HabitCompletion).where(
            HabitCompletion.habit_id == habit.id,
            HabitCompletion.local_date == local_date,
            HabitCompletion.deleted_at.is_(None),
        )
    )
    if completion is not None:
        completion.deleted_at = utc_now()
        await session.commit()


# ------------------------------------------------------------------ views


async def today_view(session: AsyncSession, user_id: uuid.UUID, *, today: date) -> HabitTodayOut:
    habits = list(
        await session.scalars(
            select(Habit)
            .where(
                Habit.user_id == user_id,
                Habit.deleted_at.is_(None),
                Habit.archived_at.is_(None),
            )
            .order_by(Habit.sort_order, Habit.created_at)
        )
    )
    schedules, values, exceptions = await _load_context(session, user_id, [h.id for h in habits])
    items: list[HabitTodayItem] = []
    for habit in habits:
        history = _history(habit, schedules, values, exceptions)
        schedule = history.schedule_on(today)
        if schedule is None:
            continue  # starts in the future
        stats = streaks.compute_stats(history, today, STATS_WINDOW_DAYS)
        status = streaks.day_status(history, today, today)
        items.append(
            HabitTodayItem(
                habit_id=habit.id,
                name=habit.name,
                icon=habit.icon,
                color=habit.color,
                measure=habit.measure,
                target_value=float(habit.target_value),
                unit=habit.unit,
                scheduled_today=schedule.is_scheduled(today),
                value_today=float(history.values.get(today, Decimal(0))),
                done=history.is_met(today),
                status=status.value,
                current_streak=stats.current_streak,
                streak_unit=stats.streak_unit,
            )
        )
    scheduled = [i for i in items if i.scheduled_today]
    return HabitTodayOut(
        date=today,
        scheduled=len(scheduled),
        completed=sum(1 for i in scheduled if i.done),
        items=items,
    )


async def history(
    session: AsyncSession,
    user_id: uuid.UUID,
    habit_id: uuid.UUID,
    *,
    start: date,
    end: date,
    today: date,
) -> HabitHistoryOut:
    if end < start:
        raise BadRequest("`to` must be on or after `from`.")
    if (end - start).days > MAX_HISTORY_DAYS:
        raise BadRequest(f"History is limited to {MAX_HISTORY_DAYS} days per request.")
    habit = await _get_habit(session, user_id, habit_id)
    schedules, values, exceptions = await _load_context(session, user_id, [habit.id])
    habit_history = _history(habit, schedules, values, exceptions)
    days = [
        HistoryDay(date=day, status=status.value, value=float(habit_history.values.get(day, 0)))
        for day, status in streaks.daily_statuses(habit_history, start, end, today)
    ]
    stats = streaks.compute_stats(habit_history, today, STATS_WINDOW_DAYS)
    return HabitHistoryOut(
        habit_id=habit.id, start=start, end=end, days=days, stats=_stats_out(stats)
    )


async def summary(session: AsyncSession, user_id: uuid.UUID, *, today: date) -> HabitsSummary:
    view = await today_view(session, user_id, today=today)
    at_risk = [
        i.name
        for i in view.items
        if i.scheduled_today and not i.done and i.current_streak > 0 and i.streak_unit == "day"
    ]
    return HabitsSummary(
        scheduled=view.scheduled, completed=view.completed, at_risk=at_risk, items=view.items
    )


# ------------------------------------------------------------------ breaks


async def list_exceptions(session: AsyncSession, user_id: uuid.UUID) -> list[ExceptionOut]:
    rows = await session.scalars(
        select(HabitException)
        .where(HabitException.user_id == user_id)
        .order_by(HabitException.start_date.desc())
    )
    return [ExceptionOut.model_validate(r) for r in rows]


async def create_exception(
    session: AsyncSession, user_id: uuid.UUID, data: ExceptionIn
) -> ExceptionOut:
    if data.habit_id is not None:
        await _get_habit(session, user_id, data.habit_id)
    exception = HabitException(user_id=user_id, **data.model_dump(by_alias=False))
    session.add(exception)
    await session.commit()
    return ExceptionOut.model_validate(exception)


async def delete_exception(
    session: AsyncSession, user_id: uuid.UUID, exception_id: uuid.UUID
) -> None:
    exception = await session.scalar(
        select(HabitException).where(
            HabitException.id == exception_id, HabitException.user_id == user_id
        )
    )
    if exception is None:
        raise NotFound("Break not found.")
    await session.delete(exception)
    await session.commit()
