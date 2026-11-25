from datetime import date

from app.core.schemas import APIModel
from app.modules.habits.schemas import HabitsSummary
from app.modules.productivity.schemas import TaskCounts, TaskOut
from app.modules.professional.schemas import SkillMinutes


class BriefOut(APIModel):
    """A deterministic headline built from counts. The AI is only used when you ask for a plan."""

    headline: str
    priorities: int
    habits_left: int
    learning_minutes_left: int
    reviews_due: int


class TasksWidget(APIModel):
    counts: TaskCounts
    top: list[TaskOut]


class LearningWidget(APIModel):
    today_minutes: int
    goal_minutes: int
    week_minutes: int
    week_goal_minutes: int
    goal_streak: int
    by_skill: list[SkillMinutes]


class ProblemsWidget(APIModel):
    due_for_review: int
    solved_this_week: int
    total_solved: int


class DashboardOut(APIModel):
    date: date
    timezone: str
    brief: BriefOut
    tasks: TasksWidget
    habits: HabitsSummary
    learning: LearningWidget
    problems: ProblemsWidget
