import re
import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, model_validator

from app.core.schemas import APIModel

ItemKind = Literal["note", "link", "video", "excerpt"]
ItemStatus = Literal["inbox", "to_read", "reading", "archived"]
MetadataStatus = Literal["none", "fetched", "failed"]

TITLE_MAX = 300
EXCERPT_MAX = 10_000
BODY_MAX = 100_000
PREVIEW_LENGTH = 240

# C0 controls except tab, newline and carriage return. Postgres rejects NUL in text, and
# the others only ever arrive by accident (or to hide something from a reader).
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = _CONTROL.sub("", value).replace("\r\n", "\n").strip()
    return value or None


def _clean_line(value: str | None) -> str | None:
    """Single-line text: control characters removed, runs of whitespace collapsed."""
    if value is None:
        return None
    value = " ".join(_CONTROL.sub("", value).split())
    return value or None


Title = Annotated[str | None, Field(max_length=TITLE_MAX), AfterValidator(_clean_line)]
Excerpt = Annotated[str | None, Field(max_length=EXCERPT_MAX), AfterValidator(_clean_text)]
Body = Annotated[str | None, Field(max_length=BODY_MAX), AfterValidator(_clean_text)]
Url = Annotated[str | None, Field(max_length=2048)]


class ItemIn(APIModel):
    """Save something. `kind` may be left out: a URL makes a link (or a video for YouTube),
    text alone makes a note. A link's title defaults to its site; a note's to its first line."""

    kind: ItemKind | None = None
    title: Title = None
    url: Url = None
    excerpt: Excerpt = None
    body: Body = None
    status: ItemStatus = "inbox"
    is_favorite: bool = False

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.kind is None:
            self.kind = "link" if self.url else "note"
        if self.kind == "note":
            if self.url:
                raise ValueError("A note cannot have a link; save it as a link or an excerpt.")
            if not (self.title or self.body):
                raise ValueError("Write a title or some text for the note.")
        elif self.kind in ("link", "video") and not self.url:
            raise ValueError("A link needs a web address.")
        elif self.kind == "excerpt" and not self.excerpt:
            raise ValueError("Paste the excerpt you want to keep.")
        return self


class ItemUpdate(APIModel):
    """Change an item. Send `version` from the item you loaded; a stale one gets 409."""

    version: int = Field(ge=1)
    title: Title = None
    url: Url = None
    excerpt: Excerpt = None
    body: Body = None
    status: ItemStatus | None = None
    is_favorite: bool | None = None


class ItemSummaryOut(APIModel):
    """A list row: everything but the full excerpt and note, which can be long."""

    id: uuid.UUID
    kind: ItemKind
    status: ItemStatus
    title: str
    url: str | None
    site_name: str | None
    preview: str | None = Field(
        description="Start of the excerpt, or of the note when there is no excerpt."
    )
    is_favorite: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    version: int


class ItemOut(ItemSummaryOut):
    author: str | None
    excerpt: str | None = Field(description="Text the user saved from the source.")
    body: str | None = Field(description="The user's own note.")
    metadata_status: MetadataStatus
    fetched_at: datetime | None


class CountsOut(APIModel):
    inbox: int
    to_read: int
    reading: int
    archived: int
    favorites: int
    trash: int
