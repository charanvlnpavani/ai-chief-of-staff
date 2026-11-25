import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import CurrentAuth, SessionDep
from app.core.pagination import CursorParam, LimitParam, decode_cursor, next_cursor
from app.core.schemas import Page
from app.core.time import local_day_start, local_today
from app.modules.identity import service as identity_service
from app.modules.professional import service
from app.modules.professional.schemas import (
    AttemptIn,
    Difficulty,
    LearningSessionIn,
    LearningSessionOut,
    LearningSessionUpdate,
    LearningSummaryOut,
    ProblemIn,
    ProblemOut,
    ProblemStatsOut,
    ProblemStatus,
    ProblemUpdate,
    SkillIn,
    SkillOut,
    SkillUpdate,
)

router = APIRouter(prefix="/professional", tags=["professional"])

FromParam = Annotated[date | None, Query(alias="from")]
ToParam = Annotated[date | None, Query(alias="to")]


# ------------------------------------------------------------------ skills


@router.get("/skills", response_model=list[SkillOut])
async def list_skills(auth: CurrentAuth, session: SessionDep) -> list[SkillOut]:
    return await service.list_skills(session, auth.user.id, today=local_today(auth.user.timezone))


@router.post("/skills", response_model=SkillOut, status_code=201)
async def create_skill(payload: SkillIn, auth: CurrentAuth, session: SessionDep) -> SkillOut:
    return await service.create_skill(session, auth.user.id, payload)


@router.patch("/skills/{skill_id}", response_model=SkillOut)
async def update_skill(
    skill_id: uuid.UUID, payload: SkillUpdate, auth: CurrentAuth, session: SessionDep
) -> SkillOut:
    return await service.update_skill(session, auth.user.id, skill_id, payload)


@router.delete("/skills/{skill_id}", status_code=204)
async def delete_skill(skill_id: uuid.UUID, auth: CurrentAuth, session: SessionDep) -> Response:
    await service.delete_skill(session, auth.user.id, skill_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ learning sessions


@router.get("/learning-sessions", response_model=Page[LearningSessionOut])
async def list_learning_sessions(
    auth: CurrentAuth,
    session: SessionDep,
    start: FromParam = None,
    end: ToParam = None,
    skill_id: Annotated[uuid.UUID | None, Query(alias="skillId")] = None,
    limit: LimitParam = 50,
    cursor: CursorParam = None,
) -> Page[LearningSessionOut]:
    offset = decode_cursor(cursor)
    rows = await service.list_learning_sessions(
        session, auth.user.id, start=start, end=end, skill_id=skill_id, limit=limit, offset=offset
    )
    return Page[LearningSessionOut](
        items=[LearningSessionOut.model_validate(r) for r in rows[:limit]],
        next_cursor=next_cursor(offset, limit, len(rows)),
    )


@router.post("/learning-sessions", response_model=LearningSessionOut, status_code=201)
async def create_learning_session(
    payload: LearningSessionIn, auth: CurrentAuth, session: SessionDep
) -> LearningSessionOut:
    row = await service.create_learning_session(
        session, auth.user.id, payload, today=local_today(auth.user.timezone)
    )
    return LearningSessionOut.model_validate(row)


@router.get("/learning-sessions/summary", response_model=LearningSummaryOut)
async def learning_summary(
    auth: CurrentAuth, session: SessionDep, start: FromParam = None, end: ToParam = None
) -> LearningSummaryOut:
    today = local_today(auth.user.timezone)
    end = end or today
    start = start or end - timedelta(days=end.weekday())  # this week, Monday onwards
    preferences, _version = await identity_service.get_preferences(session, auth.user.id)
    return await service.learning_summary(
        session,
        auth.user.id,
        start=start,
        end=end,
        goal_minutes=preferences.daily_learning_goal_minutes,
        today=today,
    )


@router.patch("/learning-sessions/{session_id}", response_model=LearningSessionOut)
async def update_learning_session(
    session_id: uuid.UUID, payload: LearningSessionUpdate, auth: CurrentAuth, session: SessionDep
) -> LearningSessionOut:
    row = await service.update_learning_session(
        session, auth.user.id, session_id, payload, today=local_today(auth.user.timezone)
    )
    return LearningSessionOut.model_validate(row)


@router.delete("/learning-sessions/{session_id}", status_code=204)
async def delete_learning_session(
    session_id: uuid.UUID, auth: CurrentAuth, session: SessionDep
) -> Response:
    await service.delete_learning_session(session, auth.user.id, session_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ problems


@router.get("/problems", response_model=Page[ProblemOut])
async def list_problems(
    auth: CurrentAuth,
    session: SessionDep,
    status: ProblemStatus | None = None,
    difficulty: Difficulty | None = None,
    topic: Annotated[str | None, Query(max_length=40)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: LimitParam = 50,
    cursor: CursorParam = None,
) -> Page[ProblemOut]:
    offset = decode_cursor(cursor)
    rows = await service.list_problems(
        session,
        auth.user.id,
        status=status,
        difficulty=difficulty,
        topic=topic,
        search=q,
        limit=limit,
        offset=offset,
    )
    return Page[ProblemOut](
        items=[ProblemOut.model_validate(r) for r in rows[:limit]],
        next_cursor=next_cursor(offset, limit, len(rows)),
    )


@router.post("/problems", response_model=ProblemOut, status_code=201)
async def create_problem(payload: ProblemIn, auth: CurrentAuth, session: SessionDep) -> ProblemOut:
    problem = await service.create_problem(
        session, auth.user.id, payload, today=local_today(auth.user.timezone)
    )
    return ProblemOut.model_validate(problem)


@router.get("/problems/stats", response_model=ProblemStatsOut)
async def problem_stats(auth: CurrentAuth, session: SessionDep) -> ProblemStatsOut:
    today = local_today(auth.user.timezone)
    monday = today - timedelta(days=today.weekday())
    return await service.problem_stats(
        session,
        auth.user.id,
        today=today,
        week_start=local_day_start(auth.user.timezone, monday),
    )


@router.get("/problems/review-queue", response_model=list[ProblemOut])
async def review_queue(
    auth: CurrentAuth, session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[ProblemOut]:
    rows = await service.review_queue(
        session, auth.user.id, today=local_today(auth.user.timezone), limit=limit
    )
    return [ProblemOut.model_validate(r) for r in rows]


@router.get("/problems/{problem_id}", response_model=ProblemOut)
async def get_problem(problem_id: uuid.UUID, auth: CurrentAuth, session: SessionDep) -> ProblemOut:
    return ProblemOut.model_validate(await service.get_problem(session, auth.user.id, problem_id))


@router.patch("/problems/{problem_id}", response_model=ProblemOut)
async def update_problem(
    problem_id: uuid.UUID, payload: ProblemUpdate, auth: CurrentAuth, session: SessionDep
) -> ProblemOut:
    problem = await service.update_problem(session, auth.user.id, problem_id, payload)
    return ProblemOut.model_validate(problem)


@router.post("/problems/{problem_id}/attempts", response_model=ProblemOut)
async def record_attempt(
    problem_id: uuid.UUID, payload: AttemptIn, auth: CurrentAuth, session: SessionDep
) -> ProblemOut:
    problem = await service.record_attempt(
        session, auth.user.id, problem_id, payload, today=local_today(auth.user.timezone)
    )
    return ProblemOut.model_validate(problem)


@router.delete("/problems/{problem_id}", status_code=204)
async def delete_problem(problem_id: uuid.UUID, auth: CurrentAuth, session: SessionDep) -> Response:
    await service.delete_problem(session, auth.user.id, problem_id)
    return Response(status_code=204)
