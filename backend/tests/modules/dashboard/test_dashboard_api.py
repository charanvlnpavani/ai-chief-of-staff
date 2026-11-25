"""Dashboard: deterministic aggregates and headline."""

from httpx import AsyncClient

from app.core.time import local_today
from app.modules.dashboard.service import build_headline

TZ = "Asia/Kolkata"


def test_headline_wording() -> None:
    assert build_headline(1, 0, 0, 0) == "1 priority"
    assert (
        build_headline(3, 2, 40, 1)
        == "3 priorities · 2 habits left · 40 min to your learning goal · 1 review due"
    )
    assert build_headline(0, 0, 0, 0) == "You're all caught up for today."


async def test_empty_dashboard(owner: AsyncClient) -> None:
    body = (await owner.get("/api/v1/dashboard")).json()
    assert body["date"] == local_today(TZ).isoformat()
    assert body["timezone"] == TZ
    assert body["tasks"]["counts"] == {
        "dueToday": 0,
        "overdue": 0,
        "completedToday": 0,
        "openTotal": 0,
    }
    assert body["habits"]["scheduled"] == 0
    assert body["learning"]["goalMinutes"] == 120
    assert body["brief"]["headline"] == "120 min to your learning goal"


async def test_dashboard_reflects_real_activity(owner: AsyncClient) -> None:
    today = local_today(TZ).isoformat()
    task = (
        await owner.post("/api/v1/tasks", json={"title": "Ship M4", "dueOn": today, "priority": 1})
    ).json()
    await owner.post("/api/v1/tasks", json={"title": "Done already", "dueOn": today})
    done = (await owner.get("/api/v1/tasks", params={"q": "Done already"})).json()["items"][0]
    await owner.post(f"/api/v1/tasks/{done['id']}/complete")
    habit = (await owner.post("/api/v1/habits", json={"name": "Read"})).json()
    await owner.post(
        "/api/v1/professional/learning-sessions", json={"durationMin": 90, "topic": "Heaps"}
    )

    body = (await owner.get("/api/v1/dashboard")).json()
    assert body["tasks"]["counts"]["dueToday"] == 1
    assert body["tasks"]["counts"]["completedToday"] == 1
    assert body["tasks"]["top"][0]["id"] == task["id"]
    assert body["habits"]["scheduled"] == 1
    assert body["habits"]["items"][0]["habitId"] == habit["id"]
    assert body["learning"]["todayMinutes"] == 90
    assert body["brief"]["learningMinutesLeft"] == 30
    assert body["brief"]["headline"] == "1 priority · 1 habit left · 30 min to your learning goal"


async def test_dashboard_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/dashboard")).status_code == 401
