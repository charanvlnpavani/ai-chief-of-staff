"""Opaque pagination cursors.

Cursors are opaque to clients, so the encoding can move from offsets to keyset values
later without changing the API contract.
"""

import base64
import json
from typing import Annotated

from fastapi import Query

from app.core.errors import BadRequest

LimitParam = Annotated[int, Query(ge=1, le=200, description="Maximum items to return.")]
CursorParam = Annotated[str | None, Query(description="Cursor from a previous page.")]


def encode_cursor(offset: int) -> str:
    raw = json.dumps({"o": offset}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        offset = int(data["o"])
    except (
        ValueError,
        KeyError,
        TypeError,
    ) as exc:  # binascii.Error/JSONDecodeError are ValueErrors
        raise BadRequest("Invalid pagination cursor.", code="invalid_cursor") from exc
    if offset < 0:
        raise BadRequest("Invalid pagination cursor.", code="invalid_cursor")
    return offset


def next_cursor(offset: int, limit: int, fetched: int) -> str | None:
    """`fetched` is the row count read with `limit + 1`; more rows exist if it exceeds `limit`."""
    return encode_cursor(offset + limit) if fetched > limit else None
