"""Tags: get-or-create by name, attach to items, list with counts, rename (merging) and delete.

Tags are matched case-insensitively through `name_key`; the first spelling used is kept
for display.
"""

import uuid
from collections import defaultdict

from sqlalchemy import delete, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.core.ids import uuid7
from app.core.time import utc_now
from app.modules.library.models import LibraryItem, LibraryItemTag, Tag
from app.modules.library.schemas import TagOut, TagUpdate, tag_key


async def ensure_tags(session: AsyncSession, user_id: uuid.UUID, names: list[str]) -> list[Tag]:
    """The user's tags with these names, creating missing ones. Safe under concurrency:
    a tag created by a parallel request is picked up instead of failing."""
    if not names:
        return []
    keys = {tag_key(n): n for n in names}
    now = utc_now()
    await session.execute(
        insert(Tag)
        .values(
            [
                # Core inserts skip ORM defaults, so ids and timestamps are set here.
                {
                    "id": uuid7(),
                    "user_id": user_id,
                    "name": name,
                    "name_key": key,
                    "created_at": now,
                }
                for key, name in keys.items()
            ]
        )
        .on_conflict_do_nothing(index_elements=["user_id", "name_key"])
    )
    return list(
        await session.scalars(
            select(Tag).where(Tag.user_id == user_id, Tag.name_key.in_(list(keys)))
        )
    )


async def set_item_tags(
    session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID, names: list[str]
) -> None:
    """Replace the item's tags with exactly these."""
    tags = await ensure_tags(session, user_id, names)
    await session.execute(delete(LibraryItemTag).where(LibraryItemTag.item_id == item_id))
    if tags:
        await session.execute(
            insert(LibraryItemTag).values(
                [{"item_id": item_id, "tag_id": t.id, "user_id": user_id} for t in tags]
            )
        )


async def tags_for(session: AsyncSession, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """Tag names per item, alphabetical."""
    result: dict[uuid.UUID, list[str]] = defaultdict(list)
    if item_ids:
        rows = await session.execute(
            select(LibraryItemTag.item_id, Tag.name)
            .join(Tag, Tag.id == LibraryItemTag.tag_id)
            .where(LibraryItemTag.item_id.in_(item_ids))
            .order_by(Tag.name_key)
        )
        for item_id, name in rows.all():
            result[item_id].append(name)
    return result


async def _get_tag(session: AsyncSession, user_id: uuid.UUID, tag_id: uuid.UUID) -> Tag:
    tag = await session.scalar(select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id))
    if tag is None:
        raise NotFound("Tag not found.")
    return tag


async def list_tags(session: AsyncSession, user_id: uuid.UUID) -> list[TagOut]:
    live_items = (
        select(LibraryItemTag.tag_id, func.count().label("n"))
        .join(LibraryItem, LibraryItem.id == LibraryItemTag.item_id)
        .where(LibraryItemTag.user_id == user_id, LibraryItem.deleted_at.is_(None))
        .group_by(LibraryItemTag.tag_id)
        .subquery()
    )
    rows = await session.execute(
        select(Tag, func.coalesce(live_items.c.n, 0))
        .outerjoin(live_items, live_items.c.tag_id == Tag.id)
        .where(Tag.user_id == user_id)
        .order_by(Tag.name_key)
    )
    return [TagOut(id=t.id, name=t.name, item_count=n) for t, n in rows.all()]


async def rename_tag(
    session: AsyncSession, user_id: uuid.UUID, tag_id: uuid.UUID, data: TagUpdate
) -> TagOut:
    """Rename. If another tag already has the new name, its items gain this tag's items
    and this tag is removed, so the result is one tag under the new name."""
    tag = await _get_tag(session, user_id, tag_id)
    new_key = tag_key(data.name)
    target = await session.scalar(
        select(Tag).where(Tag.user_id == user_id, Tag.name_key == new_key, Tag.id != tag.id)
    )
    if target is None:
        tag.name, tag.name_key = data.name, new_key
        result_id = tag.id
    else:
        moved = select(LibraryItemTag.item_id, literal(target.id), LibraryItemTag.user_id).where(
            LibraryItemTag.tag_id == tag.id
        )
        await session.execute(
            insert(LibraryItemTag)
            .from_select(["item_id", "tag_id", "user_id"], moved)
            .on_conflict_do_nothing()
        )
        await session.delete(tag)  # its remaining links go with it (ON DELETE CASCADE)
        result_id = target.id
    await session.commit()
    return next(t for t in await list_tags(session, user_id) if t.id == result_id)


async def delete_tag(session: AsyncSession, user_id: uuid.UUID, tag_id: uuid.UUID) -> None:
    """Remove the tag from every item. The items themselves are untouched."""
    await session.delete(await _get_tag(session, user_id, tag_id))
    await session.commit()
