"""Link metadata fetching: what is read, what is refused, and that failures stay quiet."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx
import pytest

from app.modules.library import metadata
from app.modules.library.metadata import Metadata, fetch, parse_html
from tests.core.test_netguard import PUBLIC_V4, fake_dns

PAGE = "https://blog.example.test/post"


def html_response(body: str, *, content_type: str = "text/html; charset=utf-8") -> httpx.Response:
    return httpx.Response(200, headers={"content-type": content_type}, content=body.encode())


Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


def recorder(handler: Handler) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        result = handler(request)
        return result if isinstance(result, httpx.Response) else await result

    return httpx.MockTransport(handle), seen


@pytest.fixture(autouse=True)
def dns(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_dns(
        monkeypatch,
        {
            "blog.example.test": [PUBLIC_V4],
            "other.example.test": [PUBLIC_V4],
            "www.youtube.com": [PUBLIC_V4],
            "internal.example.test": ["10.0.0.9"],
        },
    )


# ------------------------------------------------------------------ parsing


def test_open_graph_title_wins_and_entities_are_decoded() -> None:
    meta = parse_html(
        "<html><head><title>Fallback</title>"
        '<meta property="og:title" content="Caf&eacute; &amp; Code">'
        '<meta property="og:site_name" content="The Blog">'
        '<meta name="author" content="Ana\x00 Lopez">'
        "</head><body><title>not this</title></body></html>"
    )
    assert meta == Metadata(title="Café & Code", site_name="The Blog", author="Ana Lopez")


def test_title_tag_is_the_fallback_and_whitespace_is_collapsed() -> None:
    meta = parse_html("<title>\n  Hello\n\tworld  </title>")
    assert meta == Metadata(title="Hello world", site_name=None, author=None)


def test_head_fields_after_the_body_starts_are_ignored() -> None:
    meta = parse_html('<body><meta property="og:title" content="sneaky"><title>x</title>')
    assert meta == Metadata(title=None, site_name=None, author=None)


def test_long_values_are_capped() -> None:
    meta = parse_html(f"<title>{'t' * 400}</title>")
    assert meta.title is not None
    assert len(meta.title) == 300
    assert meta.title.endswith("…")


# ------------------------------------------------------------------ fetching pages


async def test_fetches_a_page_title() -> None:
    transport, seen = recorder(lambda r: html_response("<title>A post</title>"))
    assert await fetch(PAGE, "link", transport=transport) == Metadata("A post", None, None)
    (request,) = seen
    assert request.headers["host"] == "blog.example.test"
    assert "PersonalOS" in request.headers["user-agent"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, headers={"content-type": "text/html"}, content=b"<title>x</title>"),
        httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF"),
        httpx.Response(200, headers={"content-type": "text/html"}, content=b"<p>no title</p>"),
    ],
)
async def test_unusable_responses_return_nothing(response: httpx.Response) -> None:
    transport, _ = recorder(lambda r: response)
    assert await fetch(PAGE, "link", transport=transport) is None


async def test_only_the_first_512_kb_is_read() -> None:
    padding = "<!--" + "x" * metadata.MAX_BYTES + "-->"
    transport, _ = recorder(lambda r: html_response(padding + "<title>too late</title>"))
    assert await fetch(PAGE, "link", transport=transport) is None


async def test_declared_charset_is_used_and_unknown_ones_fall_back() -> None:
    latin = httpx.Response(
        200,
        headers={"content-type": "text/html; charset=iso-8859-1"},
        content="<title>Ni\xf1o</title>".encode("latin-1"),
    )
    transport, _ = recorder(lambda r: latin)
    assert (await fetch(PAGE, "link", transport=transport)).title == "Niño"  # type: ignore[union-attr]
    bogus = html_response("<title>ok</title>", content_type="text/html; charset=nope")
    transport, _ = recorder(lambda r: bogus)
    assert (await fetch(PAGE, "link", transport=transport)).title == "ok"  # type: ignore[union-attr]


async def test_redirects_are_followed_up_to_three_hops() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        hop = int(request.url.params.get("hop", "0"))
        if hop < 3:
            return httpx.Response(302, headers={"location": f"/post?hop={hop + 1}"})
        return html_response("<title>arrived</title>")

    transport, seen = recorder(handler)
    assert (await fetch(PAGE, "link", transport=transport)).title == "arrived"  # type: ignore[union-attr]
    assert len(seen) == 4

    endless, seen = recorder(lambda r: httpx.Response(302, headers={"location": "/again"}))
    assert await fetch(PAGE, "link", transport=endless) is None
    assert len(seen) == 4  # the first request plus three redirects, then it stops


async def test_redirects_to_private_addresses_are_refused() -> None:
    transport, seen = recorder(
        lambda r: httpx.Response(302, headers={"location": "http://internal.example.test/admin"})
    )
    assert await fetch(PAGE, "link", transport=transport) is None
    assert [r.url.host for r in seen] == [PUBLIC_V4]  # never connected to the private host


async def test_private_links_are_never_fetched() -> None:
    transport, seen = recorder(lambda r: html_response("<title>internal</title>"))
    assert await fetch("http://internal.example.test/", "link", transport=transport) is None
    assert await fetch("http://127.0.0.1/", "link", transport=transport) is None
    assert seen == []


async def test_only_web_ports_are_fetched() -> None:
    transport, seen = recorder(lambda r: html_response("<title>x</title>"))
    assert await fetch("https://blog.example.test:8443/", "link", transport=transport) is None
    assert seen == []
    to_odd_port, seen = recorder(
        lambda r: httpx.Response(302, headers={"location": "http://other.example.test:6379/"})
    )
    assert await fetch(PAGE, "link", transport=to_odd_port) is None
    assert len(seen) == 1


async def test_slow_sites_give_up_within_the_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metadata, "BUDGET_SECONDS", 0.05)

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return html_response("<title>late</title>")

    transport, _ = recorder(slow)
    started = asyncio.get_running_loop().time()
    assert await fetch(PAGE, "link", transport=transport) is None
    assert asyncio.get_running_loop().time() - started < 0.5


# ------------------------------------------------------------------ YouTube


async def test_youtube_uses_oembed() -> None:
    video = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    transport, seen = recorder(
        lambda r: httpx.Response(200, json={"title": "A talk", "author_name": "A channel"})
    )
    assert await fetch(video, "video", transport=transport) == Metadata(
        "A talk", "YouTube", "A channel"
    )
    (request,) = seen
    assert request.headers["host"] == "www.youtube.com"
    assert request.url.path == "/oembed"
    assert request.url.params["url"] == video


async def test_youtube_errors_return_nothing() -> None:
    for response in (httpx.Response(404), httpx.Response(200, content=b"not json")):
        transport, _ = recorder(lambda r, resp=response: resp)  # type: ignore[misc]
        assert (
            await fetch("https://www.youtube.com/watch?v=x", "video", transport=transport) is None
        )
