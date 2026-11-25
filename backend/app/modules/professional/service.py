"""Professional growth: skills, learning sessions (daily goal), DSA practice with spaced review."""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import Select, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequest, Conflict, NotFound
from app.core.time import utc_now
from app.modules.professional.models import LearningSession, PracticeProblem, Skill
from app.modules.professional.schemas import (
    AttemptIn,
    DailyMinutes,
    LearningSessionIn,
    LearningSessionUpdate,
    LearningSummaryOut,
    ProblemIn,
    ProblemStatsOut,
    ProblemUpdate,
    SkillIn,
    SkillMinutes,
    SkillOut,
    SkillUpdate,
    TopicCount,
)

# Days until the next review after each successful solve (a simple Leitner schedule).
REVIEW_INTERVALS = (1, 3, 7, 14, 30, 60, 120)
MAX_SUMMARY_DAYS = 366


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ------------------------------------------------------------------ skills


async def _get_skill(session: AsyncSession, user_id: uuid.UUID, skill_id: uuid.UUID) -> Skill:
    skill = await session.scalar(
        select(Skill).where(
            Skill.id == skill_id, Skill.user_id == user_id, Skill.deleted_at.is_(None)
        )
    )
    if skill is None:
        raise NotFound("Skill not found.")
    return skill


async def _ensure_unique_skill(
    session: AsyncSession, user_id: uuid.UUID, name: str, exclude: uuid.UUID | None = None
) -> None:
    query = select(Skill.id).where(
        Skill.user_id == user_id, func.lower(Skill.name) == name.lower(), Skill.deleted_at.is_(None)
    )
    if exclude is not None:
        query = query.where(Skill.id != exclude)
    if await session.scalar(query) is not None:
        raise Conflict("You already track a skill with this name.", code="duplicate_name")


async def list_skills(session: AsyncSession, user_id: uuid.UUID, *, today: date) -> list[SkillOut]:
    since = today - timedelta(days=29)
    rows = await session.execute(
        select(LearningSession.skill_id, func.sum(LearningSession.duration_min))
        .where(
            LearningSession.user_id == user_id,
            LearningSession.deleted_at.is_(None),
            LearningSession.local_date >= since,
            LearningSession.skill_id.is_not(None),
        )
        .group_by(LearningSession.skill_id)
    )
    # .all() first: dict(result) would treat the Result itself as a mapping (it has .keys()).
    minutes = dict(rows.all())
    skills = await session.scalars(
        select(Skill)
        .where(Skill.user_id == user_id, Skill.deleted_at.is_(None))
        .order_by(Skill.category, Skill.name)
    )
    return [
        SkillOut.model_validate(s).model_copy(
            update={"minutes_last_30_days": int(minutes.get(s.id) or 0)}
        )
        for s in skills
    ]


async def create_skill(session: AsyncSession, user_id: uuid.UUID, data: SkillIn) -> SkillOut:
    await _ensure_unique_skill(session, user_id, data.name)
    skill = Skill(user_id=user_id, **data.model_dump(by_alias=False))
    session.add(skill)
    await session.commit()
    return SkillOut.model_validate(skill)


async def update_skill(
    session: AsyncSession, user_id: uuid.UUID, skill_id: uuid.UUID, data: SkillUpdate
) -> SkillOut:
    skill = await _get_skill(session, user_id, skill_id)
    changes = data.model_dump(exclude_unset=True, by_alias=False)
    if (name := changes.get("name")) is not None:
        await _ensure_unique_skill(session, user_id, name, exclude=skill_id)
    for field, value in changes.items():
        if value is None and field not in {"target_level", "notes"}:
            continue
        setattr(skill, field, value)
    await session.commit()
    return SkillOut.model_validate(skill)


async def delete_skill(session: AsyncSession, user_id: uuid.UUID, skill_id: uuid.UUID) -> None:
    skill = await _get_skill(session, user_id, skill_id)
    skill.deleted_at = utc_now()
    await session.commit()


# ------------------------------------------------------------------ learning sessions


def _owned_sessions(user_id: uuid.UUID) -> Select[LearningSession]:
    return select(LearningSession).where(
        LearningSession.user_id == user_id, LearningSession.deleted_at.is_(None)
    )


async def _get_learning_session(
    session: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
) -> LearningSession:
    row = await session.scalar(_owned_sessions(user_id).where(LearningSession.id == session_id))
    if row is None:
        raise NotFound("Learning session not found.")
    return row


async def list_learning_sessions(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    start: date | None,
    end: date | None,
    skill_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> list[LearningSession]:
    query = _owned_sessions(user_id)
    if start is not None:
        query = query.where(LearningSession.local_date >= start)
    if end is not None:
        query = query.where(LearningSession.local_date <= end)
    if skill_id is not None:
        query = query.where(LearningSession.skill_id == skill_id)
    query = query.order_by(LearningSession.local_date.desc(), LearningSession.created_at.desc())
    return list(await session.scalars(query.offset(offset).limit(limit + 1)))


async def create_learning_session(
    session: AsyncSession, user_id: uuid.UUID, data: LearningSessionIn, *, today: date
) -> LearningSession:
    local_date = data.local_date or today
    if local_date > today + timedelta(days=1):
        raise BadRequest("Sessions cannot be logged for future days.", code="future_date")
    if data.skill_id is not None:
        await _get_skill(session, user_id, data.skill_id)
    row = LearningSession(
        user_id=user_id,
        **data.model_dump(by_alias=False, exclude={"local_date"}),
        local_date=local_date,
    )
    session.add(row)
    await session.commit()
    return row


async def update_learning_session(
    session: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    data: LearningSessionUpdate,
    *,
    today: date,
) -> LearningSession:
    row = await _get_learning_session(session, user_id, session_id)
    changes = data.model_dump(exclude_unset=True, by_alias=False)
    if changes.get("skill_id") is not None:
        await _get_skill(session, user_id, changes["skill_id"])
    if (local_date := changes.get("local_date")) is not None and local_date > today + timedelta(
        days=1
    ):
        raise BadRequest("Sessions cannot be logged for future days.", code="future_date")
    for field, value in changes.items():
        if value is None and field not in {"skill_id", "resource_url", "notes", "focus"}:
            continue
        setattr(row, field, value)
    await session.commit()
    return row


async def delete_learning_session(
    session: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
) -> None:
    row = await _get_learning_session(session, user_id, session_id)
    row.deleted_at = utc_now()
    await session.commit()


async def learning_summary(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    start: date,
    end: date,
    goal_minutes: int,
    today: date,
) -> LearningSummaryOut:
    if end < start:
        raise BadRequest("`to` must be on or after `from`.")
    if (end - start).days >= MAX_SUMMARY_DAYS:
        raise BadRequest(f"A summary covers at most {MAX_SUMMARY_DAYS} days.")

    # One query covers the range plus a year before `end`, so the goal streak can look back.
    lookback_start = min(start, end - timedelta(days=MAX_SUMMARY_DAYS))
    per_day = {
        day: int(minutes)
        for day, minutes in (
            await session.execute(
                select(LearningSession.local_date, func.sum(LearningSession.duration_min))
                .where(
                    LearningSession.user_id == user_id,
                    LearningSession.deleted_at.is_(None),
                    LearningSession.local_date >= lookback_start,
                    LearningSession.local_date <= end,
                )
                .group_by(LearningSession.local_date)
            )
        )
    }

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    daily = [DailyMinutes(date=day, minutes=per_day.get(day, 0)) for day in days]
    total = sum(d.minutes for d in daily)

    streak = 0
    if goal_minutes > 0:
        cursor = end
        if cursor == today and per_day.get(today, 0) < goal_minutes:
            cursor -= timedelta(days=1)  # today is still in progress
        while per_day.get(cursor, 0) >= goal_minutes:
            streak += 1
            cursor -= timedelta(days=1)

    skill_rows = await session.execute(
        select(
            LearningSession.skill_id,
            func.coalesce(Skill.name, "Unassigned"),
            func.sum(LearningSession.duration_min),
        )
        .join(Skill, Skill.id == LearningSession.skill_id, isouter=True)
        .where(
            LearningSession.user_id == user_id,
            LearningSession.deleted_at.is_(None),
            LearningSession.local_date >= start,
            LearningSession.local_date <= end,
        )
        .group_by(LearningSession.skill_id, Skill.name)
        .order_by(func.sum(LearningSession.duration_min).desc())
    )

    return LearningSummaryOut(
        start=start,
        end=end,
        goal_minutes_per_day=goal_minutes,
        total_minutes=total,
        today_minutes=per_day.get(today, 0),
        days_with_sessions=sum(1 for d in daily if d.minutes > 0),
        goal_days_met=sum(1 for d in daily if goal_minutes > 0 and d.minutes >= goal_minutes),
        average_minutes_per_day=round(total / len(daily), 1) if daily else 0.0,
        current_goal_streak=streak,
        daily=daily,
        by_skill=[
            SkillMinutes(skill_id=skill_id, skill_name=name, minutes=int(minutes))
            for skill_id, name, minutes in skill_rows
        ],
    )


# ------------------------------------------------------------------ practice problems


def _owned_problems(user_id: uuid.UUID) -> Select[PracticeProblem]:
    return select(PracticeProblem).where(
        PracticeProblem.user_id == user_id, PracticeProblem.deleted_at.is_(None)
    )


async def get_problem(
    session: AsyncSession, user_id: uuid.UUID, problem_id: uuid.UUID
) -> PracticeProblem:
    problem = await session.scalar(_owned_problems(user_id).where(PracticeProblem.id == problem_id))
    if problem is None:
        raise NotFound("Problem not found.")
    return problem


async def list_problems(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: str | None,
    difficulty: str | None,
    topic: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> list[PracticeProblem]:
    query = _owned_problems(user_id)
    if status is not None:
        query = query.where(PracticeProblem.status == status)
    if difficulty is not None:
        query = query.where(PracticeProblem.difficulty == difficulty)
    if topic:
        query = query.where(PracticeProblem.topics.contains([topic.strip().lower()]))  # @>, GIN
    if search:
        pattern = f"%{_escape_like(search)}%"
        query = query.where(
            PracticeProblem.title.ilike(pattern, escape="\\")
            | PracticeProblem.slug.ilike(pattern, escape="\\")
        )
    query = query.order_by(PracticeProblem.updated_at.desc())
    return list(await session.scalars(query.offset(offset).limit(limit + 1)))


async def create_problem(
    session: AsyncSession, user_id: uuid.UUID, data: ProblemIn, *, today: date
) -> PracticeProblem:
    exists = await session.scalar(
        _owned_problems(user_id).where(
            PracticeProblem.platform == data.platform, PracticeProblem.slug == data.slug
        )
    )
    if exists is not None:
        raise Conflict(
            "This problem is already in your log.", code="duplicate_problem", id=str(exists.id)
        )
    problem = PracticeProblem(user_id=user_id, **data.model_dump(by_alias=False))
    if problem.status == "solved":
        problem.first_solved_at = utc_now()
        problem.next_review_on = today + timedelta(days=REVIEW_INTERVALS[0])
        problem.review_stage = 1
    session.add(problem)
    await session.commit()
    return problem


async def update_problem(
    session: AsyncSession, user_id: uuid.UUID, problem_id: uuid.UUID, data: ProblemUpdate
) -> PracticeProblem:
    problem = await get_problem(session, user_id, problem_id)
    for field, value in data.model_dump(exclude_unset=True, by_alias=False).items():
        if value is None and field not in {"url", "next_review_on", "notes"}:
            continue
        setattr(problem, field, value)
    await session.commit()
    return problem


async def delete_problem(session: AsyncSession, user_id: uuid.UUID, problem_id: uuid.UUID) -> None:
    problem = await get_problem(session, user_id, problem_id)
    problem.deleted_at = utc_now()
    await session.commit()


async def record_attempt(
    session: AsyncSession,
    user_id: uuid.UUID,
    problem_id: uuid.UUID,
    data: AttemptIn,
    *,
    today: date,
) -> PracticeProblem:
    """Logs an attempt and schedules the next review (spaced repetition)."""
    problem = await get_problem(session, user_id, problem_id)
    now = utc_now()
    problem.attempts += 1
    problem.time_spent_min += data.minutes
    problem.last_attempted_at = now
    if data.outcome == "solved":
        stage = min(problem.review_stage, len(REVIEW_INTERVALS) - 1)
        problem.next_review_on = today + timedelta(days=REVIEW_INTERVALS[stage])
        problem.review_stage = min(problem.review_stage + 1, len(REVIEW_INTERVALS) - 1)
        problem.status = "solved"
        problem.first_solved_at = problem.first_solved_at or now
    else:
        problem.next_review_on = today + timedelta(days=1)
        problem.review_stage = 0 if data.outcome == "failed" else max(0, problem.review_stage - 1)
        problem.status = "revisit" if problem.first_solved_at else "attempted"
    await session.commit()
    return problem


async def review_queue(
    session: AsyncSession, user_id: uuid.UUID, *, today: date, limit: int = 20
) -> list[PracticeProblem]:
    query = (
        _owned_problems(user_id)
        .where(PracticeProblem.next_review_on.is_not(None), PracticeProblem.next_review_on <= today)
        .order_by(PracticeProblem.next_review_on, PracticeProblem.review_stage)
        .limit(limit)
    )
    return list(await session.scalars(query))


async def problem_stats(
    session: AsyncSession, user_id: uuid.UUID, *, today: date, week_start: datetime
) -> ProblemStatsOut:
    """`week_start` is the UTC instant the user's current week began."""
    base = (PracticeProblem.user_id == user_id, PracticeProblem.deleted_at.is_(None))
    by_status = {
        status: int(count)
        for status, count in (
            await session.execute(
                select(PracticeProblem.status, func.count())
                .where(*base)
                .group_by(PracticeProblem.status)
            )
        )
    }
    solved_by_difficulty = {
        difficulty: int(count)
        for difficulty, count in (
            await session.execute(
                select(PracticeProblem.difficulty, func.count())
                .where(*base, PracticeProblem.first_solved_at.is_not(None))
                .group_by(PracticeProblem.difficulty)
            )
        )
    }
    solved_this_week = await session.scalar(
        select(func.count()).where(*base, PracticeProblem.first_solved_at >= week_start)
    )
    due = await session.scalar(
        select(func.count()).where(
            *base,
            PracticeProblem.next_review_on.is_not(None),
            PracticeProblem.next_review_on <= today,
        )
    )
    topic = func.unnest(PracticeProblem.topics).label("topic")
    topics = await session.execute(
        select(topic, func.count().label("n"))
        .where(*base)
        .group_by(literal_column("topic"))
        .order_by(literal_column("n").desc(), literal_column("topic"))
        .limit(8)
    )
    return ProblemStatsOut(
        total=sum(by_status.values()),
        by_status={s: by_status.get(s, 0) for s in ("todo", "attempted", "solved", "revisit")},
        solved_by_difficulty={
            d: solved_by_difficulty.get(d, 0) for d in ("easy", "medium", "hard")
        },
        solved_this_week=solved_this_week or 0,
        due_for_review=due or 0,
        top_topics=[TopicCount(topic=t, count=int(n)) for t, n in topics],
    )
