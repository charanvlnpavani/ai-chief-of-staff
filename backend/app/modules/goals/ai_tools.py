"""Read-only AI tools for goals."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.ai.registry import ToolContext, tool
from app.modules.goals import service


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _pct(value: float | None) -> int | None:
    return round(value * 100) if value is not None else None


@tool(
    name="get_goals",
    description="The user's goals that are not archived: status and health (on_track, at_risk, "
    "paused, completed), progress percent calculated from recorded activity, expected percent "
    "from time elapsed, current vs target value, milestones done, target date and days left.",
    input_model=NoInput,
    scopes=("goals:read",),
)
async def get_goals(ctx: ToolContext, args: NoInput) -> dict[str, Any]:
    goals = await service.list_goals(ctx.session, ctx.user_id, today=ctx.today)
    return {
        "goals": [
            {
                "title": g.title,
                "category": g.category,
                "importance": g.importance,
                "status": g.status,
                "health": g.progress.health,
                "progress_percent": _pct(g.progress.percent),
                "expected_percent": _pct(g.progress.expected),
                "progress_rule": g.progress_rule,
                "current_value": g.progress.current_value,
                "start_value": g.start_value if g.progress_rule == "numeric" else None,
                "target_value": g.target_value,
                "unit": g.unit,
                "milestones": f"{g.progress.milestones_done}/{g.progress.milestones_total}",
                "target_date": g.target_date.isoformat() if g.target_date else None,
                "days_left": g.progress.days_left,
                "last_check_in": (
                    g.progress.last_check_in.isoformat() if g.progress.last_check_in else None
                ),
            }
            for g in goals
        ],
    }
