"""Link details on save and on refresh, through the API (network replaced by FakeFetcher)."""

from typing import Any

from httpx import AsyncClient

from app.modules.library.metadata import Metadata
from tests.modules.library.conftest import FakeFetcher

BASE = "/api/v1/library"
FOUND = Metadata(title="A Great Post", site_name="The Blog", author="Ana Lopez")


async def save(client: AsyncClient, **payload: Any) -> dict[str, Any]:
    response = await client.post(f"{BASE}/items", json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_a_link_without_a_title_gets_the_pages_details(
    owner: AsyncClient, fake_fetcher: FakeFetcher
) -> None:
    fake_fetcher.result = FOUND
    item = await save(owner, url="blog.example.com/post?utm_source=x")
    assert fake_fetcher.calls == [("https://blog.example.com/post?utm_source=x", "link")]
    assert (item["title"], item["siteName"], item["author"]) == (
        "A Great Post",
        "The Blog",
        "Ana Lopez",
    )
    assert item["metadataStatus"] == "fetched"
    assert item["fetchedAt"] is not None


async def test_a_failed_fetch_falls_back_to_the_site(
    owner: AsyncClient, fake_fetcher: FakeFetcher
) -> None:
    item = await save(owner, url="https://blog.example.com/post")
    assert (item["title"], item["siteName"], item["metadataStatus"]) == (
        "blog.example.com",
        "blog.example.com",
        "failed",
    )


async def test_nothing_is_fetched_when_not_needed(
    owner: AsyncClient, fake_fetcher: FakeFetcher
) -> None:
    fake_fetcher.result = FOUND
    titled = await save(owner, url="https://example.com/a", title="My title")
    assert titled["title"] == "My title"
    assert titled["metadataStatus"] == "none"
    await save(owner, body="a note")
    await save(owner, kind="excerpt", excerpt="quote", url="https://example.com/b")
    assert fake_fetcher.calls == []
    duplicate = await owner.post(f"{BASE}/items", json={"url": "example.com/a"})
    assert duplicate.status_code == 409
    assert fake_fetcher.calls == []  # the duplicate check runs before any fetch


async def test_videos_are_fetched_as_videos(owner: AsyncClient, fake_fetcher: FakeFetcher) -> None:
    await save(owner, url="https://youtu.be/dQw4w9WgXcQ")
    assert fake_fetcher.calls == [("https://youtu.be/dQw4w9WgXcQ", "video")]


async def test_refresh_replaces_only_a_fallback_title(
    owner: AsyncClient, fake_fetcher: FakeFetcher
) -> None:
    fallback = await save(owner, url="https://blog.example.com/1")  # fetch failed
    typed = await save(owner, url="https://blog.example.com/2", title="Mine")

    fake_fetcher.result = FOUND
    refreshed = (await owner.post(f"{BASE}/items/{fallback['id']}/refresh")).json()
    assert (refreshed["title"], refreshed["siteName"], refreshed["metadataStatus"]) == (
        "A Great Post",
        "The Blog",
        "fetched",
    )
    assert refreshed["version"] == fallback["version"] + 1

    kept = (await owner.post(f"{BASE}/items/{typed['id']}/refresh")).json()
    assert (kept["title"], kept["author"]) == ("Mine", "Ana Lopez")

    fake_fetcher.result = None
    failed = (await owner.post(f"{BASE}/items/{typed['id']}/refresh")).json()
    assert failed["metadataStatus"] == "failed"
    assert failed["siteName"] == "The Blog"  # earlier details are kept


async def test_refresh_needs_a_link_and_an_owner(
    owner: AsyncClient, intruder: AsyncClient, fake_fetcher: FakeFetcher
) -> None:
    note = await save(owner, body="text")
    no_link = await owner.post(f"{BASE}/items/{note['id']}/refresh")
    assert no_link.status_code == 400
    assert no_link.json()["code"] == "library_no_link"
    link = await save(owner, url="https://example.com/private")
    calls = len(fake_fetcher.calls)
    assert (await intruder.post(f"{BASE}/items/{link['id']}/refresh")).status_code == 404
    assert len(fake_fetcher.calls) == calls


async def test_saves_and_refreshes_are_rate_limited(owner: AsyncClient) -> None:
    for n in range(30):
        await save(owner, body=f"note {n}")
    limited = await owner.post(f"{BASE}/items", json={"body": "one too many"})
    assert limited.status_code == 429
    assert "retry-after" in limited.headers
