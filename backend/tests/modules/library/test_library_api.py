"""Life Library API: capture, duplicates, edits, trash, audit and isolation between users."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import AuditLog
from app.modules.library import service

BASE = "/api/v1/library"
VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


async def save(client: AsyncClient, **payload: Any) -> dict[str, Any]:
    response = await client.post(f"{BASE}/items", json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def ids(client: AsyncClient, path: str = "/items", **params: Any) -> list[str]:
    response = await client.get(f"{BASE}{path}", params=params)
    assert response.status_code == 200, response.text
    return [i["id"] for i in response.json()["items"]]


# ------------------------------------------------------------------ capture


async def test_text_alone_becomes_a_note_titled_by_its_first_line(owner: AsyncClient) -> None:
    item = await save(owner, body="\n# Weekend ideas\n- hike\n- visit the market")
    assert item["kind"] == "note"
    assert item["title"] == "Weekend ideas"
    assert item["status"] == "inbox"
    assert item["url"] is None
    assert item["body"].startswith("# Weekend ideas")
    assert item["excerpt"] is None
    assert item["version"] == 1


async def test_a_url_becomes_a_link_titled_by_its_site(owner: AsyncClient) -> None:
    item = await save(owner, url="www.Example.com/guide?utm_source=newsletter")
    assert item["kind"] == "link"
    assert item["url"] == "https://www.example.com/guide?utm_source=newsletter"
    assert item["title"] == "example.com"
    assert item["siteName"] == "example.com"
    assert item["metadataStatus"] == "failed"  # the test fetcher finds nothing


async def test_the_server_decides_link_versus_video(owner: AsyncClient) -> None:
    video = await save(owner, kind="link", url=VIDEO_URL, title="Talk")
    assert video["kind"] == "video"
    page = await save(owner, kind="video", url="https://example.com/not-a-video")
    assert page["kind"] == "link"


async def test_excerpts_keep_source_and_text_apart_and_may_share_a_source(
    owner: AsyncClient,
) -> None:
    first = await save(
        owner,
        kind="excerpt",
        url="https://example.com/essay",
        excerpt="The best way to predict the future is to invent it.",
        body="Use this in the team talk.",
    )
    assert first["title"] == "example.com"
    assert first["excerpt"].startswith("The best way")
    assert first["body"] == "Use this in the team talk."
    second = await save(
        owner, kind="excerpt", url="https://example.com/essay", excerpt="Another line."
    )
    assert second["id"] != first["id"]
    no_source = await save(owner, kind="excerpt", excerpt="From a paper book.\nPage 12.")
    assert no_source["url"] is None
    assert no_source["title"] == "From a paper book."


async def test_capture_rejects_mismatched_shapes(owner: AsyncClient) -> None:
    cases: list[dict[str, Any]] = [
        {"kind": "note", "url": "https://example.com", "body": "x"},
        {"kind": "note"},
        {"kind": "link"},
        {"kind": "excerpt", "url": "https://example.com"},
        {"body": "\x00\x01  "},  # nothing left after cleaning
        {"body": "x" * 100_001},
        {"title": "x" * 301, "body": "x"},
    ]
    for payload in cases:
        response = await owner.post(f"{BASE}/items", json=payload)
        assert response.status_code == 422, (payload, response.text)
    bad_url = await owner.post(f"{BASE}/items", json={"url": "javascript:alert(1)"})
    assert bad_url.status_code == 400
    assert bad_url.json()["code"] == "library_url_invalid"


async def test_control_characters_are_stripped(owner: AsyncClient) -> None:
    item = await save(owner, title="Tab\there\x00", body="line one\x00\r\nline two\x07")
    assert item["title"] == "Tab here"
    assert item["body"] == "line one\nline two"


# ------------------------------------------------------------------ duplicates


async def test_saving_a_link_twice_points_at_the_first(owner: AsyncClient) -> None:
    first = await save(owner, url="https://example.com/a?b=2&a=1")
    for spelling in (
        "http://www.example.com/a/?a=1&b=2&utm_campaign=x",
        "example.com/a?a=1&b=2#top",
    ):
        again = await owner.post(f"{BASE}/items", json={"url": spelling})
        assert again.status_code == 409
        assert again.json()["code"] == "library_duplicate"
        assert again.json()["existingId"] == first["id"]
    await save(owner, url=VIDEO_URL)
    short = await owner.post(f"{BASE}/items", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert short.status_code == 409


async def test_a_lost_race_on_the_unique_index_is_the_same_409(
    owner: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two simultaneous saves can both pass the duplicate check; the database index then
    refuses the second. Requests share one session in tests, so the race is simulated by
    skipping the check."""
    first = await save(owner, url="https://example.com/race")

    async def no_check(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(service, "_ensure_not_saved", no_check)
    second = await owner.post(f"{BASE}/items", json={"url": "example.com/race/"})
    assert second.status_code == 409
    assert second.json()["code"] == "library_duplicate"
    assert second.json()["existingId"] == first["id"]
    assert await ids(owner) == [first["id"]]  # the session is usable after the rollback


async def test_each_user_has_their_own_duplicates(
    owner: AsyncClient, intruder: AsyncClient
) -> None:
    await save(owner, url="https://example.com/shared")
    await save(intruder, url="https://example.com/shared")


# ------------------------------------------------------------------ browse


async def test_list_is_newest_first_with_filters_and_paging(owner: AsyncClient) -> None:
    note = await save(owner, body="first")
    link = await save(owner, url="https://example.com/1", status="to_read", isFavorite=True)
    video = await save(owner, url=VIDEO_URL, status="reading")

    assert await ids(owner) == [video["id"], link["id"], note["id"]]
    assert await ids(owner, status="to_read") == [link["id"]]
    assert await ids(owner, kind="video") == [video["id"]]
    assert await ids(owner, favorite="true") == [link["id"]]
    assert set(await ids(owner, favorite="false")) == {note["id"], video["id"]}

    page = (await owner.get(f"{BASE}/items", params={"limit": 2})).json()
    assert [i["id"] for i in page["items"]] == [video["id"], link["id"]]
    rest = await ids(owner, limit=2, cursor=page["nextCursor"])
    assert rest == [note["id"]]

    bad = await owner.get(f"{BASE}/items", params={"status": "done"})
    assert bad.status_code == 422


async def test_list_rows_carry_a_preview_not_the_full_text(owner: AsyncClient) -> None:
    await save(owner, kind="excerpt", excerpt="quoted " * 100, body="my own thoughts")
    (row,) = (await owner.get(f"{BASE}/items")).json()["items"]
    assert "body" not in row
    assert "excerpt" not in row
    assert row["preview"].startswith("quoted quoted")
    assert len(row["preview"]) <= 240
    assert row["preview"].endswith("…")


async def test_counts(owner: AsyncClient) -> None:
    await save(owner, body="a")
    await save(owner, body="b", status="archived", isFavorite=True)
    gone = await save(owner, body="c")
    await owner.delete(f"{BASE}/items/{gone['id']}")
    counts = (await owner.get(f"{BASE}/counts")).json()
    assert counts == {
        "inbox": 1,
        "toRead": 0,
        "reading": 0,
        "archived": 1,
        "favorites": 1,
        "trash": 1,
    }


# ------------------------------------------------------------------ edit


async def test_update_needs_the_current_version(owner: AsyncClient) -> None:
    item = await save(owner, body="draft")
    url = f"{BASE}/items/{item['id']}"
    moved = await owner.patch(url, json={"version": 1, "status": "reading", "isFavorite": True})
    assert moved.status_code == 200
    assert (moved.json()["status"], moved.json()["isFavorite"], moved.json()["version"]) == (
        "reading",
        True,
        2,
    )
    stale = await owner.patch(url, json={"version": 1, "title": "Lost update"})
    assert stale.status_code == 409
    assert stale.json()["code"] == "version_conflict"
    missing = await owner.patch(url, json={"title": "No version"})
    assert missing.status_code == 422


async def test_update_text_fields(owner: AsyncClient) -> None:
    item = await save(owner, kind="excerpt", excerpt="quote", body="note")
    url = f"{BASE}/items/{item['id']}"
    cleared = await owner.patch(url, json={"version": 1, "body": None, "title": "  Renamed  "})
    assert (cleared.json()["body"], cleared.json()["title"]) == (None, "Renamed")
    kept = await owner.patch(url, json={"version": 2, "title": None})
    assert kept.json()["title"] == "Renamed"  # a title cannot be cleared
    no_text = await owner.patch(url, json={"version": 3, "excerpt": None})
    assert no_text.status_code == 400
    assert no_text.json()["code"] == "library_excerpt_required"


async def test_changing_a_link_rechecks_duplicates_and_kind(owner: AsyncClient) -> None:
    taken = await save(owner, url="https://example.com/taken")
    item = await save(owner, url="https://example.com/old")
    url = f"{BASE}/items/{item['id']}"

    clash = await owner.patch(url, json={"version": 1, "url": "example.com/taken/"})
    assert clash.status_code == 409
    assert clash.json()["existingId"] == taken["id"]

    respelled = await owner.patch(url, json={"version": 1, "url": "http://www.example.com/old/"})
    assert respelled.status_code == 200  # same page: not a duplicate of itself
    assert respelled.json()["url"] == "http://www.example.com/old/"

    video = await owner.patch(url, json={"version": 2, "url": VIDEO_URL})
    assert (video.json()["kind"], video.json()["siteName"]) == ("video", "youtube.com")

    emptied = await owner.patch(url, json={"version": 3, "url": None})
    assert emptied.status_code == 400
    assert emptied.json()["code"] == "library_url_required"


async def test_notes_cannot_gain_a_link(owner: AsyncClient) -> None:
    note = await save(owner, body="text")
    response = await owner.patch(
        f"{BASE}/items/{note['id']}", json={"version": 1, "url": "https://example.com"}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "library_note_url"


async def test_an_excerpt_source_can_be_changed_or_removed(owner: AsyncClient) -> None:
    item = await save(owner, kind="excerpt", excerpt="quote", url="https://example.com/a")
    url = f"{BASE}/items/{item['id']}"
    removed = await owner.patch(url, json={"version": 1, "url": None})
    assert (removed.json()["url"], removed.json()["siteName"]) == (None, None)
    added = await owner.patch(url, json={"version": 2, "url": "example.org/b"})
    assert added.json()["url"] == "https://example.org/b"


# ------------------------------------------------------------------ trash


async def test_trash_restore_and_permanent_delete(
    owner: AsyncClient, db_session: AsyncSession
) -> None:
    item = await save(owner, url="https://example.com/secret-plans", title="Secret plans")
    url = f"{BASE}/items/{item['id']}"

    early = await owner.delete(f"{url}/permanent")
    assert early.status_code == 409
    assert early.json()["code"] == "library_not_in_trash"

    assert (await owner.delete(url)).status_code == 204
    assert (await owner.get(url)).status_code == 404
    assert await ids(owner) == []
    assert await ids(owner, "/trash") == [item["id"]]
    assert (await owner.delete(url)).status_code == 404  # already in the trash

    restored = await owner.post(f"{url}/restore")
    assert restored.status_code == 200
    assert restored.json()["deletedAt"] is None
    assert await ids(owner) == [item["id"]]
    assert (await owner.post(f"{url}/restore")).status_code == 404  # not in the trash

    await owner.delete(url)
    assert (await owner.delete(f"{url}/permanent")).status_code == 204
    assert await ids(owner, "/trash") == []
    assert (await owner.post(f"{url}/restore")).status_code == 404

    audit = list(
        await db_session.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == "library_item")
            .order_by(AuditLog.occurred_at)
        )
    )
    assert [a.action for a in audit] == [
        "library.item_deleted",
        "library.item_restored",
        "library.item_deleted",
        "library.item_purged",
    ]
    assert all(str(a.entity_id) == item["id"] for a in audit)
    assert all(a.details == {"kind": "link"} for a in audit)  # no title or link


async def test_a_deleted_link_can_be_saved_again_but_then_not_restored(
    owner: AsyncClient,
) -> None:
    old = await save(owner, url="https://example.com/again")
    await owner.delete(f"{BASE}/items/{old['id']}")
    new = await save(owner, url="https://example.com/again")
    restore = await owner.post(f"{BASE}/items/{old['id']}/restore")
    assert restore.status_code == 409
    assert restore.json()["existingId"] == new["id"]


# ------------------------------------------------------------------ isolation


async def test_another_user_cannot_see_or_touch_items(
    owner: AsyncClient, intruder: AsyncClient
) -> None:
    live = await save(owner, body="private")
    trashed = await save(owner, url="https://example.com/private")
    await owner.delete(f"{BASE}/items/{trashed['id']}")

    for item in (live, trashed):
        url = f"{BASE}/items/{item['id']}"
        assert (await intruder.get(url)).status_code == 404
        assert (await intruder.patch(url, json={"version": 1, "title": "x"})).status_code == 404
        assert (await intruder.delete(url)).status_code == 404
        assert (await intruder.post(f"{url}/restore")).status_code == 404
        assert (await intruder.delete(f"{url}/permanent")).status_code == 404

    assert await ids(intruder) == []
    assert await ids(intruder, "/trash") == []
    counts = (await intruder.get(f"{BASE}/counts")).json()
    assert set(counts.values()) == {0}
    # The owner's data is untouched.
    assert await ids(owner) == [live["id"]]
    assert await ids(owner, "/trash") == [trashed["id"]]


async def test_signed_out_requests_are_refused(client: AsyncClient) -> None:
    assert (await client.get(f"{BASE}/items")).status_code == 401
    assert (await client.post(f"{BASE}/items", json={"body": "x"})).status_code == 401
