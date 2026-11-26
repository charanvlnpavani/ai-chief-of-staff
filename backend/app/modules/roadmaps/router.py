import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response

from app.ai import connections
from app.api.deps import CurrentAuth, SessionDep, SettingsDep
from app.core.db import SessionFactory, get_session_factory
from app.core.ratelimit import limiter
from app.core.time import local_today
from app.modules.roadmaps import service
from app.modules.roadmaps.generator import RoadmapGenerator, generator_for_connection
from app.modules.roadmaps.schemas import (
    MAX_DAYS,
    DayReferenceOut,
    DraftJobOut,
    DraftRequest,
    RoadmapDetailOut,
    RoadmapDraft,
    RoadmapOut,
    RoadmapUpdate,
    TemplateOut,
)

router = APIRouter(prefix="/roadmaps", tags=["roadmaps"])


async def _optional_generator(
    auth: CurrentAuth, session: SessionDep, settings: SettingsDep
) -> RoadmapGenerator | None:
    """The user's Claude generator, or None without a key, so built-in roadmaps still work."""
    connection = await connections.resolve_connection(session, auth.user.id, settings)
    return generator_for_connection(connection) if connection else None


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


@router.post("/draft-jobs", response_model=DraftJobOut, status_code=202)
async def start_draft_job(
    payload: DraftRequest,
    auth: CurrentAuth,
    session: SessionDep,
    generator: GeneratorDep,
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
) -> DraftJobOut:
    """Start drafting a roadmap in the background; poll GET /draft-jobs/{id} for progress.

    A built-in roadmap comes back finished at once. Nothing is saved until POST /roadmaps.
    """
    limiter.hit(f"roadmap-draft:{auth.user.id}", limit=5, window_seconds=60)
    return await service.start_draft_job(
        session,
        auth.user.id,
        payload,
        timezone=auth.user.timezone,
        today=local_today(auth.user.timezone),
        generator=generator,
        session_factory=session_factory,
    )


@router.get("/draft-jobs/{job_id}", response_model=DraftJobOut)
async def get_draft_job(job_id: uuid.UUID, auth: CurrentAuth) -> DraftJobOut:
    return service.get_draft_job(auth.user.id, job_id)


@router.delete("/draft-jobs/{job_id}", response_model=DraftJobOut)
async def cancel_draft_job(job_id: uuid.UUID, auth: CurrentAuth) -> DraftJobOut:
    """Stop a draft that is still being written. Calls already answered are still billed."""
    return await service.cancel_draft_job(auth.user.id, job_id)


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


@router.get("/{roadmap_id}/days/{day}/reference", response_model=DayReferenceOut)
async def get_day_reference(
    roadmap_id: uuid.UUID,
    day: Annotated[int, Path(ge=1, le=MAX_DAYS)],
    auth: CurrentAuth,
    session: SessionDep,
    settings: SettingsDep,
    response: Response,
) -> DayReferenceOut:
    """A roadmap.sh link, plus notes from the local clone for the concept this day teaches.

    The notes come from this machine only (personal use under the roadmap.sh licence), so the
    response must not be cached by anything between the API and the browser.
    """
    response.headers["Cache-Control"] = "private, no-store"
    return await service.get_day_reference(
        session, auth.user.id, roadmap_id, day, content_dir=settings.roadmap_sh_content_dir
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
