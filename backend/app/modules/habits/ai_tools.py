"""Read-only AI tools for habits."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.ai.registry import ToolContext, tool
from app.modules.habits import service


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@tool(
    name="get_habits_today",
    description="Today's habit checklist: which habits are scheduled, done or still pending, "
    "progress against the target, and each habit's current streak.",
    input_model=NoInput,
    scopes=("habits:read",),
)
async def get_habits_today(ctx: ToolContext, args: NoInput) -> dict[str, Any]:
    view = await service.today_view(ctx.session, ctx.user_id, today=ctx.today)
    return {
        "date": view.date.isoformat(),
        "scheduled": view.scheduled,
        "completed": view.completed,
        "habits": [
            {
                "name": i.name,
                "scheduled_today": i.scheduled_today,
                "done": i.done,
                "progress": f"{i.value_today:g}/{i.target_value:g} {i.unit or ''}".strip(),
                "current_streak": i.current_streak,
                "streak_unit": i.streak_unit,
            }
            for i in view.items
        ],
    }


@tool(
    name="get_habit_stats",
    description="Per-habit statistics over the last 30 days: current and longest streak, "
    "consistency (share of scheduled days met, excused breaks excluded) and schedule.",
    input_model=NoInput,
    scopes=("habits:read",),
)
async def get_habit_stats(ctx: ToolContext, args: NoInput) -> dict[str, Any]:
    habits = await service.list_habits(ctx.session, ctx.user_id, today=ctx.today)
    return {
        "window_days": 30,
        "habits": [
            {
                "name": h.name,
                "schedule": h.schedule.frequency if h.schedule else None,
                "current_streak": h.stats.current_streak if h.stats else 0,
                "longest_streak": h.stats.longest_streak if h.stats else 0,
                "streak_unit": h.stats.streak_unit if h.stats else "day",
                "consistency_percent": (
                    round(h.stats.consistency * 100)
                    if h.stats and h.stats.consistency is not None
                    else None
                ),
                "missed": h.stats.missed if h.stats else 0,
            }
            for h in habits
        ],
    }
