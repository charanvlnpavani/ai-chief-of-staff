"""Read-only AI tool: one call that gives the model today's whole picture."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.ai.registry import ToolContext, tool
from app.modules.dashboard import service


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@tool(
    name="get_daily_snapshot",
    description="Today's overview in one call: priority tasks, task counts, habits left and at "
    "risk, learning minutes versus the daily goal and problems due for review. Start here when "
    "the user asks what to focus on.",
    input_model=NoInput,
    scopes=("tasks:read", "habits:read", "learning:read"),
)
async def get_daily_snapshot(ctx: ToolContext, args: NoInput) -> dict[str, Any]:
    dashboard = await service.get_dashboard(
        ctx.session, user_id=ctx.user_id, timezone=ctx.timezone, today=ctx.today
    )
    return {
        "date": dashboard.date.isoformat(),
        "headline": dashboard.brief.headline,
        "task_counts": dashboard.tasks.counts.model_dump(by_alias=False),
        "priority_tasks": [
            {
                "title": t.title,
                "priority": t.priority,
                "due_on": t.due_on.isoformat() if t.due_on else None,
            }
            for t in dashboard.tasks.top
        ],
        "habits": {
            "scheduled": dashboard.habits.scheduled,
            "completed": dashboard.habits.completed,
            "at_risk": dashboard.habits.at_risk,
        },
        "learning": {
            "today_minutes": dashboard.learning.today_minutes,
            "goal_minutes": dashboard.learning.goal_minutes,
            "week_minutes": dashboard.learning.week_minutes,
            "goal_streak_days": dashboard.learning.goal_streak,
        },
        "problems": dashboard.problems.model_dump(by_alias=False),
    }
