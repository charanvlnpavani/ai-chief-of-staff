import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import CurrentAuth, SessionDep
from app.core.pagination import CursorParam, LimitParam, decode_cursor, next_cursor
from app.core.schemas import Page
from app.core.time import local_today
from app.modules.productivity import service
from app.modules.productivity.schemas import (
    TaskCompleteOut,
    TaskDomain,
    TaskIn,
    TaskListIn,
    TaskListOut,
    TaskListUpdate,
    TaskOut,
    TaskUpdate,
    TaskView,
)

tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])
lists_router = APIRouter(prefix="/task-lists", tags=["tasks"])


@tasks_router.get("", response_model=Page[TaskOut])
async def list_tasks(
    auth: CurrentAuth,
    session: SessionDep,
    view: TaskView = "all",
    list_id: Annotated[uuid.UUID | None, Query(alias="listId")] = None,
    domain: TaskDomain | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: LimitParam = 50,
    cursor: CursorParam = None,
) -> Page[TaskOut]:
    offset = decode_cursor(cursor)
    rows = await service.list_tasks(
        session,
        auth.user.id,
        today=local_today(auth.user.timezone),
        view=view,
        list_id=list_id,
        domain=domain,
        search=q,
        limit=limit,
        offset=offset,
    )
    return Page[TaskOut](
        items=[TaskOut.model_validate(t) for t in rows[:limit]],
        next_cursor=next_cursor(offset, limit, len(rows)),
    )


@tasks_router.post("", response_model=TaskOut, status_code=201)
async def create_task(payload: TaskIn, auth: CurrentAuth, session: SessionDep) -> TaskOut:
    return TaskOut.model_validate(await service.create_task(session, auth.user.id, payload))


@tasks_router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, auth: CurrentAuth, session: SessionDep) -> TaskOut:
    return TaskOut.model_validate(await service.get_task(session, auth.user.id, task_id))


@tasks_router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID, payload: TaskUpdate, auth: CurrentAuth, session: SessionDep
) -> TaskOut:
    task = await service.update_task(session, auth.user.id, task_id, payload)
    return TaskOut.model_validate(task)


@tasks_router.post("/{task_id}/complete", response_model=TaskCompleteOut)
async def complete_task(
    task_id: uuid.UUID, auth: CurrentAuth, session: SessionDep
) -> TaskCompleteOut:
    task, next_task = await service.complete_task(
        session, auth.user.id, task_id, today=local_today(auth.user.timezone)
    )
    return TaskCompleteOut(
        task=TaskOut.model_validate(task),
        next_task=TaskOut.model_validate(next_task) if next_task else None,
    )


@tasks_router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: uuid.UUID, auth: CurrentAuth, session: SessionDep) -> Response:
    await service.delete_task(session, auth.user.id, task_id)
    return Response(status_code=204)


@lists_router.get("", response_model=list[TaskListOut])
async def list_task_lists(
    auth: CurrentAuth, session: SessionDep, include_archived: bool = False
) -> list[TaskListOut]:
    rows = await service.list_task_lists(session, auth.user.id, include_archived=include_archived)
    return [TaskListOut.model_validate(r) for r in rows]


@lists_router.post("", response_model=TaskListOut, status_code=201)
async def create_task_list(
    payload: TaskListIn, auth: CurrentAuth, session: SessionDep
) -> TaskListOut:
    return TaskListOut.model_validate(
        await service.create_task_list(session, auth.user.id, payload)
    )


@lists_router.patch("/{list_id}", response_model=TaskListOut)
async def update_task_list(
    list_id: uuid.UUID, payload: TaskListUpdate, auth: CurrentAuth, session: SessionDep
) -> TaskListOut:
    task_list = await service.update_task_list(session, auth.user.id, list_id, payload)
    return TaskListOut.model_validate(task_list)


@lists_router.delete("/{list_id}", status_code=204)
async def delete_task_list(list_id: uuid.UUID, auth: CurrentAuth, session: SessionDep) -> Response:
    await service.delete_task_list(session, auth.user.id, list_id)
    return Response(status_code=204)
