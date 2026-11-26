"""Registers every module's AI tools on import (each module owns its own tools)."""

from app.modules.dashboard import ai_tools as dashboard_tools
from app.modules.goals import ai_tools as goals_tools
from app.modules.habits import ai_tools as habits_tools
from app.modules.productivity import ai_tools as productivity_tools
from app.modules.professional import ai_tools as professional_tools
from app.modules.roadmaps import ai_tools as roadmaps_tools

__all__ = [
    "dashboard_tools",
    "goals_tools",
    "habits_tools",
    "productivity_tools",
    "professional_tools",
    "roadmaps_tools",
]
