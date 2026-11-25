import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import CurrentAuth, SessionDep
from app.core.time import local_today
from app.modules.habits import service
from app.modules.habits.schemas import (
    CompletionIn,
    CompletionOut,
    ExceptionIn,
    ExceptionOut,
    HabitHistoryOut,
    HabitIn,
    HabitOut,
    HabitTodayOut,
    HabitUpdate,
    ScheduleChangeIn,
)

router = APIRouter(prefix="/habits", tags=["habits"])
exceptions_router = APIRouter(prefix="/habit-exceptions", tags=["habits"])


@router.get("", response_model=list[HabitOut])
async def list_habits(
    auth: CurrentAuth, session: SessionDep, include_archived: bool = False
) -> list[HabitOut]:
    return await service.list_habits(
        session,
        auth.user.id,
        today=local_today(auth.user.timezone),
        include_archived=include_archived,
    )


@router.post("", response_model=HabitOut, status_code=201)
async def create_habit(payload: HabitIn, auth: CurrentAuth, session: SessionDep) -> HabitOut:
    return await service.create_habit(
        session, auth.user.id, payload, today=local_today(auth.user.timezone)
    )


# Declared before /{habit_id} so "today" is not parsed as an id.
@router.get("/today", response_model=HabitTodayOut)
async def habits_today(
    auth: CurrentAuth,
    session: SessionDep,
    on: Annotated[date | None, Query(alias="date")] = None,
) -> HabitTodayOut:
    return await service.today_view(
        session, auth.user.id, today=on or local_today(auth.user.timezone)
    )


@router.get("/{habit_id}", response_model=HabitOut)
async def get_habit(habit_id: uuid.UUID, auth: CurrentAuth, session: SessionDep) -> HabitOut:
    return await service.get_habit(
        session, auth.user.id, habit_id, today=local_today(auth.user.timezone)
    )


@router.patch("/{habit_id}", response_model=HabitOut)
async def update_habit(
    habit_id: uuid.UUID, payload: HabitUpdate, auth: CurrentAuth, session: SessionDep
) -> HabitOut:
    return await service.update_habit(
        session, auth.user.id, habit_id, payload, today=local_today(auth.user.timezone)
    )


@router.delete("/{habit_id}", status_code=204)
async def delete_habit(habit_id: uuid.UUID, auth: CurrentAuth, session: SessionDep) -> Response:
    await service.delete_habit(session, auth.user.id, habit_id)
    return Response(status_code=204)


@router.post("/{habit_id}/schedule", response_model=HabitOut)
async def change_schedule(
    habit_id: uuid.UUID, payload: ScheduleChangeIn, auth: CurrentAuth, session: SessionDep
) -> HabitOut:
    return await service.change_schedule(
        session, auth.user.id, habit_id, payload, today=local_today(auth.user.timezone)
    )


@router.put("/{habit_id}/completions/{local_date}", response_model=CompletionOut)
async def set_completion(
    habit_id: uuid.UUID,
    local_date: date,
    auth: CurrentAuth,
    session: SessionDep,
    payload: CompletionIn | None = None,
) -> CompletionOut:
    return await service.set_completion(
        session,
        auth.user.id,
        habit_id,
        local_date,
        payload or CompletionIn(),
        tz=auth.user.timezone,
        today=local_today(auth.user.timezone),
    )


@router.delete("/{habit_id}/completions/{local_date}", status_code=204)
async def clear_completion(
    habit_id: uuid.UUID, local_date: date, auth: CurrentAuth, session: SessionDep
) -> Response:
    await service.clear_completion(session, auth.user.id, habit_id, local_date)
    return Response(status_code=204)


@router.get("/{habit_id}/history", response_model=HabitHistoryOut)
async def habit_history(
    habit_id: uuid.UUID,
    auth: CurrentAuth,
    session: SessionDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> HabitHistoryOut:
    today = local_today(auth.user.timezone)
    end = end or today
    start = start or end - timedelta(days=89)
    return await service.history(session, auth.user.id, habit_id, start=start, end=end, today=today)


@exceptions_router.get("", response_model=list[ExceptionOut])
async def list_exceptions(auth: CurrentAuth, session: SessionDep) -> list[ExceptionOut]:
    return await service.list_exceptions(session, auth.user.id)


@exceptions_router.post("", response_model=ExceptionOut, status_code=201)
async def create_exception(
    payload: ExceptionIn, auth: CurrentAuth, session: SessionDep
) -> ExceptionOut:
    return await service.create_exception(session, auth.user.id, payload)


@exceptions_router.delete("/{exception_id}", status_code=204)
async def delete_exception(
    exception_id: uuid.UUID, auth: CurrentAuth, session: SessionDep
) -> Response:
    await service.delete_exception(session, auth.user.id, exception_id)
    return Response(status_code=204)
