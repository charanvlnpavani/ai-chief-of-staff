"""Version 1 API router. Each domain module contributes its own router."""

from fastapi import APIRouter

from app.ai.router import router as ai_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.goals.router import router as goals_router
from app.modules.habits.router import exceptions_router as habit_exceptions_router
from app.modules.habits.router import router as habits_router
from app.modules.identity.router import auth_router, users_router
from app.modules.productivity.router import lists_router, tasks_router
from app.modules.professional.router import router as professional_router
from app.modules.roadmaps.router import router as roadmaps_router

router = APIRouter()
for module_router in (
    auth_router,
    users_router,
    dashboard_router,
    tasks_router,
    lists_router,
    habits_router,
    habit_exceptions_router,
    goals_router,
    professional_router,
    roadmaps_router,
    ai_router,
):
    router.include_router(module_router)
