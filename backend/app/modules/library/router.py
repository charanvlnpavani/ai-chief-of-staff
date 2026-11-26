import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.api.deps import CurrentAuth, SessionDep
from app.core.pagination import CursorParam, LimitParam
from app.core.schemas import Page
from app.modules.library import collections, service, tagging
from app.modules.library.schemas import (
    QUERY_MAX,
    TAG_MAX,
    CollectionIn,
    CollectionOut,
    CollectionUpdate,
    CountsOut,
    ItemIn,
    ItemKind,
    ItemOut,
    ItemStatus,
    ItemSummaryOut,
    ItemUpdate,
    TagOut,
    TagUpdate,
)

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/items", response_model=Page[ItemSummaryOut])
async def list_items(
    auth: CurrentAuth,
    session: SessionDep,
    q: Annotated[
        str | None,
        Query(
            max_length=QUERY_MAX,
            description='Search title, excerpt, note, link and tags. Supports "phrases", '
            "-exclude and OR. Results are ordered by relevance.",
        ),
    ] = None,
    status: ItemStatus | None = None,
    kind: ItemKind | None = None,
    favorite: bool | None = None,
    tag: Annotated[str | None, Query(max_length=TAG_MAX, description="Tag name.")] = None,
    collection: Annotated[uuid.UUID | None, Query(description="Collection id.")] = None,
    date_from: Annotated[
        date | None, Query(alias="from", description="Saved on or after (local day).")
    ] = None,
    date_to: Annotated[
        date | None, Query(alias="to", description="Saved on or before (local day).")
    ] = None,
    limit: LimitParam = 50,
    cursor: CursorParam = None,
) -> Page[ItemSummaryOut]:
    """Saved items outside the trash: newest first, or best match first with `q`."""
    filters = service.ItemFilters(
        q=q,
        status=status,
        kind=kind,
        favorite=favorite,
        tag=tag,
        collection_id=collection,
        date_from=date_from,
        date_to=date_to,
    )
    return await service.list_items(
        session,
        auth.user.id,
        filters,
        timezone=auth.user.timezone,
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


# ------------------------------------------------------------------ tags


@router.get("/tags", response_model=list[TagOut])
async def list_tags(auth: CurrentAuth, session: SessionDep) -> list[TagOut]:
    return await tagging.list_tags(session, auth.user.id)


@router.patch("/tags/{tag_id}", response_model=TagOut)
async def rename_tag(
    tag_id: uuid.UUID, payload: TagUpdate, auth: CurrentAuth, session: SessionDep
) -> TagOut:
    """Rename a tag. Renaming to another tag's name merges them into that tag."""
    return await tagging.rename_tag(session, auth.user.id, tag_id, payload)


@router.delete("/tags/{tag_id}", status_code=204)
async def delete_tag(tag_id: uuid.UUID, auth: CurrentAuth, session: SessionDep) -> Response:
    """Remove the tag from every item; the items stay."""
    await tagging.delete_tag(session, auth.user.id, tag_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ collections


@router.get("/collections", response_model=list[CollectionOut])
async def list_collections(auth: CurrentAuth, session: SessionDep) -> list[CollectionOut]:
    return await collections.list_collections(session, auth.user.id)


@router.post("/collections", response_model=CollectionOut, status_code=201)
async def create_collection(
    payload: CollectionIn, auth: CurrentAuth, session: SessionDep
) -> CollectionOut:
    return await collections.create_collection(session, auth.user.id, payload)


@router.patch("/collections/{collection_id}", response_model=CollectionOut)
async def update_collection(
    collection_id: uuid.UUID, payload: CollectionUpdate, auth: CurrentAuth, session: SessionDep
) -> CollectionOut:
    return await collections.update_collection(session, auth.user.id, collection_id, payload)


@router.delete("/collections/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: uuid.UUID, auth: CurrentAuth, session: SessionDep
) -> Response:
    """Delete the collection; its items stay in the library without a collection."""
    await collections.delete_collection(session, auth.user.id, collection_id)
    return Response(status_code=204)
