"""Life Library: saved notes, links, videos and excerpts, with collections and tags."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Computed, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, OwnedMixin, SoftDeleteMixin, TimestampMixin, VersionMixin
from app.core.time import utc_now

# Weighted so a title match ranks above an excerpt match, and an excerpt above the note body.
# The `simple` configuration does no stemming, so it behaves the same for every language.
SEARCH_VECTOR = (
    "setweight(to_tsvector('simple'::regconfig, coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('simple'::regconfig, coalesce(excerpt, '')), 'B') || "
    "setweight(to_tsvector('simple'::regconfig, coalesce(body, '')), 'C')"
)


class LibraryCollection(IdMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, OwnedMixin, Base):
    """A folder: each item lives in at most one collection. Tags give many-to-many."""

    __tablename__ = "library_collections"

    name: Mapped[str] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(default=0)

    __table_args__ = (
        Index(
            "uq_library_collections_user_name",
            "user_id",
            func.lower(text("name")),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class LibraryItem(IdMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, OwnedMixin, Base):
    """One saved thing. `url` is what the user saved; `url_key` is its normalised form,
    used only to find duplicate links and videos. `excerpt` is text the user pasted from
    the source and `body` is the user's own note, kept apart so the two are never confused."""

    __tablename__ = "library_items"

    kind: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="inbox")
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(2048), default=None)
    url_key: Mapped[str | None] = mapped_column(String(2048), default=None)
    site_name: Mapped[str | None] = mapped_column(String(200), default=None)
    author: Mapped[str | None] = mapped_column(String(200), default=None)
    excerpt: Mapped[str | None] = mapped_column(Text, default=None)
    body: Mapped[str | None] = mapped_column(Text, default=None)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("library_collections.id", ondelete="SET NULL"), default=None
    )
    is_favorite: Mapped[bool] = mapped_column(default=False)
    metadata_status: Mapped[str] = mapped_column(String(10), default="none")
    fetched_at: Mapped[datetime | None] = mapped_column(default=None)
    search_tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed(SEARCH_VECTOR, persisted=True), deferred=True
    )

    __table_args__ = (
        CheckConstraint("kind IN ('note', 'link', 'video', 'excerpt')", name="kind_valid"),
        CheckConstraint(
            "status IN ('inbox', 'to_read', 'reading', 'archived')", name="status_valid"
        ),
        CheckConstraint(
            "metadata_status IN ('none', 'fetched', 'failed')", name="metadata_status_valid"
        ),
        # Notes never have a link; links and videos always do; an excerpt's source is optional.
        CheckConstraint("kind <> 'note' OR url IS NULL", name="note_has_no_url"),
        CheckConstraint("kind NOT IN ('link', 'video') OR url IS NOT NULL", name="link_has_url"),
        CheckConstraint("kind <> 'excerpt' OR excerpt IS NOT NULL", name="excerpt_has_text"),
        # Only links and videos are deduplicated: several excerpts may share one source.
        CheckConstraint(
            "(kind IN ('link', 'video')) = (url_key IS NOT NULL)", name="url_key_for_links"
        ),
        CheckConstraint("char_length(excerpt) <= 10000", name="excerpt_length"),
        CheckConstraint("char_length(body) <= 100000", name="body_length"),
        Index(
            "uq_library_items_user_url_key",
            "user_id",
            "url_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND url_key IS NOT NULL"),
        ),
        Index(
            "ix_library_items_user_status_created",
            "user_id",
            "status",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_library_items_user_deleted",
            "user_id",
            text("deleted_at DESC"),
            postgresql_where=text("deleted_at IS NOT NULL"),
        ),
        Index("ix_library_items_search", "search_tsv", postgresql_using="gin"),
        Index("ix_library_items_collection", "collection_id"),
    )


class Tag(IdMixin, OwnedMixin, Base):
    """A user's tag. Generic so other modules can tag their records later without a second
    tag system; `name_key` (trimmed, lower-case) makes "Python" and "python " one tag."""

    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(40))
    name_key: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    __table_args__ = (Index("uq_tags_user_name_key", "user_id", "name_key", unique=True),)


class LibraryItemTag(OwnedMixin, Base):
    __tablename__ = "library_item_tags"

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("library_items.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_library_item_tags_tag", "tag_id"),)
