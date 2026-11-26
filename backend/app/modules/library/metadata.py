"""Fetch a saved link's title, site name and author. Nothing else from the page is kept.

- YouTube: the public oEmbed endpoint (title and channel). No scraping, no transcript.
- Other pages: the first 512 KB of HTML, reading `<title>`, `og:title`, `og:site_name`
  and `author` meta tags.

Every request (and every redirect hop) goes through `netguard.PublicOnlyTransport`, so a
saved link can never make the server call a private or local address. Fetched strings are
untrusted: they are cleaned, length-capped and only ever shown as text.
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit

import httpx

from app.core import netguard

logger = logging.getLogger(__name__)

BUDGET_SECONDS = 5.0
MAX_BYTES = 512 * 1024
MAX_REDIRECTS = 3
ALLOWED_PORTS = {None, 80, 443}
HTML_TYPES = ("text/html", "application/xhtml+xml")
OEMBED = "https://www.youtube.com/oembed"
USER_AGENT = "Mozilla/5.0 (compatible; PersonalOS-LinkPreview/1.0)"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class Metadata:
    title: str | None
    site_name: str | None
    author: str | None


MetadataFetcher = Callable[[str, str], Awaitable[Metadata | None]]
"""(url, kind) -> metadata, or None when nothing usable could be fetched."""


def _clean(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    text = " ".join(_CONTROL.sub(" ", value).split())
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class _HeadParser(HTMLParser):
    """Collects the few head fields we use; stops caring after </head> or <body>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self._in_title = False
        self.done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.done:
            return
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            values = {k.lower(): v for k, v in attrs if v is not None}
            name = (values.get("property") or values.get("name") or "").lower()
            if name in ("og:title", "og:site_name", "author") and "content" in values:
                self.meta.setdefault(name, values["content"])
        elif tag == "body":
            self.done = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "head":
            self.done = True

    def handle_data(self, data: str) -> None:
        if self._in_title and not self.done:
            self.title_parts.append(data)


def parse_html(text: str) -> Metadata:
    parser = _HeadParser()
    parser.feed(text)
    title = parser.meta.get("og:title") or "".join(parser.title_parts)
    return Metadata(
        title=_clean(title, 300),
        site_name=_clean(parser.meta.get("og:site_name"), 200),
        author=_clean(parser.meta.get("author"), 200),
    )


async def _check_hop(request: httpx.Request) -> None:
    """Event hook run before every request, including redirects."""
    if request.url.scheme not in ("http", "https") or request.url.port not in ALLOWED_PORTS:
        raise netguard.BlockedAddress(f"refusing {request.url.scheme} port {request.url.port}")


def make_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=netguard.PublicOnlyTransport(transport),
        timeout=httpx.Timeout(BUDGET_SECONDS),
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
        trust_env=False,  # an environment proxy would bypass the address guard
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        event_hooks={"request": [_check_hop]},
    )


async def _read_capped(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        chunks.append(chunk)
        size += len(chunk)
        if size >= MAX_BYTES:
            break
    return b"".join(chunks)[:MAX_BYTES]


async def _youtube(client: httpx.AsyncClient, url: str) -> Metadata | None:
    response = await client.get(f"{OEMBED}?{urlencode({'url': url, 'format': 'json'})}")
    if response.status_code != 200:
        return None
    data = response.json()
    if not isinstance(data, dict):
        return None
    return Metadata(
        title=_clean(str(data.get("title") or ""), 300),
        site_name="YouTube",
        author=_clean(str(data.get("author_name") or ""), 200),
    )


async def _page(client: httpx.AsyncClient, url: str) -> Metadata | None:
    async with client.stream("GET", url) as response:
        if response.status_code != 200:
            return None
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type not in HTML_TYPES:
            return None
        raw = await _read_capped(response)
        encoding = response.charset_encoding or "utf-8"
    try:
        text = raw.decode(encoding, errors="replace")
    except LookupError:  # an unknown charset name from the server
        text = raw.decode("utf-8", errors="replace")
    return parse_html(text)


async def fetch(
    url: str, kind: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> Metadata | None:
    """Best effort within `BUDGET_SECONDS`. Any failure (blocked address, timeout, bad
    response, unparsable page) returns None; the caller falls back to the site name."""
    if urlsplit(url).port not in ALLOWED_PORTS:
        return None
    try:
        async with asyncio.timeout(BUDGET_SECONDS), make_client(transport) as client:
            result = await (_youtube(client, url) if kind == "video" else _page(client, url))
    except (httpx.HTTPError, TimeoutError, ValueError) as exc:
        # Host only: the full link is the user's content and stays out of the logs.
        logger.info(
            "library_metadata_failed",
            extra={"host": urlsplit(url).hostname, "error": type(exc).__name__},
        )
        return None
    if result is None or not (result.title or result.site_name or result.author):
        return None
    return result


async def fetch_live(url: str, kind: str) -> Metadata | None:
    return await fetch(url, kind)


def get_metadata_fetcher() -> MetadataFetcher:
    """Dependency so tests can replace the network."""
    return fetch_live
