"""Read-only AI tools for goals."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.ai.registry import ToolContext, tool
from app.modules.goals import service
from app.modules.goals.schemas import GoalOut

HEALTH_WORDS = {
    "on_track": "on track",
    "at_risk": "at risk (behind schedule)",
    "not_started": "not started",
    "paused": "paused",
    "completed": "completed",
    "archived": "archived",
}


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _pct(value: float | None) -> int | None:
    return round(value * 100) if value is not None else None


def _number(value: float | None) -> str:
    if value is None:
        return "?"
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def summary(g: GoalOut) -> str:
    """One finished sentence per goal, so even a small model repeats the numbers correctly
    instead of combining raw fields (it once reported "1/2 milestones" and "6 books" for
    one numeric goal)."""
    p = g.progress
    parts: list[str] = []
    if g.progress_rule == "numeric":
        unit = f" {g.unit}" if g.unit else ""
        parts.append(f"{_number(p.current_value)} of {_number(g.target_value)}{unit}")
    else:
        parts.append(f"{p.milestones_done} of {p.milestones_total} milestones done")
    if p.percent is not None:
        parts[-1] += f" ({_pct(p.percent)}%)"
    if p.expected is not None and g.status == "active":
        parts.append(f"about {_pct(p.expected)}% expected by now")
    parts.append(HEALTH_WORDS.get(p.health, p.health))
    if g.target_date is not None and g.status == "active":
        left = f"{p.days_left} days left" if p.days_left is not None else "no days left"
        parts.append(f"{left} (target date {g.target_date.isoformat()})")
    return f"{g.title}: " + ", ".join(parts) + "."


@tool(
    name="get_goals",
    description="The user's goals that are not archived. Each goal has a ready-made `summary` "
    "sentence (progress, expected progress, health, days left); quote it rather than "
    "combining the other fields. Progress is calculated from recorded activity.",
    input_model=NoInput,
    scopes=("goals:read",),
)
async def get_goals(ctx: ToolContext, args: NoInput) -> dict[str, Any]:
    goals = await service.list_goals(ctx.session, ctx.user_id, today=ctx.today)
    if not goals:
        return {"goals": [], "summary": "The user has no goals yet."}
    out: list[dict[str, Any]] = []
    for g in goals:
        item: dict[str, Any] = {
            "summary": summary(g),
            "title": g.title,
            "category": g.category,
            "importance": g.importance,
            "status": g.status,
            "health": g.progress.health,
            "progress_percent": _pct(g.progress.percent),
            "expected_percent": _pct(g.progress.expected),
            "target_date": g.target_date.isoformat() if g.target_date else None,
            "days_left": g.progress.days_left,
            "last_check_in": (
                g.progress.last_check_in.isoformat() if g.progress.last_check_in else None
            ),
        }
        # Only the fields that apply to this goal's progress rule, so nothing contradicts.
        if g.progress_rule == "numeric":
            item |= {
                "current_value": g.progress.current_value,
                "start_value": g.start_value,
                "target_value": g.target_value,
                "unit": g.unit,
            }
        else:
            item["milestones_done"] = g.progress.milestones_done
            item["milestones_total"] = g.progress.milestones_total
        out.append(item)
    return {"goals": out}
