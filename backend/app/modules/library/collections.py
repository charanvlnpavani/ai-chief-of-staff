"""Collections: one folder per item. Names are unique per user, ignoring case."""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.core.time import utc_now
from app.modules.library.models import LibraryCollection, LibraryItem
from app.modules.library.schemas import CollectionIn, CollectionOut, CollectionUpdate

NAME_INDEX = "uq_library_collections_user_name"


async def get_live(
    session: AsyncSession, user_id: uuid.UUID, collection_id: uuid.UUID, *, lock: bool = False
) -> LibraryCollection:
    query = select(LibraryCollection).where(
        LibraryCollection.id == collection_id,
        LibraryCollection.user_id == user_id,
        LibraryCollection.deleted_at.is_(None),
    )
    collection = await session.scalar(query.with_for_update() if lock else query)
    if collection is None:
        raise NotFound("Collection not found.", code="library_collection_not_found")
    return collection


def _name_taken() -> Conflict:
    return Conflict(
        "You already have a collection with that name.", code="library_collection_exists"
    )


async def _ensure_name_free(
    session: AsyncSession, user_id: uuid.UUID, name: str, *, exclude: uuid.UUID | None = None
) -> None:
    query = select(LibraryCollection.id).where(
        LibraryCollection.user_id == user_id,
        func.lower(LibraryCollection.name) == name.lower(),
        LibraryCollection.deleted_at.is_(None),
    )
    if exclude is not None:
        query = query.where(LibraryCollection.id != exclude)
    if await session.scalar(query) is not None:
        raise _name_taken()


async def _commit(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:  # a parallel request took the name after our check
        await session.rollback()
        diag = getattr(exc.orig, "diag", None)
        if getattr(diag, "constraint_name", None) == NAME_INDEX:
            raise _name_taken() from exc
        raise


async def _out(session: AsyncSession, collection: LibraryCollection) -> CollectionOut:
    return next(
        c for c in await list_collections(session, collection.user_id) if c.id == collection.id
    )


async def list_collections(session: AsyncSession, user_id: uuid.UUID) -> list[CollectionOut]:
    counts = (
        select(LibraryItem.collection_id, func.count().label("n"))
        .where(LibraryItem.user_id == user_id, LibraryItem.deleted_at.is_(None))
        .group_by(LibraryItem.collection_id)
        .subquery()
    )
    rows = await session.execute(
        select(LibraryCollection, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.collection_id == LibraryCollection.id)
        .where(LibraryCollection.user_id == user_id, LibraryCollection.deleted_at.is_(None))
        .order_by(LibraryCollection.sort_order, func.lower(LibraryCollection.name))
    )
    return [
        CollectionOut(
            id=c.id, name=c.name, sort_order=c.sort_order, item_count=n, version=c.version
        )
        for c, n in rows.all()
    ]


async def create_collection(
    session: AsyncSession, user_id: uuid.UUID, data: CollectionIn
) -> CollectionOut:
    await _ensure_name_free(session, user_id, data.name)
    collection = LibraryCollection(user_id=user_id, name=data.name, sort_order=data.sort_order)
    session.add(collection)
    await _commit(session)
    return await _out(session, collection)


async def update_collection(
    session: AsyncSession, user_id: uuid.UUID, collection_id: uuid.UUID, data: CollectionUpdate
) -> CollectionOut:
    collection = await get_live(session, user_id, collection_id, lock=True)
    if data.version != collection.version:
        raise Conflict("This collection changed since you loaded it.", code="version_conflict")
    if data.name is not None and data.name != collection.name:
        await _ensure_name_free(session, user_id, data.name, exclude=collection.id)
        collection.name = data.name
    if data.sort_order is not None:
        collection.sort_order = data.sort_order
    collection.version += 1
    await _commit(session)
    return await _out(session, collection)


async def delete_collection(
    session: AsyncSession, user_id: uuid.UUID, collection_id: uuid.UUID
) -> None:
    """Remove the folder; its items stay in the library, uncollected. Items in the trash
    are released too, so restoring one never points at a deleted collection."""
    collection = await get_live(session, user_id, collection_id, lock=True)
    collection.deleted_at = utc_now()
    collection.version += 1
    await session.execute(
        update(LibraryItem)
        .where(LibraryItem.user_id == user_id, LibraryItem.collection_id == collection.id)
        .values(collection_id=None, version=LibraryItem.version + 1, updated_at=utc_now())
    )
    await session.commit()
