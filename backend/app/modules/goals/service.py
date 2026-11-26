"""Goals: definitions, milestones, check-ins and an append-only progress history."""

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequest, Conflict, NotFound
from app.core.pagination import decode_cursor, next_cursor
from app.core.schemas import Page
from app.core.time import utc_now
from app.modules.goals import progress
from app.modules.goals.models import Goal, GoalEntry, GoalMilestone
from app.modules.goals.schemas import (
    ENTRY_PAGE_SIZE,
    MAX_MILESTONES,
    CheckInIn,
    EntryOut,
    GoalDetailOut,
    GoalIn,
    GoalOut,
    GoalProgressOut,
    GoalUpdate,
    MilestoneIn,
    MilestoneOut,
    MilestoneUpdate,
)

BACKFILL_DAYS = 366

# Columns whose change is recorded in the history, so earlier progress keeps its meaning.
TARGET_FIELDS = ("progress_rule", "start_value", "target_value", "unit")

# (latest recorded value, day of the latest check-in) per goal.
CheckInStats = dict[uuid.UUID, tuple[Decimal | None, date | None]]


# ------------------------------------------------------------------ helpers


async def _get_goal(
    session: AsyncSession, user_id: uuid.UUID, goal_id: uuid.UUID, *, lock: bool = False
) -> Goal:
    """Load the user's goal. `lock` takes a row lock so concurrent writes are serialised."""
    query = select(Goal).where(
        Goal.id == goal_id, Goal.user_id == user_id, Goal.deleted_at.is_(None)
    )
    goal = await session.scalar(query.with_for_update() if lock else query)
    if goal is None:
        raise NotFound("Goal not found.")
    return goal


def _ensure_editable(goal: Goal) -> None:
    if goal.status == "archived":
        raise BadRequest("Restore this goal before changing it.", code="goal_archived")


async def _get_milestone(
    session: AsyncSession, goal: Goal, milestone_id: uuid.UUID
) -> GoalMilestone:
    milestone = await session.scalar(
        select(GoalMilestone).where(
            GoalMilestone.id == milestone_id, GoalMilestone.goal_id == goal.id
        )
    )
    if milestone is None:
        raise NotFound("Milestone not found.")
    return milestone


async def _load_milestones(
    session: AsyncSession, goal_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[GoalMilestone]]:
    milestones: dict[uuid.UUID, list[GoalMilestone]] = defaultdict(list)
    if goal_ids:
        for m in await session.scalars(
            select(GoalMilestone)
            .where(GoalMilestone.goal_id.in_(goal_ids))
            .order_by(GoalMilestone.sort_order, GoalMilestone.created_at)
        ):
            milestones[m.goal_id].append(m)
    return milestones


async def _check_in_stats(session: AsyncSession, goal_ids: list[uuid.UUID]) -> CheckInStats:
    """Latest value and last check-in day per goal, computed in SQL (never the full history)."""
    if not goal_ids:
        return {}
    latest = await session.execute(
        select(GoalEntry.goal_id, GoalEntry.value)
        .where(
            GoalEntry.goal_id.in_(goal_ids),
            GoalEntry.kind == "check_in",
            GoalEntry.value.is_not(None),
        )
        .order_by(GoalEntry.goal_id, GoalEntry.local_date.desc(), GoalEntry.created_at.desc())
        .ext(distinct_on(GoalEntry.goal_id))
    )
    values: dict[uuid.UUID, Decimal | None] = dict(latest.all())
    last_days = await session.execute(
        select(GoalEntry.goal_id, func.max(GoalEntry.local_date))
        .where(GoalEntry.goal_id.in_(goal_ids), GoalEntry.kind == "check_in")
        .group_by(GoalEntry.goal_id)
    )
    days: dict[uuid.UUID, date | None] = dict(last_days.all())
    return {gid: (values.get(gid), days.get(gid)) for gid in goal_ids}


async def _entries_page(
    session: AsyncSession, goal_id: uuid.UUID, *, offset: int, limit: int
) -> tuple[list[EntryOut], str | None]:
    rows = list(
        await session.scalars(
            select(GoalEntry)
            .where(GoalEntry.goal_id == goal_id)
            .order_by(GoalEntry.local_date.desc(), GoalEntry.created_at.desc())
            .offset(offset)
            .limit(limit + 1)
        )
    )
    return [EntryOut.model_validate(e) for e in rows[:limit]], next_cursor(offset, limit, len(rows))


def _progress_out(
    goal: Goal,
    milestones: list[GoalMilestone],
    current: Decimal | None,
    last_check_in: date | None,
    today: date,
) -> GoalProgressOut:
    done = sum(1 for m in milestones if m.completed_at is not None)
    if goal.progress_rule == "numeric" and goal.target_value is not None:
        fraction: float | None = progress.numeric_fraction(
            goal.start_value,
            goal.target_value,
            current if current is not None else goal.start_value,
        )
    else:
        fraction = progress.milestone_fraction(done, len(milestones))
    result = progress.health(goal.status, fraction, goal.start_date, goal.target_date, today)
    return GoalProgressOut(
        percent=round(result.fraction, 4) if result.fraction is not None else None,
        expected=round(result.expected, 4) if result.expected is not None else None,
        health=result.health,
        current_value=float(current) if current is not None else None,
        milestones_done=done,
        milestones_total=len(milestones),
        days_left=(goal.target_date - today).days if goal.target_date else None,
        last_check_in=last_check_in,
    )


def _goal_out(
    goal: Goal, milestones: list[GoalMilestone], stats: CheckInStats, today: date
) -> GoalOut:
    current, last_check_in = stats.get(goal.id, (None, None))
    fields = {name: getattr(goal, name) for name in GoalOut.model_fields if name != "progress"}
    return GoalOut(
        **fields, progress=_progress_out(goal, milestones, current, last_check_in, today)
    )


def _entry(goal: Goal, kind: str, local_date: date, **fields: object) -> GoalEntry:
    return GoalEntry(
        user_id=goal.user_id,
        goal_id=goal.id,
        kind=kind,
        local_date=local_date,
        target_value=goal.target_value,
        **fields,
    )


def _num(value: Decimal) -> str:
    """Exact plain-decimal text: 24.00 -> "24", 1500000.00 -> "1500000" (never 1.5e+06)."""
    return format(value.normalize(), "f")


def _check_numeric(goal: Goal) -> None:
    if goal.progress_rule == "numeric":
        if goal.target_value is None:
            raise BadRequest("A numeric goal needs a target value.", code="target_required")
        if goal.target_value == goal.start_value:
            raise BadRequest(
                "The target value must differ from the start value.", code="target_invalid"
            )


# ------------------------------------------------------------------ goals


async def list_goals(
    session: AsyncSession, user_id: uuid.UUID, *, today: date, include_archived: bool = False
) -> list[GoalOut]:
    query = select(Goal).where(Goal.user_id == user_id, Goal.deleted_at.is_(None))
    if not include_archived:
        query = query.where(Goal.status != "archived")
    goals = list(
        await session.scalars(query.order_by(Goal.target_date.nulls_last(), Goal.created_at))
    )
    ids = [g.id for g in goals]
    milestones = await _load_milestones(session, ids)
    stats = await _check_in_stats(session, ids)
    return [_goal_out(g, milestones[g.id], stats, today) for g in goals]


async def get_goal(
    session: AsyncSession, user_id: uuid.UUID, goal_id: uuid.UUID, *, today: date
) -> GoalDetailOut:
    goal = await _get_goal(session, user_id, goal_id)
    milestones = (await _load_milestones(session, [goal.id]))[goal.id]
    stats = await _check_in_stats(session, [goal.id])
    entries, cursor = await _entries_page(session, goal.id, offset=0, limit=ENTRY_PAGE_SIZE)
    base = _goal_out(goal, milestones, stats, today)
    return GoalDetailOut(
        **base.model_dump(by_alias=False),
        milestones=[MilestoneOut.model_validate(m) for m in milestones],
        entries=entries,
        entries_next_cursor=cursor,
    )


async def list_entries(
    session: AsyncSession,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
) -> Page[EntryOut]:
    goal = await _get_goal(session, user_id, goal_id)
    items, next_page = await _entries_page(
        session, goal.id, offset=decode_cursor(cursor), limit=limit
    )
    return Page[EntryOut](items=items, next_cursor=next_page)


async def create_goal(
    session: AsyncSession, user_id: uuid.UUID, data: GoalIn, *, today: date
) -> GoalDetailOut:
    fields = data.model_dump(by_alias=False, exclude={"milestones", "start_date"})
    goal = Goal(user_id=user_id, start_date=data.start_date or today, **fields)
    if goal.target_date is not None and goal.target_date < goal.start_date:
        raise BadRequest("The target date cannot be before the start date.", code="date_order")
    if goal.progress_rule != "numeric":
        goal.target_value = None
    session.add(goal)
    await session.flush()
    for order, milestone in enumerate(data.milestones):
        session.add(
            GoalMilestone(
                user_id=user_id,
                goal_id=goal.id,
                sort_order=order,
                **milestone.model_dump(by_alias=False),
            )
        )
    await session.commit()
    return await get_goal(session, user_id, goal.id, today=today)


async def update_goal(
    session: AsyncSession,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    data: GoalUpdate,
    *,
    today: date,
) -> GoalDetailOut:
    goal = await _get_goal(session, user_id, goal_id, lock=True)
    changes = data.model_dump(exclude_unset=True, by_alias=False)
    expected = changes.pop("version", None)
    if expected is not None and expected != goal.version:
        raise Conflict("This goal changed since you loaded it.", code="version_conflict")
    if set(changes) - {"status"}:
        _ensure_editable(goal)  # an archived goal can only be restored

    before = {field: getattr(goal, field) for field in TARGET_FIELDS}
    old_status = goal.status
    nullable = {"category", "description", "success_metric", "target_date", "unit", "target_value"}
    for field, value in changes.items():
        if value is None and field not in nullable:
            continue
        setattr(goal, field, value)
    if goal.progress_rule != "numeric":
        goal.target_value = None  # same shape as a goal created with milestones
    _check_numeric(goal)
    if goal.target_date is not None and goal.target_date < goal.start_date:
        raise BadRequest("The target date cannot be before the start date.", code="date_order")

    if any(getattr(goal, f) != before[f] for f in TARGET_FIELDS):
        old = (
            f"{_num(before['start_value'])} → {_num(before['target_value'])} "
            f"{before['unit'] or ''}".strip()
            if before["target_value"] is not None
            else "milestones"
        )
        session.add(_entry(goal, "target_change", today, note=f"Target was {old}"))
    if goal.status != old_status:
        if goal.status == "completed" and goal.completed_at is None:
            goal.completed_at = utc_now()
        elif goal.status in ("active", "paused"):
            goal.completed_at = None  # reopened; archiving keeps the completion time
        session.add(_entry(goal, "status_change", today, note=f"{old_status} → {goal.status}"))

    goal.version += 1
    await session.commit()
    return await get_goal(session, user_id, goal_id, today=today)


async def delete_goal(session: AsyncSession, user_id: uuid.UUID, goal_id: uuid.UUID) -> None:
    goal = await _get_goal(session, user_id, goal_id)
    goal.deleted_at = utc_now()
    await session.commit()


# ------------------------------------------------------------------ milestones


async def add_milestone(
    session: AsyncSession, user_id: uuid.UUID, goal_id: uuid.UUID, data: MilestoneIn, *, today: date
) -> GoalDetailOut:
    # The row lock serialises concurrent adds, so the cap and sort order cannot race.
    goal = await _get_goal(session, user_id, goal_id, lock=True)
    _ensure_editable(goal)
    count, last_order = (
        await session.execute(
            select(func.count(), func.max(GoalMilestone.sort_order)).where(
                GoalMilestone.goal_id == goal.id
            )
        )
    ).one()
    if count >= MAX_MILESTONES:
        raise BadRequest(f"A goal can have at most {MAX_MILESTONES} milestones.", code="too_many")
    session.add(
        GoalMilestone(
            user_id=user_id,
            goal_id=goal.id,
            sort_order=0 if last_order is None else last_order + 1,
            **data.model_dump(by_alias=False),
        )
    )
    goal.version += 1
    await session.commit()
    return await get_goal(session, user_id, goal_id, today=today)


async def update_milestone(
    session: AsyncSession,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    milestone_id: uuid.UUID,
    data: MilestoneUpdate,
    *,
    today: date,
) -> GoalDetailOut:
    goal = await _get_goal(session, user_id, goal_id, lock=True)
    _ensure_editable(goal)
    milestone = await _get_milestone(session, goal, milestone_id)
    changes = data.model_dump(exclude_unset=True, by_alias=False)
    done = changes.pop("done", None)
    for field, value in changes.items():
        if value is None and field != "due_date":
            continue
        setattr(milestone, field, value)
    if done is not None and done != (milestone.completed_at is not None):
        milestone.completed_at = utc_now() if done else None
    goal.version += 1
    await session.commit()
    return await get_goal(session, user_id, goal_id, today=today)


async def delete_milestone(
    session: AsyncSession,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    milestone_id: uuid.UUID,
    *,
    today: date,
) -> GoalDetailOut:
    goal = await _get_goal(session, user_id, goal_id, lock=True)
    _ensure_editable(goal)
    milestone = await _get_milestone(session, goal, milestone_id)
    await session.delete(milestone)
    goal.version += 1
    await session.commit()
    return await get_goal(session, user_id, goal_id, today=today)


# ------------------------------------------------------------------ check-ins


async def check_in(
    session: AsyncSession, user_id: uuid.UUID, goal_id: uuid.UUID, data: CheckInIn, *, today: date
) -> GoalDetailOut:
    """Append a check-in. Values are the current total, so the latest one is the progress."""
    goal = await _get_goal(session, user_id, goal_id)
    _ensure_editable(goal)
    if data.value is not None and goal.progress_rule != "numeric":
        raise BadRequest(
            "This goal tracks milestones; add a note or tick a milestone instead.",
            code="value_not_allowed",
        )
    local_date = data.local_date or today
    if local_date > today:
        raise BadRequest("You cannot check in for a future day.", code="future_date")
    if local_date < goal.start_date:
        raise BadRequest("That day is before this goal started.", code="before_start")
    if local_date < today - timedelta(days=BACKFILL_DAYS):
        raise BadRequest("Check-ins can be backfilled up to a year.", code="too_old")
    note = data.note.strip() if data.note and data.note.strip() else None
    session.add(_entry(goal, "check_in", local_date, value=data.value, note=note))
    await session.commit()
    return await get_goal(session, user_id, goal_id, today=today)
