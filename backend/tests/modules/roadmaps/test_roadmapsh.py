"""roadmap.sh links and local "learn more" notes.

All topic files here are synthetic. Real roadmap.sh content is licensed for personal use only
and must never be copied into this repository, including its tests.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import get_settings
from app.modules.roadmaps import roadmapsh

BASE = "/api/v1/roadmaps"

EFFECT_TOPIC = """\
# useEffect

A made-up note about effects for this test. It spans
two lines.

Visit the following resources to learn more:

- [@video@Some video](https://video.example/effects)
- [@article@Some article](https://article.example/effects)
- [@official@Official docs](https://docs.example/effects)
- [@unknown@Ignored kind](https://ignored.example)
- [@official@Not a web link](javascript:alert(1))
"""


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    content = tmp_path / "roadmaps" / "react" / "content"
    content.mkdir(parents=True)
    (content / "useeffect@abc.md").write_text(EFFECT_TOPIC, encoding="utf-8")
    (content / "components@def.md").write_text("# Components\n\nA made-up note.\n")
    (content / "custom-hooks@ghi.md").write_text("# Custom Hooks\n\nAnother made-up note.\n")
    (tmp_path / "roadmaps" / "datastructures-and-algorithms" / "content").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def use_clone(app: FastAPI, clone: Path):  # type: ignore[no-untyped-def]
    settings = get_settings().model_copy(update={"roadmap_sh_content_dir": str(clone)})
    app.dependency_overrides[get_settings] = lambda: settings
    yield clone
    app.dependency_overrides.pop(get_settings, None)


def test_subjects_map_to_roadmaps(clone: Path) -> None:
    assert roadmapsh.roadmap_slug("React") == "react"
    assert roadmapsh.roadmap_slug("  DSA ") == "datastructures-and-algorithms"
    assert roadmapsh.roadmap_slug("System design") == "system-design"  # built-in names
    assert roadmapsh.roadmap_slug("React hooks in depth") == "react"
    assert roadmapsh.roadmap_slug("Node.js") == "nodejs"
    assert roadmapsh.roadmap_slug("Cooking") is None
    # With a clone, only roadmaps that exist in it are used.
    assert roadmapsh.roadmap_slug("Python", str(clone)) is None
    assert roadmapsh.roadmap_name("datastructures-and-algorithms") == "Data Structures & Algorithms"


def test_topic_parsing_keeps_web_links_only() -> None:
    topic = roadmapsh.parse_topic(EFFECT_TOPIC)
    assert topic is not None
    assert topic.title == "useEffect"
    assert topic.summary == "A made-up note about effects for this test. It spans two lines."
    assert [r.kind for r in topic.resources] == ["official", "article", "video"]
    assert all(r.url.startswith("https://") for r in topic.resources)


def test_matching_prefers_the_concept_task() -> None:
    topics = tuple(
        t
        for t in (
            roadmapsh.parse_topic("# useEffect\n\nx"),
            roadmapsh.parse_topic("# Components\n\nx"),
            roadmapsh.parse_topic("# Custom Hooks\n\nx"),
        )
        if t
    )
    best = roadmapsh.best_topic(topics, ["useEffect cleanup and dependency arrays", "Components"])
    assert best is not None
    assert best.title == "useEffect"
    hooks = roadmapsh.best_topic(topics, ["Writing your own custom hooks"])
    assert hooks is not None
    assert hooks.title == "Custom Hooks"
    assert roadmapsh.best_topic(topics, ["Server rendering"]) is None


async def create_react(owner: AsyncClient, subject: str = "React") -> str:
    draft = {
        "subject": subject,
        "title": f"{subject} plan",
        "source": "ai",
        "days": [
            {
                "level": "basic",
                "tasks": [
                    {"title": "Understand: useEffect cleanup and dependency arrays"},
                    {"title": "Practise: a timer with cleanup"},
                ],
            },
            {"level": "basic", "tasks": [{"title": "Understand: server rendering"}]},
        ],
    }
    created = await owner.post(BASE, json=draft)
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


async def test_day_reference_with_a_local_clone(
    owner: AsyncClient, intruder: AsyncClient, use_clone: Path
) -> None:
    roadmap_id = await create_react(owner)
    response = await owner.get(f"{BASE}/{roadmap_id}/days/1/reference")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    ref = response.json()
    assert ref["roadmapName"] == "React"
    assert ref["roadmapUrl"] == "https://roadmap.sh/react"
    assert ref["localContent"] is True
    assert ref["topic"]["title"] == "useEffect"
    assert ref["topic"]["resources"][0] == {
        "kind": "official",
        "title": "Official docs",
        "url": "https://docs.example/effects",
    }
    unmatched = (await owner.get(f"{BASE}/{roadmap_id}/days/2/reference")).json()
    assert unmatched["topic"] is None
    assert unmatched["roadmapUrl"] == "https://roadmap.sh/react"  # the link is still offered
    assert (await owner.get(f"{BASE}/{roadmap_id}/days/9/reference")).status_code == 404
    assert (await intruder.get(f"{BASE}/{roadmap_id}/days/1/reference")).status_code == 404


async def test_day_reference_without_a_clone_offers_links_only(
    app: FastAPI, owner: AsyncClient
) -> None:
    # Explicitly no clone (a developer's own .env may point at one).
    settings = get_settings().model_copy(update={"roadmap_sh_content_dir": ""})
    app.dependency_overrides[get_settings] = lambda: settings
    roadmap_id = await create_react(owner, subject="System design")
    ref = (await owner.get(f"{BASE}/{roadmap_id}/days/1/reference")).json()
    assert ref == {
        "roadmapName": "System Design",
        "roadmapUrl": "https://roadmap.sh/system-design",
        "topic": None,
        "localContent": False,
    }
    app.dependency_overrides.pop(get_settings, None)


def test_labels_and_exact_names_in_matching() -> None:
    def topics(*titles: str) -> tuple[roadmapsh.Topic, ...]:
        return tuple(t for t in (roadmapsh.parse_topic(f"# {x}\n\nx") for x in titles) if t)

    # "Hook" only labels the topic; the day names the concept itself.
    found = roadmapsh.best_topic(topics("useEffect Hook", "Hooks"), ["useEffect cleanup"])
    assert found is not None
    assert found.title == "useEffect Hook"
    # Symbols are stripped, so both look like "big notation"; the exact name must win.
    big = roadmapsh.best_topic(topics("Big-Ω Notation", "Big O Notation"), ["Big-O notation"])
    assert big is not None
    assert big.title == "Big O Notation"
