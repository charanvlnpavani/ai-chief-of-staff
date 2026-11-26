import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import CurrentAuth, SessionDep
from app.core.errors import AppError
from app.core.ratelimit import limiter
from app.core.time import local_today
from app.modules.roadmaps import service
from app.modules.roadmaps.generator import RoadmapGenerator, get_roadmap_generator
from app.modules.roadmaps.schemas import (
    DraftRequest,
    RoadmapDetailOut,
    RoadmapDraft,
    RoadmapOut,
    RoadmapUpdate,
    TemplateOut,
)

router = APIRouter(prefix="/roadmaps", tags=["roadmaps"])


def _optional_generator() -> RoadmapGenerator | None:
    """None when Claude is not configured, so built-in roadmaps still work."""
    try:
        return get_roadmap_generator()
    except AppError:
        return None


GeneratorDep = Annotated[RoadmapGenerator | None, Depends(_optional_generator)]


@router.get("", response_model=list[RoadmapOut])
async def list_roadmaps(
    auth: CurrentAuth, session: SessionDep, include_archived: bool = False
) -> list[RoadmapOut]:
    return await service.list_roadmaps(
        session,
        auth.user.id,
        today=local_today(auth.user.timezone),
        include_archived=include_archived,
    )


@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(auth: CurrentAuth) -> list[TemplateOut]:
    return service.list_templates()


@router.post("/draft", response_model=RoadmapDraft)
async def draft_roadmap(
    payload: DraftRequest, auth: CurrentAuth, session: SessionDep, generator: GeneratorDep
) -> RoadmapDraft:
    """Preview a roadmap for a subject. Nothing is saved until POST /roadmaps."""
    limiter.hit(f"roadmap-draft:{auth.user.id}", limit=5, window_seconds=60)
    return await service.draft(
        session,
        auth.user.id,
        payload,
        timezone=auth.user.timezone,
        today=local_today(auth.user.timezone),
        generator=generator,
    )


@router.post("", response_model=RoadmapDetailOut, status_code=201)
async def create_roadmap(
    payload: RoadmapDraft, auth: CurrentAuth, session: SessionDep
) -> RoadmapDetailOut:
    return await service.create_roadmap(
        session, auth.user.id, payload, today=local_today(auth.user.timezone)
    )


@router.get("/{roadmap_id}", response_model=RoadmapDetailOut)
async def get_roadmap(
    roadmap_id: uuid.UUID, auth: CurrentAuth, session: SessionDep, ahead: bool = False
) -> RoadmapDetailOut:
    """`ahead=true` also shows the next day once today's day is finished."""
    return await service.get_roadmap(
        session, auth.user.id, roadmap_id, today=local_today(auth.user.timezone), ahead=ahead
    )


@router.patch("/{roadmap_id}", response_model=RoadmapDetailOut)
async def update_roadmap(
    roadmap_id: uuid.UUID, payload: RoadmapUpdate, auth: CurrentAuth, session: SessionDep
) -> RoadmapDetailOut:
    return await service.update_roadmap(
        session, auth.user.id, roadmap_id, payload, today=local_today(auth.user.timezone)
    )


@router.delete("/{roadmap_id}", status_code=204)
async def delete_roadmap(roadmap_id: uuid.UUID, auth: CurrentAuth, session: SessionDep) -> Response:
    await service.delete_roadmap(session, auth.user.id, roadmap_id)
    return Response(status_code=204)


@router.put("/{roadmap_id}/tasks/{task_id}/done", response_model=RoadmapDetailOut)
async def complete_task(
    roadmap_id: uuid.UUID,
    task_id: uuid.UUID,
    auth: CurrentAuth,
    session: SessionDep,
    ahead: bool = False,
) -> RoadmapDetailOut:
    return await service.set_task_done(
        session,
        auth.user.id,
        roadmap_id,
        task_id,
        done=True,
        today=local_today(auth.user.timezone),
        ahead=ahead,
    )


@router.delete("/{roadmap_id}/tasks/{task_id}/done", response_model=RoadmapDetailOut)
async def uncomplete_task(
    roadmap_id: uuid.UUID,
    task_id: uuid.UUID,
    auth: CurrentAuth,
    session: SessionDep,
    ahead: bool = False,
) -> RoadmapDetailOut:
    return await service.set_task_done(
        session,
        auth.user.id,
        roadmap_id,
        task_id,
        done=False,
        today=local_today(auth.user.timezone),
        ahead=ahead,
    )
