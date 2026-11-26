import uuid

from fastapi import APIRouter, Request, Response

from app.api.deps import CurrentAuth, SessionDep
from app.core.pagination import CursorParam, LimitParam
from app.core.schemas import Page
from app.modules.library import service
from app.modules.library.schemas import (
    CountsOut,
    ItemIn,
    ItemKind,
    ItemOut,
    ItemStatus,
    ItemSummaryOut,
    ItemUpdate,
)

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/items", response_model=Page[ItemSummaryOut])
async def list_items(
    auth: CurrentAuth,
    session: SessionDep,
    status: ItemStatus | None = None,
    kind: ItemKind | None = None,
    favorite: bool | None = None,
    limit: LimitParam = 50,
    cursor: CursorParam = None,
) -> Page[ItemSummaryOut]:
    """Saved items outside the trash, newest first."""
    return await service.list_items(
        session,
        auth.user.id,
        status=status,
        kind=kind,
        favorite=favorite,
        cursor=cursor,
        limit=limit,
    )


@router.post("/items", response_model=ItemOut, status_code=201)
async def create_item(payload: ItemIn, auth: CurrentAuth, session: SessionDep) -> ItemOut:
    """Save a note, link, video or excerpt. A link saved before returns 409
    `library_duplicate` with `existingId`."""
    return await service.create_item(session, auth.user.id, payload)


@router.get("/counts", response_model=CountsOut)
async def counts(auth: CurrentAuth, session: SessionDep) -> CountsOut:
    return await service.counts(session, auth.user.id)


@router.get("/trash", response_model=Page[ItemSummaryOut])
async def list_trash(
    auth: CurrentAuth, session: SessionDep, limit: LimitParam = 50, cursor: CursorParam = None
) -> Page[ItemSummaryOut]:
    """Items moved to the trash, most recently deleted first."""
    return await service.list_trash(session, auth.user.id, cursor=cursor, limit=limit)


@router.get("/items/{item_id}", response_model=ItemOut)
async def get_item(item_id: uuid.UUID, auth: CurrentAuth, session: SessionDep) -> ItemOut:
    return await service.get_item(session, auth.user.id, item_id)


@router.patch("/items/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: uuid.UUID, payload: ItemUpdate, auth: CurrentAuth, session: SessionDep
) -> ItemOut:
    return await service.update_item(session, auth.user.id, item_id, payload)


@router.delete("/items/{item_id}", status_code=204)
async def delete_item(
    item_id: uuid.UUID, request: Request, auth: CurrentAuth, session: SessionDep
) -> Response:
    """Move to the trash (restorable)."""
    await service.delete_item(session, auth.user.id, item_id, request=request)
    return Response(status_code=204)


@router.post("/items/{item_id}/restore", response_model=ItemOut)
async def restore_item(
    item_id: uuid.UUID, request: Request, auth: CurrentAuth, session: SessionDep
) -> ItemOut:
    return await service.restore_item(session, auth.user.id, item_id, request=request)


@router.delete("/items/{item_id}/permanent", status_code=204)
async def purge_item(
    item_id: uuid.UUID, request: Request, auth: CurrentAuth, session: SessionDep
) -> Response:
    """Delete an item that is already in the trash, for good."""
    await service.purge_item(session, auth.user.id, item_id, request=request)
    return Response(status_code=204)
