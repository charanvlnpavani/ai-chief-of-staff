"""Read-only AI tools for learning, DSA practice and skills."""

from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.ai.registry import ToolContext, tool
from app.core.time import local_day_start
from app.modules.identity import service as identity_service
from app.modules.professional import service
from app.modules.professional.schemas import Difficulty, ProblemStatus


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LearningSummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(default=7, ge=1, le=90, description="How many days back, including today.")


class ListProblemsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ProblemStatus | None = None
    difficulty: Difficulty | None = None
    topic: str | None = Field(default=None, max_length=40)
    limit: int = Field(default=15, ge=1, le=25)


class ReviewQueueInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=10, ge=1, le=25)


@tool(
    name="get_learning_summary",
    description="Learning time over the last N days against the user's daily goal: totals, "
    "minutes per day, days the goal was met, the current goal streak and time per skill.",
    input_model=LearningSummaryInput,
    scopes=("learning:read",),
)
async def get_learning_summary(ctx: ToolContext, args: LearningSummaryInput) -> dict[str, Any]:
    preferences, _version = await identity_service.get_preferences(ctx.session, ctx.user_id)
    summary = await service.learning_summary(
        ctx.session,
        ctx.user_id,
        start=ctx.today - timedelta(days=args.days - 1),
        end=ctx.today,
        goal_minutes=preferences.daily_learning_goal_minutes,
        today=ctx.today,
    )
    return {
        "from": summary.start.isoformat(),
        "to": summary.end.isoformat(),
        "daily_goal_minutes": summary.goal_minutes_per_day,
        "today_minutes": summary.today_minutes,
        "total_minutes": summary.total_minutes,
        "goal_days_met": summary.goal_days_met,
        "current_goal_streak_days": summary.current_goal_streak,
        "minutes_per_day": {d.date.isoformat(): d.minutes for d in summary.daily},
        "by_skill": [{"skill": s.skill_name, "minutes": s.minutes} for s in summary.by_skill],
    }


@tool(
    name="list_practice_problems",
    description="The user's DSA/LeetCode problem log, filterable by status, difficulty or topic.",
    input_model=ListProblemsInput,
    scopes=("learning:read",),
)
async def list_practice_problems(ctx: ToolContext, args: ListProblemsInput) -> dict[str, Any]:
    rows = await service.list_problems(
        ctx.session,
        ctx.user_id,
        status=args.status,
        difficulty=args.difficulty,
        topic=args.topic,
        search=None,
        limit=args.limit,
        offset=0,
    )
    return {
        "problems": [
            {
                "title": p.title,
                "platform": p.platform,
                "difficulty": p.difficulty,
                "status": p.status,
                "topics": p.topics,
                "attempts": p.attempts,
                "next_review_on": p.next_review_on.isoformat() if p.next_review_on else None,
            }
            for p in rows[: args.limit]
        ],
        "has_more": len(rows) > args.limit,
    }


@tool(
    name="get_review_queue",
    description="Problems due for spaced-repetition review today or earlier, most overdue first.",
    input_model=ReviewQueueInput,
    scopes=("learning:read",),
)
async def get_review_queue(ctx: ToolContext, args: ReviewQueueInput) -> dict[str, Any]:
    rows = await service.review_queue(ctx.session, ctx.user_id, today=ctx.today, limit=args.limit)
    return {
        "due": [
            {
                "title": p.title,
                "difficulty": p.difficulty,
                "topics": p.topics,
                "due_since": p.next_review_on.isoformat() if p.next_review_on else None,
            }
            for p in rows
        ]
    }


@tool(
    name="get_skill_matrix",
    description="Skills the user tracks with current level, target level (0-5) and learning "
    "minutes in the last 30 days, plus problem-solving stats for this week.",
    input_model=NoInput,
    scopes=("learning:read",),
)
async def get_skill_matrix(ctx: ToolContext, args: NoInput) -> dict[str, Any]:
    skills = await service.list_skills(ctx.session, ctx.user_id, today=ctx.today)
    monday = ctx.today - timedelta(days=ctx.today.weekday())
    stats = await service.problem_stats(
        ctx.session,
        ctx.user_id,
        today=ctx.today,
        week_start=local_day_start(ctx.timezone, monday),
    )
    return {
        "skills": [
            {
                "name": s.name,
                "category": s.category,
                "level": s.level,
                "target_level": s.target_level,
                "minutes_last_30_days": s.minutes_last_30_days,
            }
            for s in skills
        ],
        "problems": {
            "solved_this_week": stats.solved_this_week,
            "due_for_review": stats.due_for_review,
            "solved_by_difficulty": stats.solved_by_difficulty,
        },
    }
