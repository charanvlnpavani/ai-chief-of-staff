"""Roadmaps API: built-in and AI drafts, daily ticks, completion, guards and isolation."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.models import AIUsageLedger
from app.ai.pricing import Usage
from app.core.time import local_today
from app.modules.roadmaps import router as roadmaps_router
from app.modules.roadmaps.generator import GeneratedRoadmap
from app.modules.roadmaps.schemas import PlannedDay, PlannedLevel, PlannedRoadmap, PlannedTask

TZ = "Asia/Kolkata"
BASE = "/api/v1/roadmaps"


def day(offset: int = 0) -> str:
    return (local_today(TZ) + timedelta(days=offset)).isoformat()


class FakeGenerator:
    """Scripted stand-in for Claude: never calls the API."""

    def __init__(self, *, refuse: bool = False) -> None:
        self.refuse = refuse
        self.calls: list[str] = []

    async def generate(
        self, *, subject: str, target_days: int, minutes_per_day: int
    ) -> GeneratedRoadmap:
        self.calls.append(subject)
        plan = PlannedRoadmap(
            title=f"{subject}: zero to pro",
            levels=[
                PlannedLevel(
                    level=level,  # type: ignore[arg-type]
                    days=[
                        PlannedDay(
                            tasks=[
                                PlannedTask(
                                    title=f"{level} task {n}", detail="  Do it.  ", minutes=1
                                )
                            ]
                        )
                        for n in (1, 2)
                    ],
                )
                # Deliberately out of order: the service must sort levels.
                for level in ("advanced", "basic", "pro", "intermediate")
            ],
        )
        return GeneratedRoadmap(
            plan=None if self.refuse else plan,
            refused=self.refuse,
            model="claude-opus-5-5",
            usage=Usage(
                input_tokens=1000, output_tokens=2000, cache_read_tokens=0, cache_write_tokens=0
            ),
            request_id="req_test",
        )


@pytest.fixture
def fake_generator(app: FastAPI) -> Iterator[FakeGenerator]:
    fake = FakeGenerator()
    app.dependency_overrides[roadmaps_router._optional_generator] = lambda: fake
    yield fake
    app.dependency_overrides.pop(roadmaps_router._optional_generator, None)


async def save_dsa(client: AsyncClient) -> dict[str, object]:
    draft = (await client.post(f"{BASE}/draft", json={"subject": "  DSA "})).json()
    created = await client.post(BASE, json=draft)
    assert created.status_code == 201, created.text
    body: dict[str, object] = created.json()
    return body


def small_draft(days: int = 2) -> dict[str, object]:
    return {
        "subject": "Chess",
        "title": "Chess basics",
        "source": "ai",
        "days": [
            {"level": "basic", "tasks": [{"title": f"Day {d} task", "minutes": 20}]}
            for d in range(1, days + 1)
        ],
    }


async def test_dsa_builtin_roadmap_needs_no_ai(owner: AsyncClient) -> None:
    templates = (await owner.get(f"{BASE}/templates")).json()
    assert [t["key"] for t in templates] == ["dsa"]
    draft = (
        await owner.post(f"{BASE}/draft", json={"subject": "Data Structures and Algorithms"})
    ).json()
    assert draft["source"] == "template"
    levels = [d["level"] for d in draft["days"]]
    assert levels[0] == "basic"
    assert levels[-1] == "pro"
    assert levels == sorted(levels, key=["basic", "intermediate", "advanced", "pro"].index)

    roadmap = await save_dsa(owner)
    total_days = len(draft["days"])
    progress = roadmap["progress"]
    assert progress["done"] == 0  # type: ignore[index]
    assert progress["currentLevel"] == "basic"  # type: ignore[index]
    assert progress["totalDays"] == total_days  # type: ignore[index]
    assert progress["projectedFinish"] == day(total_days - 1)  # type: ignore[index]
    today = roadmap["today"]
    assert today["days"] == [1]  # type: ignore[index]
    assert len(today["tasks"]) == 2  # type: ignore[index]


async def test_daily_ticks_progress_and_go_ahead(owner: AsyncClient) -> None:
    roadmap = await save_dsa(owner)
    url = f"{BASE}/{roadmap['id']}"
    first, second = roadmap["today"]["tasks"]  # type: ignore[index]
    once = await owner.put(f"{url}/tasks/{first['id']}/done")
    again = (await owner.put(f"{url}/tasks/{first['id']}/done")).json()  # idempotent
    assert once.status_code == 200
    assert again["progress"]["done"] == 1
    assert again["today"]["complete"] is False
    finished = (await owner.put(f"{url}/tasks/{second['id']}/done")).json()
    assert finished["today"]["complete"] is True
    assert finished["today"]["canGoAhead"] is True
    assert finished["progress"]["streakDays"] == 1
    assert finished["progress"]["currentDay"] == 2
    assert [t["completedOn"] for t in finished["today"]["tasks"]] == [day(), day()]
    ahead = (await owner.get(url, params={"ahead": "true"})).json()
    assert ahead["today"]["days"] == [1, 2]
    undone = (await owner.delete(f"{url}/tasks/{second['id']}/done")).json()
    assert undone["today"]["complete"] is False
    assert undone["progress"]["done"] == 1


async def test_last_tick_completes_the_roadmap(owner: AsyncClient) -> None:
    created = (await owner.post(BASE, json=small_draft(days=2))).json()
    url = f"{BASE}/{created['id']}"
    tasks = created["tasks"]
    await owner.put(f"{url}/tasks/{tasks[0]['id']}/done")
    done = (await owner.put(f"{url}/tasks/{tasks[1]['id']}/done", params={"ahead": "true"})).json()
    assert done["status"] == "completed"
    assert done["completedAt"] is not None
    assert done["today"]["finished"] is True
    assert done["progress"]["projectedFinish"] is None
    reopened = (await owner.delete(f"{url}/tasks/{tasks[1]['id']}/done")).json()
    assert reopened["status"] == "active"
    assert reopened["completedAt"] is None


async def test_ai_draft_is_gated_and_costed(
    owner: AsyncClient, fake_generator: FakeGenerator, db_session: AsyncSession
) -> None:
    request = {"subject": "System design", "targetDays": 30, "minutesPerDay": 45}
    no_consent = await owner.post(f"{BASE}/draft", json=request)
    assert no_consent.json()["code"] == "consent_required"
    assert fake_generator.calls == []
    await owner.put("/api/v1/users/me/consents/ai_processing", json={"granted": True})
    draft = (await owner.post(f"{BASE}/draft", json=request)).json()
    assert draft["source"] == "ai"
    assert draft["title"] == "System design: zero to pro"
    assert [d["level"] for d in draft["days"]] == ["basic"] * 2 + ["intermediate"] * 2 + [
        "advanced"
    ] * 2 + ["pro"] * 2  # sorted, never trusted as given
    assert draft["days"][0]["tasks"][0] == {
        "title": "basic task 1",
        "detail": "Do it.",
        "minutes": 5,  # clamped from 1
    }
    rows = list(
        await db_session.scalars(select(AIUsageLedger).where(AIUsageLedger.route == "roadmap"))
    )
    assert len(rows) == 1
    assert rows[0].cost_usd_micros > 0
    # Saving the AI draft works like any other draft.
    assert (await owner.post(BASE, json=draft)).status_code == 201


async def test_ai_refusal_is_still_costed(
    owner: AsyncClient, fake_generator: FakeGenerator, db_session: AsyncSession
) -> None:
    fake_generator.refuse = True
    await owner.put("/api/v1/users/me/consents/ai_processing", json={"granted": True})
    refused = await owner.post(f"{BASE}/draft", json={"subject": "Something"})
    assert refused.json()["code"] == "ai_refused"
    rows = list(
        await db_session.scalars(select(AIUsageLedger).where(AIUsageLedger.route == "roadmap"))
    )
    assert len(rows) == 1


async def test_ai_budget_and_missing_key(
    owner: AsyncClient, app: FastAPI, db_session: AsyncSession
) -> None:
    # No ANTHROPIC_API_KEY in tests: new subjects explain why, built-ins still work.
    missing = await owner.post(f"{BASE}/draft", json={"subject": "Rust"})
    assert missing.json()["code"] == "ai_not_configured"
    assert (await owner.post(f"{BASE}/draft", json={"subject": "dsa"})).status_code == 200
    fake = FakeGenerator()
    app.dependency_overrides[roadmaps_router._optional_generator] = lambda: fake
    await owner.put("/api/v1/users/me/consents/ai_processing", json={"granted": True})
    user_id = (await owner.get("/api/v1/users/me")).json()["user"]["id"]
    db_session.add(
        AIUsageLedger(
            user_id=user_id,
            route="chat",
            model="claude-opus-5-5",
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost_usd_micros=1_000_000_000,  # $1000 spent this month
            batch=False,
        )
    )
    await db_session.commit()
    over = await owner.post(f"{BASE}/draft", json={"subject": "Rust"})
    assert over.json()["code"] == "ai_budget_exceeded"
    assert fake.calls == []
    app.dependency_overrides.pop(roadmaps_router._optional_generator, None)


async def test_guards(owner: AsyncClient) -> None:
    backwards = small_draft()
    backwards["days"] = [  # type: ignore[index]
        {"level": "pro", "tasks": [{"title": "x"}]},
        {"level": "basic", "tasks": [{"title": "y"}]},
    ]
    assert (await owner.post(BASE, json=backwards)).status_code == 422
    fake_template = small_draft() | {"source": "template", "templateKey": "nope"}
    assert (await owner.post(BASE, json=fake_template)).json()["code"] == "unknown_template"
    created = (await owner.post(BASE, json=small_draft())).json()
    url = f"{BASE}/{created['id']}"
    forced = await owner.patch(url, json={"status": "completed"})
    assert forced.json()["code"] == "status_not_allowed"
    await owner.patch(url, json={"status": "archived"})
    assert (await owner.get(BASE)).json() == []
    task = created["tasks"][0]["id"]
    blocked = await owner.put(f"{url}/tasks/{task}/done")
    assert blocked.json()["code"] == "roadmap_archived"
    stale = await owner.patch(url, json={"title": "New", "version": created["version"]})
    assert stale.json()["code"] == "version_conflict"


async def test_other_users_cannot_see_or_tick(owner: AsyncClient, intruder: AsyncClient) -> None:
    created = (await owner.post(BASE, json=small_draft())).json()
    url = f"{BASE}/{created['id']}"
    task = created["tasks"][0]["id"]
    assert (await intruder.get(url)).status_code == 404
    assert (await intruder.put(f"{url}/tasks/{task}/done")).status_code == 404
    assert (await intruder.patch(url, json={"title": "mine"})).status_code == 404
    assert (await intruder.delete(url)).status_code == 404
    assert (await intruder.get(BASE)).json() == []
    other = (await intruder.post(BASE, json=small_draft())).json()
    # A task id from another user's roadmap is not found through your own roadmap.
    assert (await intruder.put(f"{BASE}/{other['id']}/tasks/{task}/done")).status_code == 404
    assert (await owner.get(url)).json()["progress"]["done"] == 0
