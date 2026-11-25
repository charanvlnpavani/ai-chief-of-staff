"""Read-only AI tools for tasks. Outputs are minimised to what planning needs."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.registry import ToolContext, tool
from app.core.time import local_day_start
from app.modules.productivity import service
from app.modules.productivity.schemas import TaskDomain


class ListTasksInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    view: Literal["today", "overdue", "upcoming", "completed", "all"] = Field(
        default="today",
        description="today = open tasks due today or earlier; overdue = due before today; "
        "upcoming = due later or undated; completed = done tasks.",
    )
    domain: TaskDomain | None = Field(default=None, description="Filter by life area.")
    limit: int = Field(default=15, ge=1, le=25)


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@tool(
    name="list_tasks",
    description="List the user's tasks for a view (today, overdue, upcoming, completed, all). "
    "Returns title, status, priority (1 = highest), due date and life area.",
    input_model=ListTasksInput,
    scopes=("tasks:read",),
)
async def list_tasks(ctx: ToolContext, args: ListTasksInput) -> dict[str, Any]:
    rows = await service.list_tasks(
        ctx.session,
        ctx.user_id,
        today=ctx.today,
        view=args.view,
        domain=args.domain,
        limit=args.limit,
    )
    return {
        "view": args.view,
        "today": ctx.today.isoformat(),
        "tasks": [
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "due_on": t.due_on.isoformat() if t.due_on else None,
                "overdue": bool(t.due_on and t.due_on < ctx.today and t.status != "done"),
                "domain": t.domain,
                "recurring": bool(t.recurrence_rule),
            }
            for t in rows[: args.limit]
        ],
        "has_more": len(rows) > args.limit,
    }


@tool(
    name="get_task_counts",
    description="Counts of tasks due today, overdue, completed today and open in total.",
    input_model=NoInput,
    scopes=("tasks:read",),
)
async def get_task_counts(ctx: ToolContext, args: NoInput) -> dict[str, Any]:
    counts = await service.task_counts(
        ctx.session,
        ctx.user_id,
        today=ctx.today,
        day_start=local_day_start(ctx.timezone, ctx.today),
    )
    return counts.model_dump(by_alias=False)
