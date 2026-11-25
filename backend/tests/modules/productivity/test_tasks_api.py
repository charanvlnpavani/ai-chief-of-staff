"""Tasks API: views, recurrence, conflicts, lists and isolation."""

from datetime import timedelta

from httpx import AsyncClient

from app.core.time import local_today

TZ = "Asia/Kolkata"


def day(offset: int = 0) -> str:
    return (local_today(TZ) + timedelta(days=offset)).isoformat()


async def create_task(client: AsyncClient, **fields: object) -> dict[str, object]:
    payload: dict[str, object] = {"title": "Task"} | fields
    response = await client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


async def titles(client: AsyncClient, view: str) -> list[str]:
    response = await client.get("/api/v1/tasks", params={"view": view})
    return [t["title"] for t in response.json()["items"]]


async def test_views_split_tasks_by_due_date(owner: AsyncClient) -> None:
    await create_task(owner, title="Overdue", dueOn=day(-2))
    await create_task(owner, title="Today", dueOn=day(), priority=1)
    await create_task(owner, title="Later", dueOn=day(3))
    await create_task(owner, title="Someday")
    assert await titles(owner, "today") == ["Overdue", "Today"]
    assert await titles(owner, "overdue") == ["Overdue"]
    assert await titles(owner, "upcoming") == ["Later", "Someday"]


async def test_completing_a_recurring_task_schedules_the_next_one(owner: AsyncClient) -> None:
    task = await create_task(
        owner, title="Weekly review", dueOn=day(), recurrenceRule="freq=weekly"
    )
    assert task["recurrenceRule"] == "FREQ=WEEKLY"
    result = (await owner.post(f"/api/v1/tasks/{task['id']}/complete")).json()
    assert result["task"]["status"] == "done"
    assert result["task"]["completedAt"] is not None
    assert result["nextTask"]["dueOn"] == day(7)
    assert await titles(owner, "completed") == ["Weekly review"]


async def test_overdue_recurring_task_continues_from_today(owner: AsyncClient) -> None:
    task = await create_task(
        owner, title="Daily standup", dueOn=day(-3), recurrenceRule="FREQ=DAILY"
    )
    result = (await owner.post(f"/api/v1/tasks/{task['id']}/complete")).json()
    assert result["nextTask"]["dueOn"] == day(1)


async def test_invalid_recurrence_rule_is_rejected(owner: AsyncClient) -> None:
    response = await owner.post("/api/v1/tasks", json={"title": "x", "recurrenceRule": "every day"})
    assert response.status_code == 422


async def test_stale_version_is_a_conflict(owner: AsyncClient) -> None:
    task = await create_task(owner)
    ok = await owner.patch(f"/api/v1/tasks/{task['id']}", json={"title": "v2", "version": 1})
    assert ok.status_code == 200
    assert ok.json()["version"] == 2
    stale = await owner.patch(f"/api/v1/tasks/{task['id']}", json={"title": "v3", "version": 1})
    assert stale.status_code == 409
    assert stale.json()["code"] == "version_conflict"


async def test_reopening_clears_completion_time(owner: AsyncClient) -> None:
    task = await create_task(owner)
    await owner.post(f"/api/v1/tasks/{task['id']}/complete")
    reopened = await owner.patch(f"/api/v1/tasks/{task['id']}", json={"status": "todo"})
    assert reopened.json()["completedAt"] is None


async def test_search_and_delete(owner: AsyncClient) -> None:
    keep = await create_task(owner, title="Prepare system design notes")
    drop = await create_task(owner, title="Buy groceries")
    found = (await owner.get("/api/v1/tasks", params={"q": "design"})).json()["items"]
    assert [t["id"] for t in found] == [keep["id"]]
    assert (await owner.delete(f"/api/v1/tasks/{drop['id']}")).status_code == 204
    assert (await owner.get(f"/api/v1/tasks/{drop['id']}")).status_code == 404


async def test_like_wildcards_are_escaped(owner: AsyncClient) -> None:
    await create_task(owner, title="100% done")
    await create_task(owner, title="1000 things")
    found = (await owner.get("/api/v1/tasks", params={"q": "100%"})).json()["items"]
    assert [t["title"] for t in found] == ["100% done"]


async def test_pagination_returns_a_cursor(owner: AsyncClient) -> None:
    for i in range(3):
        await create_task(owner, title=f"T{i}")
    first = (await owner.get("/api/v1/tasks", params={"limit": 2})).json()
    assert len(first["items"]) == 2
    assert first["nextCursor"]
    second = (
        await owner.get("/api/v1/tasks", params={"limit": 2, "cursor": first["nextCursor"]})
    ).json()
    assert len(second["items"]) == 1
    assert second["nextCursor"] is None


async def test_lists_names_are_unique_and_tasks_survive_list_deletion(owner: AsyncClient) -> None:
    created = await owner.post("/api/v1/task-lists", json={"name": "Work"})
    assert created.status_code == 201
    duplicate = await owner.post("/api/v1/task-lists", json={"name": "work"})
    assert duplicate.status_code == 409
    task = await create_task(owner, listId=created.json()["id"])
    assert (await owner.delete(f"/api/v1/task-lists/{created.json()['id']}")).status_code == 204
    assert (await owner.get(f"/api/v1/tasks/{task['id']}")).json()["listId"] is None


async def test_other_users_cannot_touch_tasks_or_lists(
    owner: AsyncClient, intruder: AsyncClient
) -> None:
    task = await create_task(owner, title="Private")
    task_list = (await owner.post("/api/v1/task-lists", json={"name": "Mine"})).json()
    assert (await intruder.get(f"/api/v1/tasks/{task['id']}")).status_code == 404
    assert (
        await intruder.patch(f"/api/v1/tasks/{task['id']}", json={"title": "x"})
    ).status_code == 404
    assert (await intruder.post(f"/api/v1/tasks/{task['id']}/complete")).status_code == 404
    assert (await intruder.delete(f"/api/v1/tasks/{task['id']}")).status_code == 404
    borrowed = await intruder.post("/api/v1/tasks", json={"title": "x", "listId": task_list["id"]})
    assert borrowed.status_code == 404
    assert (await intruder.get("/api/v1/tasks")).json()["items"] == []
