"""Read-only AI tools for learning roadmaps."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.ai.registry import ToolContext, tool
from app.modules.roadmaps import service


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@tool(
    name="get_roadmaps",
    description="The user's learning roadmaps (basic to pro, split into days): subject, "
    "status, tasks done out of total, percent, progress per level, current day and level, "
    "daily streak and the projected finish date. All numbers come from ticked tasks.",
    input_model=NoInput,
    scopes=("roadmaps:read",),
)
async def get_roadmaps(ctx: ToolContext, args: NoInput) -> dict[str, Any]:
    roadmaps = await service.list_roadmaps(ctx.session, ctx.user_id, today=ctx.today)
    return {
        "roadmaps": [
            {
                "subject": r.subject,
                "title": r.title,
                "status": r.status,
                "done": r.progress.done,
                "total": r.progress.total,
                "percent": round(r.progress.percent * 100),
                "levels": {lv.level: f"{lv.done}/{lv.total}" for lv in r.progress.levels},
                "current_day": r.progress.current_day,
                "total_days": r.progress.total_days,
                "current_level": r.progress.current_level,
                "streak_days": r.progress.streak_days,
                "projected_finish": (
                    r.progress.projected_finish.isoformat() if r.progress.projected_finish else None
                ),
            }
            for r in roadmaps
        ],
    }
