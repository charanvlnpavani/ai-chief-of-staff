"""Roadmaps API: built-in and AI drafts, daily ticks, completion, guards and isolation."""

import asyncio
import re
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.models import AIUsageLedger
from app.ai.pricing import Usage
from app.core.time import local_today
from app.modules.roadmaps import jobs as roadmap_jobs
from app.modules.roadmaps import router as roadmaps_router
from app.modules.roadmaps.drafting import split_days
from app.modules.roadmaps.generator import AIReply
from app.modules.roadmaps.schemas import (
    PlannedDay,
    PlannedDays,
    PlannedOutline,
    PlannedOutlineLevel,
    PlannedTask,
    PlannedTopicList,
)

TZ = "Asia/Kolkata"
BASE = "/api/v1/roadmaps"


def day(offset: int = 0) -> str:
    return (local_today(TZ) + timedelta(days=offset)).isoformat()


class FakeGenerator:
    """Scripted stand-in for the model: never calls a provider.

    Knobs imitate a weak model: `outline_per_level` caps the concepts it outlines per level,
    `skip_first_try` drops the last day of every first expand reply, and `never_write` lists
    concepts it never expands.
    """

    def __init__(self, *, refuse: bool = False) -> None:
        self.refuse = refuse
        self.outline_per_level: int | None = None
        self.skip_first_try = False
        self.never_write: set[str] = set()
        self.gate: asyncio.Event | None = None  # when set, every call waits for it
        self.calls: list[str] = []
        self._expanded: set[str] = set()

    async def complete[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], max_tokens: int
    ) -> AIReply[T]:
        if self.gate is not None:
            await self.gate.wait()
        self.calls.append(schema.__name__)
        parsed: BaseModel | None = None
        if self.refuse:
            pass
        elif schema is PlannedOutline:
            counts = dict(re.findall(r"- (basic|intermediate|advanced|pro): (\d+) days", user))
            parsed = PlannedOutline(
                title="  System design:   zero to pro ",
                levels=[
                    PlannedOutlineLevel(
                        level=lv,
                        topics=[f"{lv} concept {i}" for i in range(1, int(counts[lv]) + 1)][
                            : self.outline_per_level
                        ],
                    )
                    # Deliberately out of order: the drafter must sort levels.
                    for lv in ("advanced", "basic", "pro", "intermediate")
                ],
            )
        elif schema is PlannedTopicList:
            n, lv = re.search(r"Give exactly (\d+) more (\w+)-level", user).groups()  # type: ignore[union-attr]
            # Includes a duplicate of an existing concept, which must be dropped.
            parsed = PlannedTopicList(
                topics=[f"{lv} concept 1"] + [f"{lv} extra {i}" for i in range(1, int(n) + 1)]
            )
        elif schema is PlannedDays:
            wanted = re.findall(r"^Day \d+: (.+)$", user, flags=re.MULTILINE)
            first_try = not any(topic in self._expanded for topic in wanted)
            self._expanded.update(wanted)
            if self.skip_first_try and first_try:
                wanted = wanted[:-1]
            parsed = PlannedDays(
                days=[
                    PlannedDay(
                        topic=topic,
                        tasks=[
                            PlannedTask(title=f"Understand: {topic}", detail="  Why.  ", minutes=1),
                            PlannedTask(title=f"Practise: {topic}", detail="Do it.", minutes=1),
                            PlannedTask(title=f"Check yourself: {topic}?", detail="", minutes=1),
                        ],
                    )
                    for topic in wanted
                    if topic not in self.never_write
                ]
            )
        return AIReply(
            parsed=cast(T | None, parsed),
            refused=self.refuse,
            model="claude-opus-5-5",
            usage=Usage(
                input_tokens=1000, output_tokens=2000, cache_read_tokens=0, cache_write_tokens=0
            ),
            request_id="req_test",
        )


def task_titles(draft: dict[str, Any]) -> list[str]:
    return [d["tasks"][0]["title"] for d in draft["days"]]


@pytest.fixture
def fake_generator(app: FastAPI) -> Iterator[FakeGenerator]:
    fake = FakeGenerator()
    app.dependency_overrides[roadmaps_router._optional_generator] = lambda: fake
    yield fake
    app.dependency_overrides.pop(roadmaps_router._optional_generator, None)


@pytest.fixture(autouse=True)
def no_leftover_jobs() -> Iterator[None]:
    roadmap_jobs._jobs.clear()
    yield
    roadmap_jobs._jobs.clear()


async def finish_job(job_id: str) -> None:
    """Wait for a background draft to finish (the fake model answers instantly)."""
    task = roadmap_jobs._jobs[uuid.UUID(job_id)].task
    if task is not None:
        await task


async def test_draft_job_runs_in_the_background(
    owner: AsyncClient,
    intruder: AsyncClient,
    fake_generator: FakeGenerator,
    db_session: AsyncSession,
) -> None:
    await owner.put("/api/v1/users/me/consents/ai_processing", json={"granted": True})
    fake_generator.gate = asyncio.Event()  # hold the job while we look at it
    request = {"subject": "System design", "targetDays": 30, "minutesPerDay": 45}
    started = await owner.post(f"{BASE}/draft-jobs", json=request)
    assert started.status_code == 202
    job = started.json()
    assert (job["status"], job["stage"], job["daysTotal"], job["draft"]) == (
        "running",
        "outline",
        0,
        None,
    )
    busy = await owner.post(f"{BASE}/draft-jobs", json=request)
    assert busy.json()["code"] == "draft_in_progress"  # one draft at a time
    assert (await intruder.get(f"{BASE}/draft-jobs/{job['id']}")).status_code == 404

    fake_generator.gate.set()
    await finish_job(job["id"])
    done = (await owner.get(f"{BASE}/draft-jobs/{job['id']}")).json()
    assert (done["status"], done["stage"], done["daysDone"], done["daysTotal"]) == (
        "done",
        "done",
        30,
        30,
    )
    assert done["error"] is None
    assert len(done["draft"]["days"]) == 30
    assert (await owner.post(BASE, json=done["draft"])).status_code == 201
    rows = list(
        await db_session.scalars(select(AIUsageLedger).where(AIUsageLedger.route == "roadmap"))
    )
    assert len(rows) == len(fake_generator.calls) == 8  # billed from the job's own session


async def test_draft_job_failure_is_reported_and_costed(
    owner: AsyncClient, fake_generator: FakeGenerator, db_session: AsyncSession
) -> None:
    fake_generator.refuse = True
    await owner.put("/api/v1/users/me/consents/ai_processing", json={"granted": True})
    job = (await owner.post(f"{BASE}/draft-jobs", json={"subject": "Something"})).json()
    await finish_job(job["id"])
    failed = (await owner.get(f"{BASE}/draft-jobs/{job['id']}")).json()
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "ai_refused"
    assert failed["draft"] is None
    rows = list(
        await db_session.scalars(select(AIUsageLedger).where(AIUsageLedger.route == "roadmap"))
    )
    assert len(rows) == 1


async def test_draft_job_gates_and_built_ins(owner: AsyncClient) -> None:
    # Gates are checked when the job starts, so the page can explain them straight away.
    missing = await owner.post(f"{BASE}/draft-jobs", json={"subject": "Rust"})
    assert missing.json()["code"] == "ai_key_required"
    # A built-in roadmap needs no AI and comes back finished.
    built_in = (await owner.post(f"{BASE}/draft-jobs", json={"subject": "dsa"})).json()
    assert built_in["status"] == "done"
    assert built_in["draft"]["source"] == "template"
    assert built_in["daysDone"] == built_in["daysTotal"] == len(built_in["draft"]["days"])
    unknown = await owner.get(f"{BASE}/draft-jobs/{uuid.uuid4()}")
    assert unknown.status_code == 404


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
    # The full 30 days, split 30/30/25/15 % and sorted, never trusted as given.
    assert [d["level"] for d in draft["days"]] == ["basic"] * 9 + ["intermediate"] * 9 + [
        "advanced"
    ] * 8 + ["pro"] * 4
    assert task_titles(draft)[:2] == ["Understand: basic concept 1", "Understand: basic concept 2"]
    assert task_titles(draft)[-1] == "Understand: pro concept 4"
    first_day = draft["days"][0]["tasks"]
    assert [t["title"].split(":")[0] for t in first_day] == [
        "Understand",
        "Practise",
        "Check yourself",
    ]
    assert first_day[0]["detail"] == "Why."
    assert first_day[2]["detail"] is None
    # 1-minute tasks are clamped, then scaled to the 45 minutes a day the learner has.
    assert [t["minutes"] for t in first_day] == [15, 15, 15]
    # One outline call plus one expand call per batch of up to 7 days (2 + 2 + 2 + 1).
    assert fake_generator.calls == ["PlannedOutline"] + ["PlannedDays"] * 7
    rows = list(
        await db_session.scalars(select(AIUsageLedger).where(AIUsageLedger.route == "roadmap"))
    )
    assert len(rows) == len(fake_generator.calls)  # every call is costed
    assert all(row.cost_usd_micros > 0 for row in rows)
    # Saving the AI draft works like any other draft.
    assert (await owner.post(BASE, json=draft)).status_code == 201


async def test_ai_refusal_is_still_costed(
    owner: AsyncClient, fake_generator: FakeGenerator, db_session: AsyncSession
) -> None:
    fake_generator.refuse = True
    await owner.put("/api/v1/users/me/consents/ai_processing", json={"granted": True})
    refused = await owner.post(f"{BASE}/draft", json={"subject": "Something"})
    assert refused.json()["code"] == "ai_refused"
    assert fake_generator.calls == ["PlannedOutline"]  # stops at the refusal
    rows = list(
        await db_session.scalars(select(AIUsageLedger).where(AIUsageLedger.route == "roadmap"))
    )
    assert len(rows) == 1


async def test_a_weak_model_still_gets_the_full_roadmap(
    owner: AsyncClient, fake_generator: FakeGenerator, db_session: AsyncSession
) -> None:
    """Small local models outline too few days and skip days; the draft is still complete."""
    fake_generator.outline_per_level = 2
    fake_generator.skip_first_try = True
    fake_generator.never_write = {"intermediate extra 3"}
    await owner.put("/api/v1/users/me/consents/ai_processing", json={"granted": True})
    request = {"subject": "React", "targetDays": 45, "minutesPerDay": 60}
    draft = (await owner.post(f"{BASE}/draft", json=request)).json()

    assert len(draft["days"]) == 45  # what the learner asked for, not a one-week sketch
    levels = [d["level"] for d in draft["days"]]
    assert {lv: levels.count(lv) for lv in dict.fromkeys(levels)} == {
        "basic": 14,
        "intermediate": 13,
        "advanced": 11,
        "pro": 7,
    }
    titles = task_titles(draft)
    assert len(set(titles)) == 45  # the duplicate concept from the top-up was dropped
    assert titles[:3] == [
        "Understand: basic concept 1",
        "Understand: basic concept 2",
        "Understand: basic extra 1",
    ]
    # A day the model never wrote gets plain, concrete tasks instead of disappearing.
    fallback = next(
        d["tasks"] for d in draft["days"] if "intermediate extra 3" in d["tasks"][0]["title"]
    )
    assert [t["title"].split(":")[0] for t in fallback] == [
        "Understand",
        "Practise",
        "Check yourself",
    ]
    assert sum(t["minutes"] for t in fallback) == 60
    assert fake_generator.calls.count("PlannedTopicList") == 4  # one top-up per short level
    rows = list(
        await db_session.scalars(select(AIUsageLedger).where(AIUsageLedger.route == "roadmap"))
    )
    assert len(rows) == len(fake_generator.calls)


@pytest.mark.parametrize("total", [7, 8, 30, 45, 100, 180])
def test_split_days(total: int) -> None:
    counts = split_days(total)
    assert list(counts) == ["basic", "intermediate", "advanced", "pro"]
    assert sum(counts.values()) == max(total, 8)
    assert min(counts.values()) >= 2
    assert counts["basic"] >= counts["advanced"] >= counts["pro"]


async def test_ai_budget_and_missing_key(
    owner: AsyncClient, app: FastAPI, db_session: AsyncSession
) -> None:
    # No ANTHROPIC_API_KEY in tests: new subjects explain why, built-ins still work.
    missing = await owner.post(f"{BASE}/draft", json={"subject": "Rust"})
    assert missing.json()["code"] == "ai_key_required"
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


async def test_a_running_draft_can_be_found_and_cancelled(
    owner: AsyncClient, fake_generator: FakeGenerator, db_session: AsyncSession
) -> None:
    await owner.put("/api/v1/users/me/consents/ai_processing", json={"granted": True})
    fake_generator.gate = asyncio.Event()  # the model never answers until released
    job = (await owner.post(f"{BASE}/draft-jobs", json={"subject": "React"})).json()
    busy = (await owner.post(f"{BASE}/draft-jobs", json={"subject": "Go"})).json()
    assert busy["code"] == "draft_in_progress"
    assert busy["jobId"] == job["id"]  # the page shows this draft instead of an error
    assert "React" in busy["detail"]

    cancelled = (await owner.delete(f"{BASE}/draft-jobs/{job['id']}")).json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["draft"] is None
    # Cancelling frees the slot for a new draft.
    fake_generator.gate.set()
    again = await owner.post(f"{BASE}/draft-jobs", json={"subject": "Go"})
    assert again.status_code == 202
    await finish_job(again.json()["id"])
