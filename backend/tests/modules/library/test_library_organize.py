"""Life Library search, tags and collections."""

import uuid
from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.library.models import LibraryItem

BASE = "/api/v1/library"


async def save(client: AsyncClient, **payload: Any) -> dict[str, Any]:
    response = await client.post(f"{BASE}/items", json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def found(client: AsyncClient, **params: Any) -> list[str]:
    response = await client.get(f"{BASE}/items", params=params)
    assert response.status_code == 200, response.text
    return [i["id"] for i in response.json()["items"]]


async def collection(client: AsyncClient, name: str) -> dict[str, Any]:
    response = await client.post(f"{BASE}/collections", json={"name": name})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def tag_list(client: AsyncClient) -> dict[str, int]:
    return {t["name"]: t["itemCount"] for t in (await client.get(f"{BASE}/tags")).json()}


# ------------------------------------------------------------------ search


async def test_title_matches_rank_above_excerpt_and_note_matches(owner: AsyncClient) -> None:
    in_body = await save(owner, title="Weekly notes", body="Read about kubernetes operators")
    # Explicit title: by default an excerpt is titled by its first line, matching twice.
    in_excerpt = await save(
        owner, kind="excerpt", title="Scheduler quote", excerpt="Kubernetes schedules pods."
    )
    in_title = await save(owner, title="Kubernetes the hard way", body="cluster setup")
    await save(owner, title="Unrelated", body="gardening")
    assert await found(owner, q="kubernetes") == [in_title["id"], in_excerpt["id"], in_body["id"]]


async def test_websearch_syntax(owner: AsyncClient) -> None:
    phrase = await save(owner, body="the quick brown fox")
    scrambled = await save(owner, body="brown and quick, the fox")
    other = await save(owner, body="a slow brown dog")
    assert await found(owner, q='"quick brown"') == [phrase["id"]]
    assert set(await found(owner, q="brown -fox")) == {other["id"]}
    assert set(await found(owner, q="fox OR dog")) == {phrase["id"], scrambled["id"], other["id"]}


async def test_partial_text_finds_links_titles_and_tags(owner: AsyncClient) -> None:
    repo = await save(owner, url="https://github.com/astral-sh/uv", title="uv")
    tagged = await save(owner, body="sourdough starter", tags=["Baking"])
    assert await found(owner, q="githu") == [repo["id"]]
    assert await found(owner, q="bak") == [tagged["id"]]
    assert await found(owner, q="sourd") == [tagged["id"]]  # title substring (first line)


async def test_search_input_is_never_a_pattern_or_query_syntax_error(owner: AsyncClient) -> None:
    await save(owner, body="anything at all")
    for q in ("%", "_", "\\", "!!!", "&|<->", "'", '"', "-", "OR"):
        assert await found(owner, q=q) == [], q
    assert len(await found(owner, q="   ")) == 1  # blank means no search
    too_long = await owner.get(f"{BASE}/items", params={"q": "x" * 201})
    assert too_long.status_code == 422


async def test_search_respects_filters_trash_and_owner(
    owner: AsyncClient, intruder: AsyncClient
) -> None:
    keep = await save(owner, body="python tips", status="to_read")
    await save(owner, body="python tricks", status="archived")
    gone = await save(owner, body="python trash")
    await owner.delete(f"{BASE}/items/{gone['id']}")
    await save(intruder, body="python secrets")
    assert len(await found(owner, q="python")) == 2  # not the trashed one
    assert await found(owner, q="python", status="to_read") == [keep["id"]]
    assert gone["id"] not in await found(owner, q="trash")
    assert len(await found(intruder, q="python")) == 1


async def test_search_pages_are_stable(owner: AsyncClient) -> None:
    made = [(await save(owner, body=f"rust note {n}"))["id"] for n in range(5)]
    first = (await owner.get(f"{BASE}/items", params={"q": "rust", "limit": 2})).json()
    seen = [i["id"] for i in first["items"]]
    cursor = first["nextCursor"]
    while cursor:
        page = (
            await owner.get(f"{BASE}/items", params={"q": "rust", "limit": 2, "cursor": cursor})
        ).json()
        seen += [i["id"] for i in page["items"]]
        cursor = page["nextCursor"]
    assert sorted(seen) == sorted(made)
    assert len(seen) == len(set(seen))


async def test_date_filters_use_the_users_local_days(
    owner: AsyncClient, db_session: AsyncSession
) -> None:
    await owner.patch("/api/v1/users/me", json={"timezone": "Asia/Kolkata"})  # UTC+05:30
    late = await save(owner, body="late evening")
    early = await save(owner, body="early morning")

    async def saved_at(item: dict[str, Any], when: datetime) -> None:
        await db_session.execute(
            update(LibraryItem)
            .where(LibraryItem.id == uuid.UUID(item["id"]))
            .values(created_at=when)
        )

    # 2026-03-01 23:00 in Kolkata is 17:30 UTC; 2026-03-02 00:30 there is 19:00 UTC on the 1st.
    await saved_at(late, datetime(2026, 3, 1, 17, 30, tzinfo=UTC))
    await saved_at(early, datetime(2026, 3, 1, 19, 0, tzinfo=UTC))

    assert await found(owner, **{"from": "2026-03-01", "to": "2026-03-01"}) == [late["id"]]
    assert await found(owner, **{"from": "2026-03-02"}) == [early["id"]]
    assert await found(owner, to="2026-03-02") == [early["id"], late["id"]]
    reversed_range = await owner.get(
        f"{BASE}/items", params={"from": "2026-03-02", "to": "2026-03-01"}
    )
    assert reversed_range.status_code == 400
    assert reversed_range.json()["code"] == "date_order"


# ------------------------------------------------------------------ tags


async def test_tags_are_case_insensitive_and_kept_in_first_spelling(owner: AsyncClient) -> None:
    first = await save(owner, body="a", tags=["#Python", "rust", "python "])
    assert first["tags"] == ["Python", "rust"]
    second = await save(owner, body="b", tags=["PYTHON"])
    assert second["tags"] == ["Python"]
    assert await tag_list(owner) == {"Python": 2, "rust": 1}
    assert await found(owner, tag="python") == [second["id"], first["id"]]
    rows = (await owner.get(f"{BASE}/items")).json()["items"]
    assert [r["tags"] for r in rows] == [["Python"], ["Python", "rust"]]


async def test_updating_tags_replaces_them(owner: AsyncClient) -> None:
    item = await save(owner, body="x", tags=["one", "two"])
    url = f"{BASE}/items/{item['id']}"
    kept = await owner.patch(url, json={"version": 1, "title": "Renamed"})
    assert kept.json()["tags"] == ["one", "two"]
    replaced = await owner.patch(url, json={"version": 2, "tags": ["three", "One"]})
    assert replaced.json()["tags"] == ["one", "three"]  # "One" reuses the existing tag
    cleared = await owner.patch(url, json={"version": 3, "tags": []})
    assert cleared.json()["tags"] == []
    assert await tag_list(owner) == {"one": 0, "three": 0, "two": 0}


async def test_tag_limits(owner: AsyncClient) -> None:
    many = await owner.post(
        f"{BASE}/items", json={"body": "x", "tags": [f"t{n}" for n in range(21)]}
    )
    assert many.status_code == 422
    long = await owner.post(f"{BASE}/items", json={"body": "x", "tags": ["x" * 41]})
    assert long.status_code == 422
    blank = await owner.post(f"{BASE}/items", json={"body": "x", "tags": ["#  "]})
    assert blank.status_code == 422


async def test_tag_counts_skip_the_trash(owner: AsyncClient) -> None:
    await save(owner, body="a", tags=["work"])
    gone = await save(owner, body="b", tags=["work"])
    await owner.delete(f"{BASE}/items/{gone['id']}")
    assert await tag_list(owner) == {"work": 1}


async def test_rename_and_merge_tags(owner: AsyncClient) -> None:
    a = await save(owner, body="a", tags=["js"])
    b = await save(owner, body="b", tags=["javascript", "js"])
    c = await save(owner, body="c", tags=["javascript"])
    tags = {t["name"]: t["id"] for t in (await owner.get(f"{BASE}/tags")).json()}

    recased = await owner.patch(f"{BASE}/tags/{tags['javascript']}", json={"name": "JavaScript"})
    assert recased.json() == {"id": tags["javascript"], "name": "JavaScript", "itemCount": 2}

    merged = await owner.patch(f"{BASE}/tags/{tags['js']}", json={"name": "javascript"})
    assert merged.status_code == 200
    assert merged.json() == {"id": tags["javascript"], "name": "JavaScript", "itemCount": 3}
    assert await tag_list(owner) == {"JavaScript": 3}
    for item in (a, b, c):
        detail = (await owner.get(f"{BASE}/items/{item['id']}")).json()
        assert detail["tags"] == ["JavaScript"]


async def test_deleting_a_tag_keeps_the_items(owner: AsyncClient) -> None:
    item = await save(owner, body="x", tags=["temp", "keep"])
    temp = next(t for t in (await owner.get(f"{BASE}/tags")).json() if t["name"] == "temp")
    assert (await owner.delete(f"{BASE}/tags/{temp['id']}")).status_code == 204
    assert (await owner.get(f"{BASE}/items/{item['id']}")).json()["tags"] == ["keep"]


# ------------------------------------------------------------------ collections


async def test_collections_hold_items(owner: AsyncClient) -> None:
    reading = await collection(owner, "Reading list")
    item = await save(owner, url="https://example.com/a", collectionId=reading["id"])
    loose = await save(owner, body="loose")
    assert item["collectionId"] == reading["id"]
    assert await found(owner, collection=reading["id"]) == [item["id"]]

    moved = await owner.patch(
        f"{BASE}/items/{loose['id']}", json={"version": 1, "collectionId": reading["id"]}
    )
    assert moved.json()["collectionId"] == reading["id"]
    out = await owner.patch(f"{BASE}/items/{item['id']}", json={"version": 1, "collectionId": None})
    assert out.json()["collectionId"] is None
    assert [c["itemCount"] for c in (await owner.get(f"{BASE}/collections")).json()] == [1]


async def test_collection_names_are_unique_ignoring_case(owner: AsyncClient) -> None:
    first = await collection(owner, "Recipes")
    clash = await owner.post(f"{BASE}/collections", json={"name": " recipes "})
    assert clash.status_code == 409
    assert clash.json()["code"] == "library_collection_exists"
    other = await collection(owner, "Travel")
    rename = await owner.patch(
        f"{BASE}/collections/{other['id']}", json={"version": 1, "name": "RECIPES"}
    )
    assert rename.status_code == 409
    recase = await owner.patch(
        f"{BASE}/collections/{first['id']}", json={"version": 1, "name": "recipes"}
    )
    assert recase.json()["name"] == "recipes"
    stale = await owner.patch(
        f"{BASE}/collections/{first['id']}", json={"version": 1, "sortOrder": 3}
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "version_conflict"


async def test_deleting_a_collection_releases_its_items(owner: AsyncClient) -> None:
    box = await collection(owner, "Old")
    live = await save(owner, body="live", collectionId=box["id"])
    trashed = await save(owner, body="trashed", collectionId=box["id"])
    await owner.delete(f"{BASE}/items/{trashed['id']}")

    assert (await owner.delete(f"{BASE}/collections/{box['id']}")).status_code == 204
    assert (await owner.get(f"{BASE}/collections")).json() == []
    detail = (await owner.get(f"{BASE}/items/{live['id']}")).json()
    assert (detail["collectionId"], detail["version"]) == (None, 2)  # stale edits now 409
    restored = await owner.post(f"{BASE}/items/{trashed['id']}/restore")
    assert restored.json()["collectionId"] is None

    gone = await owner.post(f"{BASE}/items", json={"body": "x", "collectionId": box["id"]})
    assert gone.status_code == 404
    assert gone.json()["code"] == "library_collection_not_found"
    await collection(owner, "Old")  # the name is free again


async def test_collection_order(owner: AsyncClient) -> None:
    await owner.post(f"{BASE}/collections", json={"name": "b", "sortOrder": 1})
    await owner.post(f"{BASE}/collections", json={"name": "C", "sortOrder": 0})
    await owner.post(f"{BASE}/collections", json={"name": "a", "sortOrder": 1})
    names = [c["name"] for c in (await owner.get(f"{BASE}/collections")).json()]
    assert names == ["C", "a", "b"]


# ------------------------------------------------------------------ isolation


async def test_tags_and_collections_belong_to_one_user(
    owner: AsyncClient, intruder: AsyncClient
) -> None:
    box = await collection(owner, "Private")
    await save(owner, body="x", tags=["secret"])
    tag_id = (await owner.get(f"{BASE}/tags")).json()[0]["id"]

    assert (await intruder.get(f"{BASE}/collections")).json() == []
    assert (await intruder.get(f"{BASE}/tags")).json() == []
    assert (
        await intruder.patch(f"{BASE}/collections/{box['id']}", json={"version": 1, "name": "x"})
    ).status_code == 404
    assert (await intruder.delete(f"{BASE}/collections/{box['id']}")).status_code == 404
    assert (await intruder.patch(f"{BASE}/tags/{tag_id}", json={"name": "x"})).status_code == 404
    assert (await intruder.delete(f"{BASE}/tags/{tag_id}")).status_code == 404

    into_theirs = await intruder.post(
        f"{BASE}/items", json={"body": "x", "collectionId": box["id"]}
    )
    assert into_theirs.status_code == 404
    mine = await save(intruder, body="y", tags=["secret"])  # same name, separate tag
    assert mine["tags"] == ["secret"]
    assert await found(intruder, tag="secret") == [mine["id"]]
    assert await found(intruder, collection=box["id"]) == []
    await collection(intruder, "Private")  # names are per user
    assert await tag_list(owner) == {"secret": 1}
