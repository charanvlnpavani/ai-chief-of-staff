"""Imports every module's models so `Base.metadata` is complete (Alembic and tests use this)."""

from app.ai import models as ai_models
from app.modules.goals import models as goals_models
from app.modules.habits import models as habits_models
from app.modules.identity import models as identity_models
from app.modules.productivity import models as productivity_models
from app.modules.professional import models as professional_models
from app.modules.roadmaps import models as roadmaps_models

__all__ = [
    "ai_models",
    "goals_models",
    "habits_models",
    "identity_models",
    "productivity_models",
    "professional_models",
    "roadmaps_models",
]
