"""Life Library: capture, browse, edit, trash and restore saved items.

Every query filters on the caller's `user_id`; items in the trash (`deleted_at` set) are
only reachable through the trash, restore and permanent-delete paths.
"""

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequest, Conflict, NotFound
from app.core.pagination import decode_cursor, next_cursor
from app.core.schemas import Page
from app.core.time import utc_now
from app.modules.identity import service as identity_service
from app.modules.library import urls
from app.modules.library.models import LibraryItem
from app.modules.library.schemas import (
    PREVIEW_LENGTH,
    CountsOut,
    ItemIn,
    ItemKind,
    ItemOut,
    ItemStatus,
    ItemSummaryOut,
    ItemUpdate,
)

URL_KEY_INDEX = "uq_library_items_user_url_key"
NOTE_TITLE_LENGTH = 120


# ------------------------------------------------------------------ helpers


async def _get_item(
    session: AsyncSession,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    in_trash: bool = False,
    lock: bool = False,
) -> LibraryItem:
    query = select(LibraryItem).where(LibraryItem.id == item_id, LibraryItem.user_id == user_id)
    query = query.where(
        LibraryItem.deleted_at.is_not(None) if in_trash else LibraryItem.deleted_at.is_(None)
    )
    item = await session.scalar(query.with_for_update() if lock else query)
    if item is None:
        raise NotFound("Item not found.")
    return item


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _first_line(text: str) -> str:
    """A note's default title: its first non-empty line, without Markdown heading marks."""
    for line in text.splitlines():
        line = " ".join(line.lstrip("#").split())
        if line:
            return _shorten(line, NOTE_TITLE_LENGTH)
    return "Untitled note"


def _preview(item: LibraryItem) -> str | None:
    text = item.excerpt or item.body
    return _shorten(" ".join(text.split()), PREVIEW_LENGTH) if text else None


def _summary(item: LibraryItem) -> ItemSummaryOut:
    fields = {n: getattr(item, n) for n in ItemSummaryOut.model_fields if n != "preview"}
    return ItemSummaryOut(**fields, preview=_preview(item))


def _out(item: LibraryItem) -> ItemOut:
    fields = {n: getattr(item, n) for n in ItemOut.model_fields if n != "preview"}
    return ItemOut(**fields, preview=_preview(item))


async def _live_duplicate(
    session: AsyncSession, user_id: uuid.UUID, url_key: str, *, exclude: uuid.UUID | None = None
) -> uuid.UUID | None:
    query = select(LibraryItem.id).where(
        LibraryItem.user_id == user_id,
        LibraryItem.url_key == url_key,
        LibraryItem.deleted_at.is_(None),
    )
    if exclude is not None:
        query = query.where(LibraryItem.id != exclude)
    return await session.scalar(query)


def _duplicate(existing_id: uuid.UUID) -> Conflict:
    return Conflict(
        "You already saved this link.", code="library_duplicate", existingId=str(existing_id)
    )


async def _ensure_not_saved(
    session: AsyncSession, user_id: uuid.UUID, url_key: str, *, exclude: uuid.UUID | None = None
) -> None:
    existing = await _live_duplicate(session, user_id, url_key, exclude=exclude)
    if existing is not None:
        raise _duplicate(existing)


def _is_url_key_violation(exc: IntegrityError) -> bool:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == URL_KEY_INDEX


async def _commit(session: AsyncSession, user_id: uuid.UUID, url_key: str | None) -> None:
    """Commit, turning a lost race on the duplicate index into the same 409 as the check."""
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if url_key is None or not _is_url_key_violation(exc):
            raise
        existing = await _live_duplicate(session, user_id, url_key)
        if existing is None:
            raise
        raise _duplicate(existing) from exc


def _apply_link(item: LibraryItem, saved: urls.SavedUrl) -> None:
    item.url = saved.url
    item.url_key = saved.key
    item.kind = saved.kind
    item.site_name = saved.host
    item.metadata_status = "none"
    item.fetched_at = None


def _audit(session: AsyncSession, item: LibraryItem, action: str, request: Request | None) -> None:
    # Kind only: titles and links are the user's content and stay out of the audit log.
    identity_service.audit_event(
        session,
        user_id=item.user_id,
        action=action,
        entity_type="library_item",
        entity_id=item.id,
        details={"kind": item.kind},
        request=request,
    )


# ------------------------------------------------------------------ capture and read


async def create_item(session: AsyncSession, user_id: uuid.UUID, data: ItemIn) -> ItemOut:
    item = LibraryItem(
        user_id=user_id,
        kind=data.kind or "note",  # always set by ItemIn's validator
        status=data.status,
        excerpt=data.excerpt,
        body=data.body,
        is_favorite=data.is_favorite,
    )
    if data.url:
        saved = urls.parse(data.url)
        if data.kind == "excerpt":
            item.url, item.site_name = saved.url, saved.host  # source only; not deduplicated
        else:
            await _ensure_not_saved(session, user_id, saved.key)
            _apply_link(item, saved)  # the server decides link vs video
    item.title = data.title or _default_title(item)
    session.add(item)
    await _commit(session, user_id, item.url_key)
    return _out(item)


def _default_title(item: LibraryItem) -> str:
    if item.kind == "note":
        return _first_line(item.body or "")
    if item.site_name:
        return item.site_name
    return _first_line(item.excerpt or "")


async def get_item(session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> ItemOut:
    return _out(await _get_item(session, user_id, item_id))


async def _page(
    session: AsyncSession, query: Select[LibraryItem], *, cursor: str | None, limit: int
) -> Page[ItemSummaryOut]:
    offset = decode_cursor(cursor)
    rows = list(await session.scalars(query.offset(offset).limit(limit + 1)))
    return Page[ItemSummaryOut](
        items=[_summary(i) for i in rows[:limit]],
        next_cursor=next_cursor(offset, limit, len(rows)),
    )


async def list_items(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: ItemStatus | None = None,
    kind: ItemKind | None = None,
    favorite: bool | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> Page[ItemSummaryOut]:
    """Items outside the trash, newest first."""
    query = select(LibraryItem).where(
        LibraryItem.user_id == user_id, LibraryItem.deleted_at.is_(None)
    )
    if status is not None:
        query = query.where(LibraryItem.status == status)
    if kind is not None:
        query = query.where(LibraryItem.kind == kind)
    if favorite is not None:
        query = query.where(LibraryItem.is_favorite.is_(favorite))
    query = query.order_by(LibraryItem.created_at.desc(), LibraryItem.id.desc())
    return await _page(session, query, cursor=cursor, limit=limit)


async def list_trash(
    session: AsyncSession, user_id: uuid.UUID, *, cursor: str | None = None, limit: int = 50
) -> Page[ItemSummaryOut]:
    query = (
        select(LibraryItem)
        .where(LibraryItem.user_id == user_id, LibraryItem.deleted_at.is_not(None))
        .order_by(LibraryItem.deleted_at.desc(), LibraryItem.id.desc())
    )
    return await _page(session, query, cursor=cursor, limit=limit)


async def counts(session: AsyncSession, user_id: uuid.UUID) -> CountsOut:
    live = LibraryItem.deleted_at.is_(None)
    row = (
        await session.execute(
            select(
                *(
                    func.count().filter(live, LibraryItem.status == s).label(s)
                    for s in ("inbox", "to_read", "reading", "archived")
                ),
                func.count().filter(live, LibraryItem.is_favorite).label("favorites"),
                func.count().filter(LibraryItem.deleted_at.is_not(None)).label("trash"),
            ).where(LibraryItem.user_id == user_id)
        )
    ).one()
    return CountsOut(**row._mapping)


# ------------------------------------------------------------------ edit


async def update_item(
    session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID, data: ItemUpdate
) -> ItemOut:
    item = await _get_item(session, user_id, item_id, lock=True)
    changes: dict[str, Any] = data.model_dump(exclude_unset=True, by_alias=False)
    if changes.pop("version") != item.version:
        raise Conflict("This item changed since you loaded it.", code="version_conflict")

    if "url" in changes:
        await _change_url(session, item, changes.pop("url"))
    if changes.get("excerpt", "keep") is None and item.kind == "excerpt":
        raise BadRequest("An excerpt needs its text.", code="library_excerpt_required")
    for field in ("title", "status", "is_favorite"):
        if changes.get(field) is not None:  # these cannot be cleared
            setattr(item, field, changes[field])
    for field in ("excerpt", "body"):
        if field in changes:
            setattr(item, field, changes[field])

    item.version += 1
    await _commit(session, user_id, item.url_key)
    return _out(item)


async def _change_url(session: AsyncSession, item: LibraryItem, raw: str | None) -> None:
    if item.kind == "note":
        raise BadRequest("A note cannot have a link.", code="library_note_url")
    if item.kind == "excerpt":
        saved = urls.parse(raw) if raw else None
        item.url = saved.url if saved else None
        item.site_name = saved.host if saved else None
        return
    if not raw:
        raise BadRequest("A link needs a web address.", code="library_url_required")
    saved = urls.parse(raw)
    if saved.key != item.url_key:
        await _ensure_not_saved(session, item.user_id, saved.key, exclude=item.id)
        _apply_link(item, saved)
    else:
        item.url = saved.url  # same page, different spelling; keep fetched details


# ------------------------------------------------------------------ trash


async def delete_item(
    session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID, *, request: Request | None
) -> None:
    """Move to the trash. Restorable until deleted permanently."""
    item = await _get_item(session, user_id, item_id, lock=True)
    item.deleted_at = utc_now()
    item.version += 1
    _audit(session, item, "library.item_deleted", request)
    await session.commit()


async def restore_item(
    session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID, *, request: Request | None
) -> ItemOut:
    item = await _get_item(session, user_id, item_id, in_trash=True, lock=True)
    if item.url_key is not None:
        await _ensure_not_saved(session, user_id, item.url_key)
    item.deleted_at = None
    item.version += 1
    _audit(session, item, "library.item_restored", request)
    await _commit(session, user_id, item.url_key)
    return _out(item)


async def purge_item(
    session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID, *, request: Request | None
) -> None:
    """Delete for good. Only items already in the trash, so one click never destroys data."""
    item = await session.scalar(
        select(LibraryItem)
        .where(LibraryItem.id == item_id, LibraryItem.user_id == user_id)
        .with_for_update()
    )
    if item is None:
        raise NotFound("Item not found.")
    if item.deleted_at is None:
        raise Conflict("Move the item to the trash first.", code="library_not_in_trash")
    _audit(session, item, "library.item_purged", request)
    await session.delete(item)
    await session.commit()
