"""Tasks and task lists (shared by every manager)."""

import uuid
from datetime import date, datetime

from sqlalchemy import Select, func, nulls_last, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.core.time import utc_now
from app.modules.productivity.models import Task, TaskList
from app.modules.productivity.recurrence import next_occurrence
from app.modules.productivity.schemas import (
    TaskCounts,
    TaskIn,
    TaskListIn,
    TaskListUpdate,
    TaskUpdate,
    TaskView,
)

OPEN_STATUSES = ("todo", "in_progress")


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _owned_tasks(user_id: uuid.UUID) -> Select[Task]:
    return select(Task).where(Task.user_id == user_id, Task.deleted_at.is_(None))


# ------------------------------------------------------------------ lists


async def list_task_lists(
    session: AsyncSession, user_id: uuid.UUID, *, include_archived: bool = False
) -> list[TaskList]:
    query = select(TaskList).where(TaskList.user_id == user_id)
    if not include_archived:
        query = query.where(TaskList.archived_at.is_(None))
    return list(await session.scalars(query.order_by(TaskList.sort_order, TaskList.name)))


async def _get_list(session: AsyncSession, user_id: uuid.UUID, list_id: uuid.UUID) -> TaskList:
    task_list = await session.scalar(
        select(TaskList).where(TaskList.id == list_id, TaskList.user_id == user_id)
    )
    if task_list is None:
        raise NotFound("Task list not found.")
    return task_list


async def _ensure_unique_list_name(
    session: AsyncSession, user_id: uuid.UUID, name: str, exclude: uuid.UUID | None = None
) -> None:
    query = select(TaskList.id).where(
        TaskList.user_id == user_id,
        func.lower(TaskList.name) == name.lower(),
        TaskList.archived_at.is_(None),
    )
    if exclude is not None:
        query = query.where(TaskList.id != exclude)
    if await session.scalar(query) is not None:
        raise Conflict("A list with this name already exists.", code="duplicate_name")


async def create_task_list(session: AsyncSession, user_id: uuid.UUID, data: TaskListIn) -> TaskList:
    await _ensure_unique_list_name(session, user_id, data.name)
    task_list = TaskList(user_id=user_id, **data.model_dump(by_alias=False))
    session.add(task_list)
    await session.commit()
    return task_list


async def update_task_list(
    session: AsyncSession, user_id: uuid.UUID, list_id: uuid.UUID, data: TaskListUpdate
) -> TaskList:
    task_list = await _get_list(session, user_id, list_id)
    changes = data.model_dump(exclude_unset=True, by_alias=False)
    if (name := changes.get("name")) is not None:
        await _ensure_unique_list_name(session, user_id, name, exclude=list_id)
    archived = changes.pop("archived", None)
    for field, value in changes.items():
        if value is not None:
            setattr(task_list, field, value)
    if archived is not None:
        task_list.archived_at = utc_now() if archived else None
    await session.commit()
    return task_list


async def delete_task_list(session: AsyncSession, user_id: uuid.UUID, list_id: uuid.UUID) -> None:
    task_list = await _get_list(session, user_id, list_id)
    await session.delete(task_list)  # tasks keep existing; their list_id becomes NULL
    await session.commit()


# ------------------------------------------------------------------ tasks


async def list_tasks(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    today: date,
    view: TaskView = "all",
    list_id: uuid.UUID | None = None,
    domain: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Task]:
    """Returns up to `limit + 1` rows so the caller can tell whether another page exists."""
    query = _owned_tasks(user_id)
    if list_id is not None:
        query = query.where(Task.list_id == list_id)
    if domain is not None:
        query = query.where(Task.domain == domain)
    if search:
        query = query.where(Task.title.ilike(f"%{_escape_like(search)}%", escape="\\"))

    if view == "completed":
        query = query.where(Task.status == "done").order_by(Task.completed_at.desc())
    elif view == "all":
        query = query.order_by(Task.created_at.desc())
    else:
        query = query.where(Task.status.in_(OPEN_STATUSES))
        if view == "today":
            query = query.where(Task.due_on <= today)
        elif view == "overdue":
            query = query.where(Task.due_on < today)
        elif view == "upcoming":
            query = query.where(or_(Task.due_on > today, Task.due_on.is_(None)))
        query = query.order_by(nulls_last(Task.due_on.asc()), Task.priority, Task.created_at)

    return list(await session.scalars(query.offset(offset).limit(limit + 1)))


async def get_task(session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    task = await session.scalar(_owned_tasks(user_id).where(Task.id == task_id))
    if task is None:
        raise NotFound("Task not found.")
    return task


async def create_task(
    session: AsyncSession, user_id: uuid.UUID, data: TaskIn, *, source: str = "manual"
) -> Task:
    if data.list_id is not None:
        await _get_list(session, user_id, data.list_id)
    task = Task(user_id=user_id, source=source, **data.model_dump(by_alias=False))
    if task.status == "done":
        task.completed_at = utc_now()
    session.add(task)
    await session.commit()
    return task


async def update_task(
    session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID, data: TaskUpdate
) -> Task:
    task = await get_task(session, user_id, task_id)
    changes = data.model_dump(exclude_unset=True, by_alias=False)
    expected_version = changes.pop("version", None)
    if expected_version is not None and expected_version != task.version:
        raise Conflict(
            "This task changed since you loaded it.", code="version_conflict", version=task.version
        )
    if "list_id" in changes and changes["list_id"] is not None:
        await _get_list(session, user_id, changes["list_id"])
    nullable = {"notes", "list_id", "due_on", "due_at", "recurrence_rule"}
    for field, value in changes.items():
        if value is None and field not in nullable:
            continue
        setattr(task, field, value)
    if "status" in changes:
        task.completed_at = utc_now() if task.status == "done" else None
    task.version += 1
    await session.commit()
    return task


async def complete_task(
    session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID, *, today: date
) -> tuple[Task, Task | None]:
    task = await get_task(session, user_id, task_id)
    if task.status == "done":
        return task, None
    task.status = "done"
    task.completed_at = utc_now()
    task.version += 1
    next_task: Task | None = None
    if task.recurrence_rule:
        # An overdue recurring task continues from today, so no backlog of past copies appears.
        base = max(task.due_on, today) if task.due_on else today
        next_due = next_occurrence(task.recurrence_rule, base)
        if next_due is not None:
            next_task = Task(
                user_id=user_id,
                list_id=task.list_id,
                title=task.title,
                notes=task.notes,
                priority=task.priority,
                due_on=next_due,
                domain=task.domain,
                recurrence_rule=task.recurrence_rule,
                source=task.source,
            )
            session.add(next_task)
    await session.commit()
    return task, next_task


async def delete_task(session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> None:
    task = await get_task(session, user_id, task_id)
    task.deleted_at = utc_now()
    await session.commit()


async def task_counts(
    session: AsyncSession, user_id: uuid.UUID, *, today: date, day_start: datetime
) -> TaskCounts:
    """`day_start` is the UTC instant the user's local `today` began."""
    open_filter = (
        Task.user_id == user_id,
        Task.deleted_at.is_(None),
        Task.status.in_(OPEN_STATUSES),
    )
    due_today = await session.scalar(select(func.count()).where(*open_filter, Task.due_on == today))
    overdue = await session.scalar(select(func.count()).where(*open_filter, Task.due_on < today))
    open_total = await session.scalar(select(func.count()).where(*open_filter))
    completed_today = await session.scalar(
        select(func.count()).where(
            Task.user_id == user_id,
            Task.deleted_at.is_(None),
            Task.status == "done",
            Task.completed_at >= day_start,
        )
    )
    return TaskCounts(
        due_today=due_today or 0,
        overdue=overdue or 0,
        completed_today=completed_today or 0,
        open_total=open_total or 0,
    )


async def priority_tasks(
    session: AsyncSession, user_id: uuid.UUID, *, today: date, limit: int = 5
) -> list[Task]:
    """Open tasks due today or earlier first, then the most important undated ones."""
    query = (
        _owned_tasks(user_id)
        .where(Task.status.in_(OPEN_STATUSES), or_(Task.due_on <= today, Task.due_on.is_(None)))
        .order_by(nulls_last(Task.due_on.asc()), Task.priority, Task.created_at)
        .limit(limit)
    )
    return list(await session.scalars(query))
