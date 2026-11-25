"""Professional API: skills, learning sessions vs the daily goal, DSA problems and reviews."""

from datetime import timedelta

from httpx import AsyncClient

from app.core.time import local_today

TZ = "Asia/Kolkata"


def day(offset: int = 0) -> str:
    return (local_today(TZ) + timedelta(days=offset)).isoformat()


async def log(
    client: AsyncClient, minutes: int, offset: int = 0, **fields: object
) -> dict[str, object]:
    payload: dict[str, object] = {
        "durationMin": minutes,
        "topic": "Graphs",
        "localDate": day(offset),
    }
    payload.update(fields)
    response = await client.post("/api/v1/professional/learning-sessions", json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


async def test_skills_are_unique_per_user_and_report_recent_minutes(owner: AsyncClient) -> None:
    skill = (
        await owner.post(
            "/api/v1/professional/skills", json={"name": "Dynamic Programming", "category": "dsa"}
        )
    ).json()
    duplicate = await owner.post(
        "/api/v1/professional/skills", json={"name": "dynamic programming"}
    )
    assert duplicate.status_code == 409
    await log(owner, 45, skillId=skill["id"])
    await log(owner, 30, offset=-40, skillId=skill["id"])  # outside the 30-day window
    skills = (await owner.get("/api/v1/professional/skills")).json()
    assert skills[0]["minutesLast30Days"] == 45


async def test_learning_summary_tracks_the_daily_goal(owner: AsyncClient) -> None:
    await owner.patch("/api/v1/users/me/settings", json={"dailyLearningGoalMinutes": 60})
    await log(owner, 70, offset=-2)
    await log(owner, 30, offset=-1)
    await log(owner, 35, offset=-1)  # 65 total that day
    await log(owner, 20, offset=0)  # today, still in progress
    summary = (
        await owner.get(
            "/api/v1/professional/learning-sessions/summary",
            params={"from": day(-2), "to": day(0)},
        )
    ).json()
    assert summary["totalMinutes"] == 155
    assert summary["todayMinutes"] == 20
    assert summary["goalDaysMet"] == 2
    assert summary["currentGoalStreak"] == 2  # today does not break it yet
    assert [d["minutes"] for d in summary["daily"]] == [70, 65, 20]
    assert summary["bySkill"][0]["skillName"] == "Unassigned"


async def test_future_sessions_are_rejected(owner: AsyncClient) -> None:
    response = await owner.post(
        "/api/v1/professional/learning-sessions",
        json={"durationMin": 30, "topic": "x", "localDate": day(5)},
    )
    assert response.json()["code"] == "future_date"


async def test_problem_slug_is_normalised_and_unique(owner: AsyncClient) -> None:
    created = await owner.post(
        "/api/v1/professional/problems",
        json={
            "slug": "Two Sum",
            "title": "Two Sum",
            "difficulty": "easy",
            "topics": ["Array", "array", "Hashing "],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["slug"] == "two-sum"
    assert body["topics"] == ["array", "hashing"]
    again = await owner.post(
        "/api/v1/professional/problems", json={"slug": "two-sum", "title": "Dup"}
    )
    assert again.status_code == 409


async def test_attempts_drive_spaced_review(owner: AsyncClient) -> None:
    problem = (
        await owner.post(
            "/api/v1/professional/problems", json={"slug": "lru-cache", "title": "LRU Cache"}
        )
    ).json()
    url = f"/api/v1/professional/problems/{problem['id']}/attempts"
    first = (await owner.post(url, json={"outcome": "solved", "minutes": 40})).json()
    assert first["status"] == "solved"
    assert first["nextReviewOn"] == day(1)
    assert first["reviewStage"] == 1
    second = (await owner.post(url, json={"outcome": "solved", "minutes": 10})).json()
    assert second["nextReviewOn"] == day(3)
    failed = (await owner.post(url, json={"outcome": "failed"})).json()
    assert failed["status"] == "revisit"
    assert failed["reviewStage"] == 0
    assert failed["nextReviewOn"] == day(1)
    assert failed["attempts"] == 3
    assert failed["timeSpentMin"] == 50


async def test_review_queue_and_stats(owner: AsyncClient) -> None:
    due = (
        await owner.post(
            "/api/v1/professional/problems",
            json={
                "slug": "course-schedule",
                "title": "Course Schedule",
                "topics": ["graph"],
                "difficulty": "medium",
            },
        )
    ).json()
    await owner.patch(f"/api/v1/professional/problems/{due['id']}", json={"nextReviewOn": day(-1)})
    await owner.post(
        "/api/v1/professional/problems",
        json={
            "slug": "valid-parentheses",
            "title": "Valid Parentheses",
            "topics": ["stack", "graph"],
            "status": "solved",
            "difficulty": "easy",
        },
    )
    queue = (await owner.get("/api/v1/professional/problems/review-queue")).json()
    assert [p["slug"] for p in queue] == ["course-schedule"]
    stats = (await owner.get("/api/v1/professional/problems/stats")).json()
    assert stats["total"] == 2
    assert stats["byStatus"]["solved"] == 1
    assert stats["solvedByDifficulty"]["easy"] == 1
    assert stats["solvedThisWeek"] == 1
    assert stats["dueForReview"] == 1
    assert stats["topTopics"][0] == {"topic": "graph", "count": 2}


async def test_filters_by_topic_and_status(owner: AsyncClient) -> None:
    await owner.post(
        "/api/v1/professional/problems", json={"slug": "a", "title": "A", "topics": ["tree"]}
    )
    await owner.post(
        "/api/v1/professional/problems", json={"slug": "b", "title": "B", "topics": ["heap"]}
    )
    by_topic = (await owner.get("/api/v1/professional/problems", params={"topic": "Tree"})).json()
    assert [p["slug"] for p in by_topic["items"]] == ["a"]


async def test_other_users_cannot_access_professional_data(
    owner: AsyncClient, intruder: AsyncClient
) -> None:
    skill = (await owner.post("/api/v1/professional/skills", json={"name": "Go"})).json()
    session = await log(owner, 30)
    problem = (
        await owner.post("/api/v1/professional/problems", json={"slug": "x", "title": "X"})
    ).json()
    assert (
        await intruder.patch(f"/api/v1/professional/skills/{skill['id']}", json={"level": 5})
    ).status_code == 404
    assert (
        await intruder.delete(f"/api/v1/professional/learning-sessions/{session['id']}")
    ).status_code == 404
    assert (await intruder.get(f"/api/v1/professional/problems/{problem['id']}")).status_code == 404
    borrowed = await intruder.post(
        "/api/v1/professional/learning-sessions",
        json={"durationMin": 10, "topic": "x", "skillId": skill["id"]},
    )
    assert borrowed.status_code == 404
    assert (await intruder.get("/api/v1/professional/skills")).json() == []
