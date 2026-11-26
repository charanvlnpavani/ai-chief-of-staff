"""Saved-link handling: validation, the stored form, the duplicate key and the item kind.

Pure functions, no I/O. Saving a URL never fetches it; metadata fetching is separate and
goes through `app.core.netguard`.
"""

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import SplitResult, parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.errors import BadRequest

MAX_URL_LENGTH = 2048
TRACKING_PARAMS = frozenset({"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid"})
YOUTUBE_HOSTS = frozenset({"youtube.com", "m.youtube.com", "music.youtube.com"})
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass(frozen=True, slots=True)
class SavedUrl:
    url: str  # what is stored and shown: the user's URL with scheme and host lower-cased
    key: str  # normalised form used only to detect duplicates
    host: str  # display host, without "www."
    kind: Literal["link", "video"]


def _invalid(message: str = "Enter a full web address such as https://example.com.") -> BadRequest:
    return BadRequest(message, code="library_url_invalid")


def _youtube_id(host: str, path: str, query: dict[str, str]) -> str | None:
    if host == "youtu.be":
        candidate = path.strip("/").split("/")[0]
    elif host in YOUTUBE_HOSTS:
        parts = [p for p in path.split("/") if p]
        if parts[:1] == ["watch"]:
            candidate = query.get("v", "")
        elif len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v"):
            candidate = parts[1]
        else:
            return None
    else:
        return None
    return candidate if YOUTUBE_ID.match(candidate) else None


def _split(raw: str) -> tuple[SplitResult, str, str, int | None]:
    """Validate and split; returns (parts, scheme, ascii host, explicit port)."""
    value = raw.strip()
    if not value or any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise _invalid()
    if "://" not in value:
        value = "https://" + value  # "example.com/post"; "javascript:x" then fails below
    if len(value) > MAX_URL_LENGTH:
        raise _invalid("That web address is too long.")
    try:
        parts = urlsplit(value)
        port = parts.port  # raises ValueError for a non-numeric or out-of-range port
    except ValueError as exc:
        raise _invalid() from exc
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        raise _invalid()
    if parts.username is not None or parts.password is not None:
        raise _invalid("Remove the user name or password from the web address.")
    try:
        host = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise _invalid() from exc
    if not host:
        raise _invalid()
    return parts, scheme, host, port


def _netloc(host: str, port: int | None) -> str:
    bracketed = f"[{host}]" if ":" in host else host  # IPv6 literal
    return bracketed if port is None else f"{bracketed}:{port}"


def _dedup_key(host: str, port: int | None, path: str, pairs: list[tuple[str, str]]) -> str:
    """Folds http/https, "www." and default ports; drops the fragment, tracking parameters
    and a trailing slash; sorts the remaining parameters."""
    kept = sorted(
        (k, v)
        for k, v in pairs
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    )
    return urlunsplit(("https", _netloc(host, port), path.rstrip("/"), urlencode(kept), ""))


def parse(raw: str) -> SavedUrl:
    """Validate a URL the user wants to save. A missing scheme means https.

    Raises `BadRequest(library_url_invalid)` for anything that is not an http(s) address,
    carries credentials, or is too long.
    """
    parts, scheme, host, port = _split(raw)
    if port == (443 if scheme == "https" else 80):
        port = None
    # Shown as typed (lower-cased, so "bücher.de" stays readable); the key uses the
    # ASCII (IDNA) form so both spellings of one domain match.
    display = (parts.hostname or host).lower().rstrip(".")
    url = urlunsplit((scheme, _netloc(display, port), parts.path, parts.query, parts.fragment))
    bare = host.removeprefix("www.")
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    video_id = _youtube_id(bare, parts.path, dict(pairs))
    if video_id is not None:
        return SavedUrl(url, f"https://youtube.com/watch?v={video_id}", "youtube.com", "video")
    key = _dedup_key(bare, port, parts.path, pairs)
    return SavedUrl(url, key, display.removeprefix("www."), "link")
