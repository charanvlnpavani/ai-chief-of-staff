"""Habits API: creation, idempotent check-ins, schedule versions, breaks, isolation."""

from datetime import timedelta

from httpx import AsyncClient

from app.core.time import local_today

TZ = "Asia/Kolkata"


def today_str(offset: int = 0) -> str:
    return (local_today(TZ) + timedelta(days=offset)).isoformat()


async def create_habit(client: AsyncClient, **overrides: object) -> dict[str, object]:
    payload = {"name": "Drink water", "measure": "count", "targetValue": 8, "unit": "glasses"}
    payload.update(overrides)
    response = await client.post("/api/v1/habits", json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


async def test_new_habit_shows_up_in_today_view(owner: AsyncClient) -> None:
    habit = await create_habit(owner)
    assert habit["schedule"]["frequency"] == "daily"  # type: ignore[index]
    today = (await owner.get("/api/v1/habits/today")).json()
    assert today["scheduled"] == 1
    assert today["completed"] == 0
    assert today["items"][0]["status"] == "pending"


async def test_check_in_is_idempotent_and_defaults_to_target(owner: AsyncClient) -> None:
    habit = await create_habit(owner)
    url = f"/api/v1/habits/{habit['id']}/completions/{today_str()}"
    first = await owner.put(url)
    second = await owner.put(url)
    assert first.status_code == second.status_code == 200
    assert second.json()["value"] == 8.0
    today = (await owner.get("/api/v1/habits/today")).json()
    assert today["completed"] == 1
    assert today["items"][0]["currentStreak"] == 1


async def test_partial_count_is_not_done_and_undo_clears(owner: AsyncClient) -> None:
    habit = await create_habit(owner)
    url = f"/api/v1/habits/{habit['id']}/completions/{today_str()}"
    await owner.put(url, json={"value": 5})
    assert (await owner.get("/api/v1/habits/today")).json()["items"][0]["done"] is False
    await owner.put(url, json={"value": 8})
    assert (await owner.get("/api/v1/habits/today")).json()["items"][0]["done"] is True
    assert (await owner.delete(url)).status_code == 204
    assert (await owner.get("/api/v1/habits/today")).json()["items"][0]["done"] is False


async def test_check_in_date_rules(owner: AsyncClient) -> None:
    habit = await create_habit(owner, startDate=today_str(-3))
    base = f"/api/v1/habits/{habit['id']}/completions"
    assert (await owner.put(f"{base}/{today_str(-1)}")).status_code == 200  # late, allowed
    future = await owner.put(f"{base}/{today_str(3)}")
    assert future.json()["code"] == "future_date"
    before = await owner.put(f"{base}/{today_str(-5)}")
    assert before.json()["code"] == "before_start"


async def test_streak_counts_backfilled_days(owner: AsyncClient) -> None:
    habit = await create_habit(owner, measure="check", startDate=today_str(-4))
    for offset in (-3, -2, -1, 0):
        await owner.put(f"/api/v1/habits/{habit['id']}/completions/{today_str(offset)}")
    detail = (await owner.get(f"/api/v1/habits/{habit['id']}")).json()
    assert detail["stats"]["currentStreak"] == 4
    assert detail["stats"]["missed"] == 1  # the start day itself was not done


async def test_schedule_change_opens_a_new_version(owner: AsyncClient) -> None:
    habit = await create_habit(owner, startDate=today_str(-10))
    change = await owner.post(
        f"/api/v1/habits/{habit['id']}/schedule",
        json={"schedule": {"frequency": "days_of_week", "daysOfWeek": [5, 1, 3]}},
    )
    assert change.status_code == 200, change.text
    schedule = change.json()["schedule"]
    assert schedule["frequency"] == "days_of_week"
    assert schedule["daysOfWeek"] == [1, 3, 5]
    assert schedule["validFrom"] == today_str()
    backdated = await owner.post(
        f"/api/v1/habits/{habit['id']}/schedule",
        json={"schedule": {"frequency": "daily"}, "effectiveFrom": today_str(-20)},
    )
    assert backdated.json()["code"] == "schedule_backdated"


async def test_invalid_schedule_is_rejected(owner: AsyncClient) -> None:
    response = await owner.post(
        "/api/v1/habits",
        json={"name": "Gym", "schedule": {"frequency": "n_per_week", "timesPerPeriod": 9}},
    )
    assert response.status_code == 422


async def test_a_break_keeps_the_streak_alive(owner: AsyncClient) -> None:
    habit = await create_habit(owner, measure="check", startDate=today_str(-4))
    base = f"/api/v1/habits/{habit['id']}/completions"
    await owner.put(f"{base}/{today_str(-4)}")
    await owner.put(f"{base}/{today_str(-3)}")
    created = await owner.post(
        "/api/v1/habit-exceptions",
        json={"startDate": today_str(-2), "endDate": today_str(-1), "kind": "sick"},
    )
    assert created.status_code == 201
    stats = (await owner.get(f"/api/v1/habits/{habit['id']}")).json()["stats"]
    assert stats["currentStreak"] == 2
    assert stats["excused"] == 2
    assert stats["missed"] == 0


async def test_history_returns_day_statuses(owner: AsyncClient) -> None:
    habit = await create_habit(owner, measure="check", startDate=today_str(-2))
    await owner.put(f"/api/v1/habits/{habit['id']}/completions/{today_str(-2)}")
    history = (
        await owner.get(
            f"/api/v1/habits/{habit['id']}/history",
            params={"from": today_str(-2), "to": today_str()},
        )
    ).json()
    assert [day["status"] for day in history["days"]] == ["met", "missed", "pending"]


async def test_other_users_cannot_see_or_check_in(
    owner: AsyncClient, intruder: AsyncClient
) -> None:
    habit = await create_habit(owner)
    assert (await intruder.get(f"/api/v1/habits/{habit['id']}")).status_code == 404
    url = f"/api/v1/habits/{habit['id']}/completions/{today_str()}"
    assert (await intruder.put(url)).status_code == 404
    assert (await intruder.get("/api/v1/habits")).json() == []
    exception = await intruder.post(
        "/api/v1/habit-exceptions",
        json={"habitId": habit["id"], "startDate": today_str(), "endDate": today_str()},
    )
    assert exception.status_code == 404
