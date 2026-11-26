"""Roadmap drafts that run in the background, with progress the page can poll.

A full draft takes from about 30 seconds (a cloud model) to about 10 minutes (a small local
model on a laptop), far longer than an HTTP request should stay open. POST starts a job in
this API process and returns at once; the page polls GET for progress and the finished draft.

Jobs live in memory, like the rate limiter: fine for a single API instance. They move to the
background worker (M6) when the API scales out. A job is dropped an hour after it finishes,
and an API restart drops running jobs (the page then says to try again). Nothing is saved
until the user saves the draft. Every model call is billed, also when a job fails.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from time import monotonic
from typing import Literal

from app.ai import service as ai_service
from app.core.db import SessionFactory
from app.core.errors import AppError, Conflict, NotFound
from app.modules.roadmaps import drafting
from app.modules.roadmaps.generator import RoadmapGenerator
from app.modules.roadmaps.schemas import DraftJobError, DraftJobOut, RoadmapDraft

logger = logging.getLogger("app.roadmaps.jobs")

KEEP_FINISHED_SECONDS = 3600


@dataclass(eq=False)
class DraftJob:
    user_id: uuid.UUID
    subject: str
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: Literal["running", "done", "failed", "cancelled"] = "running"
    draft: RoadmapDraft | None = None
    error: DraftJobError | None = None
    drafter: drafting.Drafter | None = None
    finished_at: float | None = None
    task: asyncio.Task[None] | None = None

    def out(self) -> DraftJobOut:
        drafter = self.drafter
        if self.status == "done":
            total = len(self.draft.days) if self.draft else 0
            stage, done = "done", total
        else:
            stage = drafter.stage if drafter else "outline"
            total = drafter.days_total if drafter else 0
            done = drafter.days_done if drafter else 0
        return DraftJobOut(
            id=self.id,
            subject=self.subject,
            status=self.status,
            stage=stage,
            days_done=done,
            days_total=total,
            draft=self.draft,
            error=self.error,
        )


_jobs: dict[uuid.UUID, DraftJob] = {}


def _prune() -> None:
    cutoff = monotonic() - KEEP_FINISHED_SECONDS
    for job_id in [
        j.id for j in _jobs.values() if j.finished_at is not None and j.finished_at < cutoff
    ]:
        _jobs.pop(job_id, None)


def finished(user_id: uuid.UUID, subject: str, draft: RoadmapDraft) -> DraftJob:
    """A job that is done at once (a built-in roadmap), so the page has one flow."""
    _prune()
    job = DraftJob(user_id=user_id, subject=subject, status="done", draft=draft)
    job.finished_at = monotonic()
    _jobs[job.id] = job
    return job


def start(
    *,
    user_id: uuid.UUID,
    subject: str,
    target_days: int,
    minutes_per_day: int,
    generator: RoadmapGenerator,
    session_factory: SessionFactory,
) -> DraftJob:
    _prune()
    running = next(
        (j for j in _jobs.values() if j.user_id == user_id and j.status == "running"), None
    )
    if running is not None:
        # The page uses jobId to show the draft that is already running, or cancel it.
        raise Conflict(
            f"A roadmap for {running.subject!r} is already being drafted. "
            "Wait for it to finish or cancel it.",
            code="draft_in_progress",
            jobId=str(running.id),
        )
    drafter = drafting.Drafter(generator)
    job = DraftJob(user_id=user_id, subject=subject, drafter=drafter)
    _jobs[job.id] = job
    job.task = asyncio.create_task(
        _run(
            job,
            drafter,
            target_days=target_days,
            minutes_per_day=minutes_per_day,
            factory=session_factory,
        )
    )
    return job


def get(user_id: uuid.UUID, job_id: uuid.UUID) -> DraftJob:
    job = _jobs.get(job_id)
    if job is None or job.user_id != user_id:  # another user's job does not exist for you
        raise NotFound("This draft is no longer available. Build the roadmap again.")
    return job


async def cancel(user_id: uuid.UUID, job_id: uuid.UUID) -> DraftJob:
    """Stop a running draft. Calls already answered are still billed."""
    job = get(user_id, job_id)
    if job.status == "running" and job.task is not None:
        job.task.cancel()
        await asyncio.wait({job.task}, timeout=10)
    return job


async def _run(
    job: DraftJob,
    drafter: drafting.Drafter,
    *,
    target_days: int,
    minutes_per_day: int,
    factory: SessionFactory,
) -> None:
    try:
        job.draft = await drafter.build(
            subject=job.subject, target_days=target_days, minutes_per_day=minutes_per_day
        )
        job.status = "done"
    except asyncio.CancelledError:
        # Cancelled by the user; finish quietly so the usage below is still recorded.
        job.status = "cancelled"
    except drafting.DraftRefused:
        job.status = "failed"
        job.error = DraftJobError(
            code="ai_refused",
            message="The AI declined to plan this subject. Try wording it differently.",
        )
    except AppError as exc:
        job.status = "failed"
        job.error = DraftJobError(code=exc.code, message=str(exc))
    except Exception:
        logger.exception("roadmap_draft_failed")
        job.status = "failed"
        job.error = DraftJobError(
            code="ai_unavailable", message="Drafting the roadmap failed. Try again."
        )
    finally:
        job.finished_at = monotonic()
        try:
            async with factory() as session:
                for reply in drafter.replies:
                    await ai_service.record_usage(
                        session,
                        user_id=job.user_id,
                        route="roadmap",
                        model=reply.model,
                        usage=reply.usage,
                        conversation_id=None,
                        request_id=reply.request_id,
                        free=reply.free,
                    )
        except Exception:
            logger.exception("roadmap_usage_not_recorded")
