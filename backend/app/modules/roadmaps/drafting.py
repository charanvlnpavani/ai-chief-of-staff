"""Turn any subject into a complete basic-to-pro roadmap draft, in two stages.

1. Outline: one named concept per day, split across the levels (30 % basic, 30 %
   intermediate, 25 % advanced, 15 % pro). Each level ends with a project or review day.
2. Expand: batches of outline days become clear daily tasks, "Understand" (what, why, an
   example), "Practise" (hands-on, with a finish line) and "Check yourself" (a question to
   answer without notes), so each concept is learned rather than skimmed.

Why two stages: asked for a whole roadmap in one reply, small models (for example llama3.2
on Ollama) stop after about a week and keep every day shallow. Here every call is small,
day counts are checked in code, short levels get one top-up request, skipped days get one
retry, and any day still missing gets plain, deterministic tasks. The draft therefore
always has the number of days the learner asked for, never a silent one-week sketch.
"""

import asyncio
import math
from collections.abc import Awaitable, Iterable
from typing import Any, Literal

from pydantic import BaseModel

from app.core.errors import ServiceUnavailable
from app.modules.roadmaps.generator import AIReply, RoadmapGenerator
from app.modules.roadmaps.schemas import (
    MAX_TASKS_PER_DAY,
    DraftDay,
    DraftTask,
    Level,
    PlannedDay,
    PlannedDays,
    PlannedOutline,
    PlannedTopicList,
    RoadmapDraft,
)

ORDER: tuple[Level, ...] = ("basic", "intermediate", "advanced", "pro")
LEVEL_SHARE: dict[Level, float] = {
    "basic": 0.30,
    "intermediate": 0.30,
    "advanced": 0.25,
    "pro": 0.15,
}
MIN_DAYS_PER_LEVEL = 2
BATCH_DAYS = 7  # days expanded per call: small enough for local models to finish
CONCURRENCY = 3  # parallel calls per draft

LEVEL_FOCUS: dict[Level, str] = {
    "basic": "core vocabulary and fundamentals, assuming no prior knowledge",
    "intermediate": "the everyday working toolkit a practitioner uses",
    "advanced": "internals, performance, edge cases and design trade-offs",
    "pro": "real-world practice: architecture, testing, debugging, teaching others and "
    "portfolio-quality projects",
}

OUTLINE_SYSTEM = """\
You design self-study roadmaps inside Personal OS, a private planning app.

Write the outline of a roadmap that takes a complete beginner to professional level in the
subject. Give one line per day: the single concept or skill the learner masters that day.
- Use exactly the number of days asked for in each level, in the order basic,
  intermediate, advanced, pro.
- Order concepts so each one builds on the ones before it. Never repeat a concept.
- Name each concept specifically, in under 12 words ("useEffect cleanup and dependency
  arrays", not "hooks part 2").
- The last day of every level is a project or review day that combines that level's
  concepts; say what to build or review.
- Level focus: basic = {basic}; intermediate = {intermediate}; advanced = {advanced};
  pro = {pro}.
- Use your own wording. Do not reproduce other roadmaps or course outlines.
- If the subject is not something a person can learn step by step, outline the closest
  learnable skill and say so in the title.
""".format(**LEVEL_FOCUS)

EXPAND_SYSTEM = """\
You turn roadmap days into clear daily study tasks inside Personal OS, a private planning app.

For every day you are given, write tasks the learner can finish and tick off that day, so
the concept becomes clear rather than skimmed:
1. Title "Understand: <concept>". Detail: two or three plain sentences saying what it is,
   why it matters and one concrete example.
2. Title "Practise: <specific exercise>". Detail: what to build, write, solve or try, and
   how the learner knows they are done.
3. Title "Check yourself: <question or mini-challenge>". Detail: what a good answer covers.
   The learner answers without notes.
On a project or review day, replace tasks 1 and 2 with the project broken into clear steps.
- Return exactly one day per concept, in the order given, with topic set to the concept.
- Minutes are realistic and the tasks of one day add up to about the daily time.
- Details are at most two sentences. Use your own wording.
"""


class DraftRefused(Exception):
    """The model declined the subject."""


def clean(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def split_days(total: int) -> dict[Level, int]:
    """Days per level, summing to `total` (at least two days per level)."""
    total = max(total, MIN_DAYS_PER_LEVEL * len(ORDER))
    raw = {lv: total * LEVEL_SHARE[lv] for lv in ORDER}
    counts = {lv: max(MIN_DAYS_PER_LEVEL, math.floor(raw[lv])) for lv in ORDER}
    by_remainder = sorted(ORDER, key=lambda lv: raw[lv] - math.floor(raw[lv]), reverse=True)
    i = 0
    while sum(counts.values()) < total:
        counts[by_remainder[i % len(ORDER)]] += 1
        i += 1
    while sum(counts.values()) > total:
        counts[max(ORDER, key=lambda lv: counts[lv])] -= 1
    return counts


def fallback_day(topic: str, minutes_per_day: int) -> list[DraftTask]:
    """Plain but concrete tasks for a day the model never wrote."""
    return [
        DraftTask(
            title=clean(f"Understand: {topic}", 200),
            detail=f"Read a short introduction to {topic}: what it is, why it matters and one "
            "example. Then write a three-sentence summary in your own words.",
            minutes=_round5(minutes_per_day * 0.45),
        ),
        DraftTask(
            title=clean(f"Practise: a small exercise using {topic}", 200),
            detail=f"Build, write or solve one small thing that uses {topic}. You are done "
            "when it works and you can say why.",
            minutes=_round5(minutes_per_day * 0.40),
        ),
        DraftTask(
            title=clean(f"Check yourself: explain {topic} without notes", 200),
            detail=f"Explain {topic} and when you would use it, out loud or in writing. "
            "Revisit anything you could not explain.",
            minutes=_round5(minutes_per_day * 0.15),
        ),
    ]


def _round5(minutes: float) -> int:
    return min(max(5, round(minutes / 5) * 5), 480)


def _unique(topics: Iterable[str], seen: set[str]) -> list[str]:
    out: list[str] = []
    for topic in topics:
        text = clean(topic, 120)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _key(text: str) -> str:
    return " ".join(text.split()).casefold()


def _match_days(wanted: list[tuple[int, str]], days: list[PlannedDay]) -> dict[int, PlannedDay]:
    """Pair reply days with the requested days by topic, so a skipped day never shifts the
    rest into the wrong slot. Position is used only when the reply has exactly one day per
    request (the model reworded the topics but kept the order)."""
    unused = {_key(d.topic): d for d in days}
    matched: dict[int, PlannedDay] = {}
    for n, topic in wanted:  # exact topics first
        if (day := unused.pop(_key(topic), None)) is not None:
            matched[n] = day
    for n, topic in wanted:  # then a reworded topic that contains, or is inside, the request
        key = _key(topic)
        hit = next((k for k in unused if k and n not in matched and (key in k or k in key)), None)
        if hit is not None:
            matched[n] = unused.pop(hit)
    if not matched and len(days) == len(wanted):
        matched = {n: day for (n, _topic), day in zip(wanted, days, strict=True)}
    return matched


def _tasks(day: PlannedDay, minutes_per_day: int) -> list[DraftTask]:
    tasks = [
        DraftTask(
            title=clean(t.title, 200),
            detail=clean(t.detail, 1000) or None,
            minutes=min(max(t.minutes, 5), 480),
        )
        for t in day.tasks[:MAX_TASKS_PER_DAY]
        if t.title.strip()
    ]
    total = sum(t.minutes for t in tasks)
    # Keep each day close to the time the learner said they have.
    if tasks and not (0.5 * minutes_per_day <= total <= 1.5 * minutes_per_day):
        scale = minutes_per_day / total
        tasks = [t.model_copy(update={"minutes": _round5(t.minutes * scale)}) for t in tasks]
    return tasks


class Drafter:
    """One draft. Every model reply is kept in `replies` so the caller can bill all of them,
    including when drafting fails halfway."""

    def __init__(self, generator: RoadmapGenerator) -> None:
        self._generator = generator
        self._limit = asyncio.Semaphore(CONCURRENCY)
        self.replies: list[AIReply[Any]] = []
        # Progress, read by a background job while the draft is being written.
        self.stage: Literal["outline", "writing"] = "outline"
        self.days_total = 0
        self.days_done = 0

    async def _ask[T: BaseModel](
        self, system: str, user: str, schema: type[T], max_tokens: int
    ) -> T | None:
        async with self._limit:
            reply = await self._generator.complete(
                system=system, user=user, schema=schema, max_tokens=max_tokens
            )
        self.replies.append(reply)
        if reply.refused:
            raise DraftRefused
        return reply.parsed

    @staticmethod
    async def _all[R](calls: list[Awaitable[R]]) -> list[R]:
        """Run calls together; the first failure cancels the rest and is raised as is."""
        try:
            async with asyncio.TaskGroup() as group:
                tasks = [group.create_task(_wrap(call)) for call in calls]
        except ExceptionGroup as errors:
            raise errors.exceptions[0] from None
        return [task.result() for task in tasks]

    # -------------------------------------------------------------- stage 1: outline

    async def outline(
        self, subject: str, counts: dict[Level, int]
    ) -> tuple[str, dict[Level, list[str]]]:
        wanted = "\n".join(f"- {lv}: {counts[lv]} days" for lv in ORDER)
        plan = await self._ask(
            OUTLINE_SYSTEM,
            f"<subject>{subject}</subject>\nDays per level:\n{wanted}",
            PlannedOutline,
            max_tokens=4000,
        )
        if plan is None:
            raise ServiceUnavailable(
                "The AI's outline came back malformed. Try again or pick another model.",
                code="ai_bad_output",
            )
        seen: set[str] = set()
        topics: dict[Level, list[str]] = {lv: [] for lv in ORDER}
        for lv in ORDER:  # canonical order, whatever order the model used
            for level in plan.levels:
                if level.level == lv:
                    topics[lv] += _unique(level.topics, seen)

        async def top_up(lv: Level) -> None:
            missing = counts[lv] - len(topics[lv])
            so_far = "\n".join(f"- {t}" for t in topics[lv]) or "- (none yet)"
            more = await self._ask(
                OUTLINE_SYSTEM,
                f"<subject>{subject}</subject>\nGive exactly {missing} more {lv}-level "
                f"concepts, continuing after these and repeating none of them:\n{so_far}",
                PlannedTopicList,
                max_tokens=2000,
            )
            if more is not None:
                topics[lv] += _unique(more.topics, seen)

        await self._all([top_up(lv) for lv in ORDER if len(topics[lv]) < counts[lv]])
        for lv in ORDER:
            topics[lv] = topics[lv][: counts[lv]]
            while len(topics[lv]) < counts[lv]:  # the model still came up short
                n = len(topics[lv]) + 1
                topics[lv].append(
                    f"{lv.capitalize()} review: revisit and apply what you have learned ({n})"
                    if topics[lv]
                    else f"{lv.capitalize()} {subject}: {LEVEL_FOCUS[lv].split(',')[0]}"
                )
        title = clean(plan.title, 120) or f"{subject}: basic to pro"
        return title, topics

    # -------------------------------------------------------------- stage 2: expand

    async def _expand_batch(
        self,
        subject: str,
        level: Level,
        days: list[tuple[int, str]],
        context: str,
        minutes_per_day: int,
    ) -> dict[int, list[DraftTask]]:
        written: dict[int, list[DraftTask]] = {}
        todo = days
        for _attempt in range(2):  # one retry for days the model skipped
            listing = "\n".join(f"Day {n}: {topic}" for n, topic in todo)
            reply = await self._ask(
                EXPAND_SYSTEM,
                f"<subject>{subject}</subject>\nLevel: {level} ({LEVEL_FOCUS[level]})\n"
                f"Daily time: about {minutes_per_day} minutes\n\n"
                f"All {level} concepts, for context only: {context}\n\n"
                f"Write exactly these {len(todo)} days:\n{listing}",
                PlannedDays,
                max_tokens=4000,
            )
            for n, day in _match_days(todo, reply.days if reply else []).items():
                tasks = _tasks(day, minutes_per_day)
                if tasks:
                    written[n] = tasks
            todo = [(n, topic) for n, topic in todo if n not in written]
            if not todo:
                break
        for n, topic in todo:
            written[n] = fallback_day(topic, minutes_per_day)
        self.days_done += len(days)
        return written

    async def build(self, *, subject: str, target_days: int, minutes_per_day: int) -> RoadmapDraft:
        counts = split_days(target_days)
        title, topics = await self.outline(subject, counts)

        numbered: list[tuple[Level, int, str]] = []
        for lv in ORDER:
            for topic in topics[lv]:
                numbered.append((lv, len(numbered) + 1, topic))
        # Each call sees only its own level's concepts: enough to avoid overlap, and a shorter
        # prompt keeps small local models fast.
        context = {lv: "; ".join(topics[lv]) for lv in ORDER}
        self.stage, self.days_total = "writing", len(numbered)
        batches: list[tuple[Level, list[tuple[int, str]]]] = []
        for lv in ORDER:
            level_days = [(n, t) for level, n, t in numbered if level == lv]
            for start in range(0, len(level_days), BATCH_DAYS):
                batches.append((lv, level_days[start : start + BATCH_DAYS]))

        results = await self._all(
            [
                self._expand_batch(subject, lv, days, context[lv], minutes_per_day)
                for lv, days in batches
            ]
        )
        tasks_by_day = {n: tasks for result in results for n, tasks in result.items()}
        return RoadmapDraft(
            subject=subject,
            title=title,
            source="ai",
            days=[DraftDay(level=lv, tasks=tasks_by_day[n]) for lv, n, _t in numbered],
        )


async def _wrap[R](call: Awaitable[R]) -> R:
    return await call
