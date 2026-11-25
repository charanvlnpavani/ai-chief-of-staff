from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentAuth, SessionDep
from app.core.time import local_today
from app.modules.dashboard import service
from app.modules.dashboard.schemas import DashboardOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
async def get_dashboard(
    auth: CurrentAuth,
    session: SessionDep,
    on: Annotated[date | None, Query(alias="date")] = None,
) -> DashboardOut:
    return await service.get_dashboard(
        session,
        user_id=auth.user.id,
        timezone=auth.user.timezone,
        today=on or local_today(auth.user.timezone),
    )
