import uuid

from fastapi import APIRouter, Response

from app.api.deps import CurrentAuth, SessionDep
from app.core.pagination import CursorParam, LimitParam
from app.core.schemas import Page
from app.core.time import local_today
from app.modules.goals import service
from app.modules.goals.schemas import (
    CheckInIn,
    EntryOut,
    GoalDetailOut,
    GoalIn,
    GoalOut,
    GoalUpdate,
    MilestoneIn,
    MilestoneUpdate,
)

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("", response_model=list[GoalOut])
async def list_goals(
    auth: CurrentAuth, session: SessionDep, include_archived: bool = False
) -> list[GoalOut]:
    return await service.list_goals(
        session,
        auth.user.id,
        today=local_today(auth.user.timezone),
        include_archived=include_archived,
    )


@router.post("", response_model=GoalDetailOut, status_code=201)
async def create_goal(payload: GoalIn, auth: CurrentAuth, session: SessionDep) -> GoalDetailOut:
    return await service.create_goal(
        session, auth.user.id, payload, today=local_today(auth.user.timezone)
    )


@router.get("/{goal_id}", response_model=GoalDetailOut)
async def get_goal(goal_id: uuid.UUID, auth: CurrentAuth, session: SessionDep) -> GoalDetailOut:
    return await service.get_goal(
        session, auth.user.id, goal_id, today=local_today(auth.user.timezone)
    )


@router.get("/{goal_id}/entries", response_model=Page[EntryOut])
async def list_entries(
    goal_id: uuid.UUID,
    auth: CurrentAuth,
    session: SessionDep,
    limit: LimitParam = 50,
    cursor: CursorParam = None,
) -> Page[EntryOut]:
    """Older progress history, newest first. Start from the detail's `entriesNextCursor`."""
    return await service.list_entries(session, auth.user.id, goal_id, cursor=cursor, limit=limit)


@router.patch("/{goal_id}", response_model=GoalDetailOut)
async def update_goal(
    goal_id: uuid.UUID, payload: GoalUpdate, auth: CurrentAuth, session: SessionDep
) -> GoalDetailOut:
    return await service.update_goal(
        session, auth.user.id, goal_id, payload, today=local_today(auth.user.timezone)
    )


@router.delete("/{goal_id}", status_code=204)
async def delete_goal(goal_id: uuid.UUID, auth: CurrentAuth, session: SessionDep) -> Response:
    await service.delete_goal(session, auth.user.id, goal_id)
    return Response(status_code=204)


@router.post("/{goal_id}/milestones", response_model=GoalDetailOut, status_code=201)
async def add_milestone(
    goal_id: uuid.UUID, payload: MilestoneIn, auth: CurrentAuth, session: SessionDep
) -> GoalDetailOut:
    return await service.add_milestone(
        session, auth.user.id, goal_id, payload, today=local_today(auth.user.timezone)
    )


@router.patch("/{goal_id}/milestones/{milestone_id}", response_model=GoalDetailOut)
async def update_milestone(
    goal_id: uuid.UUID,
    milestone_id: uuid.UUID,
    payload: MilestoneUpdate,
    auth: CurrentAuth,
    session: SessionDep,
) -> GoalDetailOut:
    return await service.update_milestone(
        session,
        auth.user.id,
        goal_id,
        milestone_id,
        payload,
        today=local_today(auth.user.timezone),
    )


@router.delete("/{goal_id}/milestones/{milestone_id}", response_model=GoalDetailOut)
async def delete_milestone(
    goal_id: uuid.UUID, milestone_id: uuid.UUID, auth: CurrentAuth, session: SessionDep
) -> GoalDetailOut:
    return await service.delete_milestone(
        session, auth.user.id, goal_id, milestone_id, today=local_today(auth.user.timezone)
    )


@router.post("/{goal_id}/check-ins", response_model=GoalDetailOut, status_code=201)
async def check_in(
    goal_id: uuid.UUID, payload: CheckInIn, auth: CurrentAuth, session: SessionDep
) -> GoalDetailOut:
    return await service.check_in(
        session, auth.user.id, goal_id, payload, today=local_today(auth.user.timezone)
    )
