"""Today dashboard: aggregates other modules through their public services only."""

import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import local_day_start
from app.modules.dashboard.schemas import (
    BriefOut,
    DashboardOut,
    LearningWidget,
    ProblemsWidget,
    TasksWidget,
)
from app.modules.habits import service as habits_service
from app.modules.identity import service as identity_service
from app.modules.productivity import service as productivity_service
from app.modules.productivity.schemas import TaskOut
from app.modules.professional import service as professional_service


def _count(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def build_headline(priorities: int, habits_left: int, learning_left: int, reviews_due: int) -> str:
    parts: list[str] = []
    if priorities:
        parts.append(_count(priorities, "priority", "priorities"))
    if habits_left:
        parts.append(f"{_count(habits_left, 'habit', 'habits')} left")
    if learning_left:
        parts.append(f"{learning_left} min to your learning goal")
    if reviews_due:
        parts.append(f"{_count(reviews_due, 'review', 'reviews')} due")
    return " · ".join(parts) if parts else "You're all caught up for today."


async def get_dashboard(
    session: AsyncSession, *, user_id: uuid.UUID, timezone: str, today: date
) -> DashboardOut:
    monday = today - timedelta(days=today.weekday())

    counts = await productivity_service.task_counts(
        session, user_id, today=today, day_start=local_day_start(timezone, today)
    )
    top = await productivity_service.priority_tasks(session, user_id, today=today, limit=5)
    habits = await habits_service.summary(session, user_id, today=today)
    preferences, _version = await identity_service.get_preferences(session, user_id)
    goal = preferences.daily_learning_goal_minutes
    learning = await professional_service.learning_summary(
        session, user_id, start=monday, end=today, goal_minutes=goal, today=today
    )
    problems = await professional_service.problem_stats(
        session, user_id, today=today, week_start=local_day_start(timezone, monday)
    )

    priorities = counts.due_today + counts.overdue
    habits_left = max(habits.scheduled - habits.completed, 0)
    learning_left = max(goal - learning.today_minutes, 0)
    return DashboardOut(
        date=today,
        timezone=timezone,
        brief=BriefOut(
            headline=build_headline(
                priorities, habits_left, learning_left, problems.due_for_review
            ),
            priorities=priorities,
            habits_left=habits_left,
            learning_minutes_left=learning_left,
            reviews_due=problems.due_for_review,
        ),
        tasks=TasksWidget(counts=counts, top=[TaskOut.model_validate(t) for t in top]),
        habits=habits,
        learning=LearningWidget(
            today_minutes=learning.today_minutes,
            goal_minutes=goal,
            week_minutes=learning.total_minutes,
            week_goal_minutes=goal * 7,
            goal_streak=learning.current_goal_streak,
            by_skill=learning.by_skill[:3],
        ),
        problems=ProblemsWidget(
            due_for_review=problems.due_for_review,
            solved_this_week=problems.solved_this_week,
            total_solved=sum(problems.solved_by_difficulty.values()),
        ),
    )
