"""Goals API: creation, milestones, check-ins, history that survives target edits, isolation."""

import uuid
from datetime import datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import local_today

TZ = "Asia/Kolkata"


def day(offset: int = 0) -> str:
    return (local_today(TZ) + timedelta(days=offset)).isoformat()


async def create_goal(client: AsyncClient, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "Read 24 books",
        "progressRule": "numeric",
        "startValue": 0,
        "targetValue": 24,
        "unit": "books",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/goals", json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


async def test_numeric_goal_progress_comes_from_latest_check_in(owner: AsyncClient) -> None:
    goal = await create_goal(owner, startDate=day(-10))
    assert goal["progress"]["percent"] == 0.0  # type: ignore[index]
    url = f"/api/v1/goals/{goal['id']}/check-ins"
    assert (await owner.post(url, json={"value": 3, "localDate": day(-5)})).status_code == 201
    latest = await owner.post(url, json={"value": 6, "note": "Finished Dune"})
    progress = latest.json()["progress"]
    assert progress["currentValue"] == 6.0
    assert progress["percent"] == 0.25
    assert progress["lastCheckIn"] == day()
    # A backfilled check-in for an earlier day does not override the latest value.
    await owner.post(url, json={"value": 1, "localDate": day(-8)})
    detail = (await owner.get(f"/api/v1/goals/{goal['id']}")).json()
    assert detail["progress"]["currentValue"] == 6.0
    assert [e["value"] for e in detail["entries"]] == [6.0, 3.0, 1.0]


async def test_milestone_goal_progress(owner: AsyncClient) -> None:
    goal = await create_goal(
        owner,
        title="Launch side project",
        progressRule="milestones",
        targetValue=None,
        milestones=[{"title": "Spec"}, {"title": "MVP"}, {"title": "Beta"}, {"title": "Launch"}],
    )
    assert goal["targetValue"] is None
    milestones = goal["milestones"]
    assert [m["title"] for m in milestones] == ["Spec", "MVP", "Beta", "Launch"]  # type: ignore[union-attr]
    first = milestones[0]["id"]  # type: ignore[index]
    ticked = await owner.patch(
        f"/api/v1/goals/{goal['id']}/milestones/{first}", json={"done": True}
    )
    assert ticked.json()["progress"]["percent"] == 0.25
    assert ticked.json()["progress"]["milestonesDone"] == 1
    added = await owner.post(f"/api/v1/goals/{goal['id']}/milestones", json={"title": "Retro"})
    assert added.json()["progress"]["percent"] == 0.2
    value = await owner.post(f"/api/v1/goals/{goal['id']}/check-ins", json={"value": 2})
    assert value.json()["code"] == "value_not_allowed"
    note = await owner.post(
        f"/api/v1/goals/{goal['id']}/check-ins", json={"note": "Spec signed off"}
    )
    assert note.status_code == 201


async def test_editing_the_target_keeps_history(owner: AsyncClient) -> None:
    goal = await create_goal(owner)
    url = f"/api/v1/goals/{goal['id']}"
    await owner.post(f"{url}/check-ins", json={"value": 6})
    edited = (await owner.patch(url, json={"targetValue": 12, "version": goal["version"]})).json()
    assert edited["progress"]["percent"] == 0.5  # same activity, new target
    kinds = [e["kind"] for e in edited["entries"]]
    assert kinds.count("check_in") == 1
    assert kinds.count("target_change") == 1
    change = next(e for e in edited["entries"] if e["kind"] == "target_change")
    assert change["note"] == "Target was 0 → 24 books"
    check_in = next(e for e in edited["entries"] if e["kind"] == "check_in")
    assert check_in["value"] == 6.0
    assert check_in["targetValue"] == 24.0  # snapshot of the target at the time


async def test_stale_version_is_rejected(owner: AsyncClient) -> None:
    goal = await create_goal(owner)
    url = f"/api/v1/goals/{goal['id']}"
    assert (
        await owner.patch(url, json={"title": "A", "version": goal["version"]})
    ).status_code == 200
    stale = await owner.patch(url, json={"title": "B", "version": goal["version"]})
    assert stale.json()["code"] == "version_conflict"


async def test_status_changes_and_health(owner: AsyncClient) -> None:
    # Half the time gone, nothing done: at risk.
    goal = await create_goal(owner, startDate=day(-50), targetDate=day(50))
    assert goal["progress"]["health"] == "at_risk"  # type: ignore[index]
    url = f"/api/v1/goals/{goal['id']}"
    on_track = (await owner.post(f"{url}/check-ins", json={"value": 12})).json()
    assert on_track["progress"]["health"] == "on_track"
    paused = (await owner.patch(url, json={"status": "paused"})).json()
    assert paused["progress"]["health"] == "paused"
    done = (await owner.patch(url, json={"status": "completed"})).json()
    assert done["completedAt"] is not None
    assert done["progress"]["health"] == "completed"
    archived = (await owner.patch(url, json={"status": "archived"})).json()
    assert archived["progress"]["health"] == "archived"
    assert (await owner.get("/api/v1/goals")).json() == []
    assert len((await owner.get("/api/v1/goals", params={"include_archived": "true"})).json()) == 1
    reopened = (await owner.patch(url, json={"status": "active"})).json()
    assert reopened["completedAt"] is None


async def test_archiving_a_completed_goal_keeps_its_completion_time(owner: AsyncClient) -> None:
    goal = await create_goal(owner)
    url = f"/api/v1/goals/{goal['id']}"
    done = (await owner.patch(url, json={"status": "completed"})).json()
    archived = (await owner.patch(url, json={"status": "archived"})).json()
    completed_at = datetime.fromisoformat(done["completedAt"])
    assert datetime.fromisoformat(archived["completedAt"]) == completed_at
    again = (await owner.patch(url, json={"status": "completed"})).json()
    assert datetime.fromisoformat(again["completedAt"]) == completed_at  # not re-stamped


async def test_sub_cent_values_are_rejected_not_a_server_error(owner: AsyncClient) -> None:
    rounding = await owner.post(
        "/api/v1/goals",
        json={"title": "X", "progressRule": "numeric", "startValue": 0, "targetValue": 0.001},
    )
    assert rounding.status_code == 422
    huge_exponent = await owner.post(
        "/api/v1/goals",
        json={"title": "X", "progressRule": "numeric", "targetValue": "1e-999999"},
    )
    assert huge_exponent.status_code == 422
    goal = await create_goal(owner)
    url = f"/api/v1/goals/{goal['id']}"
    assert (await owner.patch(url, json={"targetValue": 0.001})).status_code == 422
    assert (await owner.post(f"{url}/check-ins", json={"value": 1.005})).status_code == 422


async def test_switching_to_milestones_clears_the_numeric_target(owner: AsyncClient) -> None:
    goal = await create_goal(owner)
    switched = (
        await owner.patch(f"/api/v1/goals/{goal['id']}", json={"progressRule": "milestones"})
    ).json()
    assert switched["targetValue"] is None
    assert any(e["kind"] == "target_change" for e in switched["entries"])


async def test_validation_rules(owner: AsyncClient) -> None:
    no_target = await owner.post("/api/v1/goals", json={"title": "X", "progressRule": "numeric"})
    assert no_target.status_code == 422
    same = await owner.post(
        "/api/v1/goals", json={"title": "X", "progressRule": "numeric", "targetValue": 0}
    )
    assert same.status_code == 422
    goal = await create_goal(owner, startDate=day(-3))
    url = f"/api/v1/goals/{goal['id']}/check-ins"
    assert (await owner.post(url, json={})).status_code == 422
    assert (await owner.post(url, json={"value": 1, "localDate": day(1)})).json()[
        "code"
    ] == "future_date"
    assert (await owner.post(url, json={"value": 1, "localDate": day(-4)})).json()[
        "code"
    ] == "before_start"
    bad_date = await owner.patch(f"/api/v1/goals/{goal['id']}", json={"targetDate": day(-10)})
    assert bad_date.json()["code"] == "date_order"


async def test_delete_hides_the_goal(owner: AsyncClient) -> None:
    goal = await create_goal(owner)
    assert (await owner.delete(f"/api/v1/goals/{goal['id']}")).status_code == 204
    assert (await owner.get(f"/api/v1/goals/{goal['id']}")).status_code == 404
    assert (await owner.get("/api/v1/goals")).json() == []


async def test_other_users_cannot_see_or_change_goals(
    owner: AsyncClient, intruder: AsyncClient
) -> None:
    goal = await create_goal(owner, progressRule="milestones", milestones=[{"title": "One"}])
    url = f"/api/v1/goals/{goal['id']}"
    milestone = goal["milestones"][0]["id"]  # type: ignore[index]
    assert (await intruder.get(url)).status_code == 404
    assert (await intruder.patch(url, json={"title": "mine"})).status_code == 404
    assert (await intruder.delete(url)).status_code == 404
    assert (await intruder.post(f"{url}/check-ins", json={"note": "hi"})).status_code == 404
    assert (await intruder.post(f"{url}/milestones", json={"title": "x"})).status_code == 404
    patched = await intruder.patch(f"{url}/milestones/{milestone}", json={"done": True})
    assert patched.status_code == 404
    assert (await intruder.get("/api/v1/goals")).json() == []
    assert (await owner.get(url)).json()["progress"]["milestonesDone"] == 0


async def test_archived_goal_is_read_only_until_restored(owner: AsyncClient) -> None:
    goal = await create_goal(owner, progressRule="milestones", milestones=[{"title": "One"}])
    url = f"/api/v1/goals/{goal['id']}"
    milestone = goal["milestones"][0]["id"]  # type: ignore[index]
    await owner.patch(url, json={"status": "archived"})
    blocked = [
        await owner.post(f"{url}/check-ins", json={"note": "hi"}),
        await owner.post(f"{url}/milestones", json={"title": "Two"}),
        await owner.patch(f"{url}/milestones/{milestone}", json={"done": True}),
        await owner.delete(f"{url}/milestones/{milestone}"),
        await owner.patch(url, json={"title": "Renamed"}),
    ]
    assert [r.json()["code"] for r in blocked] == ["goal_archived"] * 5
    restored = await owner.patch(url, json={"status": "active"})
    assert restored.status_code == 200
    assert (await owner.post(f"{url}/check-ins", json={"note": "back"})).status_code == 201


async def test_more_guard_rules(owner: AsyncClient) -> None:
    old = await create_goal(owner, startDate=day(-400))
    too_old = await owner.post(
        f"/api/v1/goals/{old['id']}/check-ins", json={"value": 1, "localDate": day(-380)}
    )
    assert too_old.json()["code"] == "too_old"
    full = await create_goal(
        owner, progressRule="milestones", milestones=[{"title": f"M{i}"} for i in range(50)]
    )
    too_many = await owner.post(f"/api/v1/goals/{full['id']}/milestones", json={"title": "51"})
    assert too_many.json()["code"] == "too_many"
    plan = await create_goal(owner, progressRule="milestones")
    no_target = await owner.patch(f"/api/v1/goals/{plan['id']}", json={"progressRule": "numeric"})
    assert no_target.json()["code"] == "target_required"


async def test_delete_milestone_and_ownership(owner: AsyncClient, intruder: AsyncClient) -> None:
    first = await create_goal(owner, progressRule="milestones", milestones=[{"title": "A"}])
    second = await create_goal(owner, progressRule="milestones", milestones=[{"title": "B"}])
    a = first["milestones"][0]["id"]  # type: ignore[index]
    # A milestone can only be reached through its own goal, even for the same user.
    wrong_goal = await owner.delete(f"/api/v1/goals/{second['id']}/milestones/{a}")
    assert wrong_goal.status_code == 404
    assert (await intruder.delete(f"/api/v1/goals/{first['id']}/milestones/{a}")).status_code == 404
    removed = await owner.delete(f"/api/v1/goals/{first['id']}/milestones/{a}")
    assert removed.json()["milestones"] == []
    # New milestones go after the highest existing position, not at the old count.
    goal = await create_goal(
        owner, progressRule="milestones", milestones=[{"title": "X"}, {"title": "Y"}]
    )
    x = goal["milestones"][0]["id"]  # type: ignore[index]
    await owner.delete(f"/api/v1/goals/{goal['id']}/milestones/{x}")
    added = (await owner.post(f"/api/v1/goals/{goal['id']}/milestones", json={"title": "Z"})).json()
    assert [(m["title"], m["sortOrder"]) for m in added["milestones"]] == [("Y", 1), ("Z", 2)]


async def test_milestone_goal_without_milestones_is_not_started(owner: AsyncClient) -> None:
    goal = await create_goal(
        owner, progressRule="milestones", startDate=day(-50), targetDate=day(50)
    )
    assert goal["progress"]["health"] == "not_started"  # type: ignore[index]
    added = await owner.post(f"/api/v1/goals/{goal['id']}/milestones", json={"title": "Plan"})
    assert added.json()["progress"]["health"] == "at_risk"  # half the time gone, 0 of 1 done


async def test_history_is_paged(owner: AsyncClient) -> None:
    goal = await create_goal(owner, startDate=day(-100))
    url = f"/api/v1/goals/{goal['id']}"
    for offset in range(-55, 0):
        await owner.post(f"{url}/check-ins", json={"value": 60 + offset, "localDate": day(offset)})
    detail = (await owner.get(url)).json()
    assert len(detail["entries"]) == 50
    assert detail["progress"]["currentValue"] == 59.0  # latest day, from SQL not the page
    older = (
        await owner.get(f"{url}/entries", params={"cursor": detail["entriesNextCursor"]})
    ).json()
    assert [e["localDate"] for e in older["items"]] == [day(o) for o in range(-51, -56, -1)]
    assert older["nextCursor"] is None


async def test_large_values_keep_exact_history_text(owner: AsyncClient) -> None:
    goal = await create_goal(owner, startValue=0, targetValue=1234567.89, unit="INR")
    edited = (
        await owner.patch(f"/api/v1/goals/{goal['id']}", json={"targetValue": 2000000})
    ).json()
    change = next(e for e in edited["entries"] if e["kind"] == "target_change")
    assert change["note"] == "Target was 0 → 1234567.89 INR"


async def test_get_goals_tool_output(owner: AsyncClient, db_session: AsyncSession) -> None:
    from app.ai.registry import ToolContext
    from app.modules.goals import ai_tools

    numeric = await create_goal(owner, startDate=day(-10), targetDate=day(10))
    await owner.post(f"/api/v1/goals/{numeric['id']}/check-ins", json={"value": 6})
    await create_goal(
        owner, title="Ship app", progressRule="milestones", milestones=[{"title": "MVP"}]
    )
    user_id = (await owner.get("/api/v1/users/me")).json()["user"]["id"]
    ctx = ToolContext(
        session=db_session, user_id=uuid.UUID(user_id), timezone=TZ, today=local_today(TZ)
    )
    result = await ai_tools.get_goals(ctx, ai_tools.NoInput())
    books, ship = sorted(result["goals"], key=lambda g: g["title"])
    assert books["progress_percent"] == 25
    assert books["current_value"] == 6.0
    assert books["target_value"] == 24.0
    assert books["days_left"] == 10
    assert ship["milestones"] == "0/1"
    assert ship["start_value"] is None
    assert ship["target_value"] is None
