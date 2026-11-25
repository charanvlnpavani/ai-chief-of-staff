"""Roadmaps: drafts (built-in or from Claude), saved plans, daily ticks and progress."""

import uuid
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import service as ai_service
from app.core.errors import BadRequest, Conflict, Forbidden, NotFound, ServiceUnavailable
from app.core.time import utc_now
from app.modules.identity import service as identity_service
from app.modules.roadmaps import planner
from app.modules.roadmaps.generator import RoadmapGenerator
from app.modules.roadmaps.models import LEVELS, Roadmap, RoadmapTask
from app.modules.roadmaps.schemas import (
    MAX_DAYS,
    MAX_TASKS_PER_DAY,
    DraftDay,
    DraftRequest,
    DraftTask,
    LevelProgressOut,
    PlannedRoadmap,
    RoadmapDetailOut,
    RoadmapDraft,
    RoadmapOut,
    RoadmapProgressOut,
    RoadmapTaskOut,
    RoadmapUpdate,
    TemplateOut,
    TodayOut,
)
from app.modules.roadmaps.templates import TEMPLATES, Template, find_template

# ------------------------------------------------------------------ drafts


def list_templates() -> list[TemplateOut]:
    return [
        TemplateOut(key=t.key, subject=t.subject, title=t.title, days=len(t.days))
        for t in TEMPLATES.values()
    ]


def _template_draft(template: Template) -> RoadmapDraft:
    return RoadmapDraft(
        subject=template.subject,
        title=template.title,
        source="template",
        template_key=template.key,
        days=[
            DraftDay(
                level=level,
                tasks=[DraftTask(title=t, detail=d, minutes=m) for t, d, m in tasks],
            )
            for level, tasks in template.days
        ],
    )


def _clean(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _plan_to_draft(subject: str, plan: PlannedRoadmap) -> RoadmapDraft:
    """Turn Claude's output into a draft, enforcing every limit the API promises."""
    order = {level: i for i, level in enumerate(LEVELS)}
    days: list[DraftDay] = []
    for planned in sorted(plan.levels, key=lambda lv: order[lv.level]):
        for planned_day in planned.days:
            tasks = [
                DraftTask(
                    title=_clean(t.title, 200),
                    detail=_clean(t.detail, 1000) or None,
                    minutes=min(max(t.minutes, 5), 480),
                )
                for t in planned_day.tasks[:MAX_TASKS_PER_DAY]
                if t.title.strip()
            ]
            if tasks:
                days.append(DraftDay(level=planned.level, tasks=tasks))
    if not days:
        raise ServiceUnavailable("Claude returned an empty roadmap.", code="ai_bad_output")
    return RoadmapDraft(
        subject=subject,
        title=_clean(plan.title, 120) or subject,
        source="ai",
        days=days[:MAX_DAYS],
    )


async def _check_ai_allowed(
    session: AsyncSession, user_id: uuid.UUID, *, timezone: str, today: date
) -> None:
    if not await identity_service.has_consent(session, user_id, "ai_processing"):
        raise Forbidden(
            "Allow AI processing in Settings to plan new subjects with Claude.",
            code="consent_required",
            category="ai_processing",
        )
    preferences, _version = await identity_service.get_preferences(session, user_id)
    budget_micros = int(preferences.ai.monthly_budget_usd * 1_000_000)
    spent = await ai_service.month_to_date_micros(session, user_id, timezone=timezone, today=today)
    if spent >= budget_micros:
        raise Forbidden(
            "You have reached this month's AI budget. Raise it in Settings to continue.",
            code="ai_budget_exceeded",
        )


async def draft(
    session: AsyncSession,
    user_id: uuid.UUID,
    data: DraftRequest,
    *,
    timezone: str,
    today: date,
    generator: RoadmapGenerator | None,
) -> RoadmapDraft:
    """A built-in roadmap when one matches; otherwise a Claude draft. Nothing is saved."""
    subject = " ".join(data.subject.split())
    template = find_template(subject) if data.use_template else None
    if template is not None:
        return _template_draft(template)
    if generator is None:
        raise ServiceUnavailable(
            "Roadmaps for new subjects need ANTHROPIC_API_KEY in backend/.env. "
            "Built-in roadmaps work without it.",
            code="ai_not_configured",
        )
    await _check_ai_allowed(session, user_id, timezone=timezone, today=today)
    result = await generator.generate(
        subject=subject, target_days=data.target_days, minutes_per_day=data.minutes_per_day
    )
    await ai_service.record_usage(
        session,
        user_id=user_id,
        route="roadmap",
        model=result.model,
        usage=result.usage,
        conversation_id=None,
        request_id=result.request_id,
    )
    if result.refused:
        raise BadRequest(
            "Claude declined to plan this subject. Try wording it differently.",
            code="ai_refused",
        )
    if result.plan is None:
        raise ServiceUnavailable(
            "Claude's roadmap came back incomplete. Try fewer days.", code="ai_bad_output"
        )
    return _plan_to_draft(subject, result.plan)


# ------------------------------------------------------------------ saved roadmaps


async def _get_roadmap(
    session: AsyncSession, user_id: uuid.UUID, roadmap_id: uuid.UUID, *, lock: bool = False
) -> Roadmap:
    query = select(Roadmap).where(
        Roadmap.id == roadmap_id, Roadmap.user_id == user_id, Roadmap.deleted_at.is_(None)
    )
    roadmap = await session.scalar(query.with_for_update() if lock else query)
    if roadmap is None:
        raise NotFound("Roadmap not found.")
    return roadmap


async def _load_tasks(
    session: AsyncSession, roadmap_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[RoadmapTask]]:
    tasks: dict[uuid.UUID, list[RoadmapTask]] = defaultdict(list)
    if roadmap_ids:
        for task in await session.scalars(
            select(RoadmapTask)
            .where(RoadmapTask.roadmap_id.in_(roadmap_ids))
            .order_by(RoadmapTask.day, RoadmapTask.position)
        ):
            tasks[task.roadmap_id].append(task)
    return tasks


def _progress_out(result: planner.Plan) -> RoadmapProgressOut:
    return RoadmapProgressOut(
        done=result.done,
        total=result.total,
        percent=round(result.done / result.total, 4) if result.total else 0.0,
        levels=[
            LevelProgressOut(level=lv.level, done=lv.done, total=lv.total) for lv in result.levels
        ],
        current_day=result.current_day,
        current_level=result.current_level,
        total_days=result.total_days,
        streak_days=result.streak_days,
        projected_finish=result.projected_finish,
    )


def _roadmap_out(roadmap: Roadmap, result: planner.Plan) -> RoadmapOut:
    fields = {
        name: getattr(roadmap, name) for name in RoadmapOut.model_fields if name != "progress"
    }
    return RoadmapOut(**fields, progress=_progress_out(result))


async def list_roadmaps(
    session: AsyncSession, user_id: uuid.UUID, *, today: date, include_archived: bool = False
) -> list[RoadmapOut]:
    query = select(Roadmap).where(Roadmap.user_id == user_id, Roadmap.deleted_at.is_(None))
    if not include_archived:
        query = query.where(Roadmap.status != "archived")
    roadmaps = list(await session.scalars(query.order_by(Roadmap.created_at.desc())))
    tasks = await _load_tasks(session, [r.id for r in roadmaps])
    return [_roadmap_out(r, planner.plan(tasks[r.id], today)) for r in roadmaps]


async def get_roadmap(
    session: AsyncSession,
    user_id: uuid.UUID,
    roadmap_id: uuid.UUID,
    *,
    today: date,
    ahead: bool = False,
) -> RoadmapDetailOut:
    roadmap = await _get_roadmap(session, user_id, roadmap_id)
    tasks = (await _load_tasks(session, [roadmap.id]))[roadmap.id]
    result = planner.plan(tasks, today, ahead=ahead)
    task_out = [RoadmapTaskOut.model_validate(t) for t in tasks]
    shown = set(result.days_today)
    base = _roadmap_out(roadmap, result)
    return RoadmapDetailOut(
        **base.model_dump(by_alias=False),
        today=TodayOut(
            date=today,
            days=result.days_today,
            tasks=[t for t in task_out if t.day in shown],
            complete=result.today_complete,
            finished=result.finished,
            can_go_ahead=result.can_go_ahead,
        ),
        tasks=task_out,
    )


async def create_roadmap(
    session: AsyncSession, user_id: uuid.UUID, data: RoadmapDraft, *, today: date
) -> RoadmapDetailOut:
    if data.source == "template":
        template = TEMPLATES.get(data.template_key or "")
        if template is None:
            raise BadRequest("Unknown built-in roadmap.", code="unknown_template")
    roadmap = Roadmap(
        user_id=user_id,
        subject=" ".join(data.subject.split()),
        title=data.title.strip(),
        source=data.source,
        template_key=data.template_key if data.source == "template" else None,
        start_date=today,
    )
    session.add(roadmap)
    await session.flush()
    for day_number, day in enumerate(data.days, start=1):
        for position, task in enumerate(day.tasks):
            session.add(
                RoadmapTask(
                    user_id=user_id,
                    roadmap_id=roadmap.id,
                    day=day_number,
                    position=position,
                    level=day.level,
                    title=task.title.strip(),
                    detail=task.detail.strip() if task.detail and task.detail.strip() else None,
                    minutes=task.minutes,
                )
            )
    await session.commit()
    return await get_roadmap(session, user_id, roadmap.id, today=today)


async def update_roadmap(
    session: AsyncSession,
    user_id: uuid.UUID,
    roadmap_id: uuid.UUID,
    data: RoadmapUpdate,
    *,
    today: date,
) -> RoadmapDetailOut:
    roadmap = await _get_roadmap(session, user_id, roadmap_id, lock=True)
    changes = data.model_dump(exclude_unset=True, by_alias=False)
    expected = changes.pop("version", None)
    if expected is not None and expected != roadmap.version:
        raise Conflict("This roadmap changed since you loaded it.", code="version_conflict")
    if changes.get("title"):
        roadmap.title = changes["title"].strip()
    status = changes.get("status")
    if status and status != roadmap.status:
        if status == "completed":
            raise BadRequest(
                "A roadmap completes itself when its last task is ticked.",
                code="status_not_allowed",
            )
        roadmap.status = status
    roadmap.version += 1
    await session.commit()
    return await get_roadmap(session, user_id, roadmap_id, today=today)


async def delete_roadmap(session: AsyncSession, user_id: uuid.UUID, roadmap_id: uuid.UUID) -> None:
    roadmap = await _get_roadmap(session, user_id, roadmap_id)
    roadmap.deleted_at = utc_now()
    await session.commit()


async def set_task_done(
    session: AsyncSession,
    user_id: uuid.UUID,
    roadmap_id: uuid.UUID,
    task_id: uuid.UUID,
    *,
    done: bool,
    today: date,
    ahead: bool = False,
) -> RoadmapDetailOut:
    """Tick or untick a task (idempotent). The roadmap completes itself on the last tick."""
    roadmap = await _get_roadmap(session, user_id, roadmap_id, lock=True)
    if roadmap.status == "archived":
        raise BadRequest("Restore this roadmap before ticking tasks.", code="roadmap_archived")
    task = await session.scalar(
        select(RoadmapTask).where(RoadmapTask.id == task_id, RoadmapTask.roadmap_id == roadmap.id)
    )
    if task is None:
        raise NotFound("Task not found.")
    if done and task.completed_on is None:
        task.completed_on, task.completed_at = today, utc_now()
    elif not done and task.completed_on is not None:
        task.completed_on, task.completed_at = None, None
    await session.flush()

    tasks = (await _load_tasks(session, [roadmap.id]))[roadmap.id]
    all_done = all(t.completed_on is not None for t in tasks)
    if all_done and roadmap.status != "completed":
        roadmap.status, roadmap.completed_at = "completed", utc_now()
        roadmap.version += 1
    elif not all_done and roadmap.status == "completed":
        roadmap.status, roadmap.completed_at = "active", None
        roadmap.version += 1
    await session.commit()
    return await get_roadmap(session, user_id, roadmap_id, today=today, ahead=ahead)
