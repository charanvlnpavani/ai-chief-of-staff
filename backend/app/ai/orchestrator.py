"""The Chief of Staff agent loop (self-hosted, Messages API).

One user message -> up to N model calls. Each call streams text to the client. Tool calls are
validated, authorised against the tools offered for this request, executed through domain
services with a timeout, and audited. Every model call is costed in the usage ledger, and the
monthly budget is re-checked before each further call.

Invariant: whenever an assistant turn contains tool_use blocks, a matching tool_result turn is
stored right after it (executed, denied, or "not run"), so the stored history is always valid
to replay and never has to be edited.
"""

import asyncio
import hashlib
import json
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime
from time import perf_counter
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import service
from app.ai.client import ChatModel, ChatModelError, TextDelta, TurnResult
from app.ai.models import AIToolExecution
from app.ai.prompts import SYSTEM_PROMPT, turn_context
from app.ai.registry import Tool, ToolContext
from app.core.db import SessionFactory
from app.core.errors import AppError
from app.core.time import zone

logger = logging.getLogger("app.ai.orchestrator")

__all__ = ["SessionFactory", "TurnRequest", "execute_tool_call", "run_turn"]
SYSTEM_BLOCKS: list[dict[str, Any]] = [
    # Explicit cache breakpoint at the end of the static prefix (tools + system).
    {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
]


@dataclass(frozen=True, slots=True)
class TurnRequest:
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    timezone: str
    today: date
    now: datetime
    text: str
    budget_micros: int
    tools: list[Tool]
    max_iterations: int


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _redact_args(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 80 else value[:80] + "…"
    if isinstance(value, dict):
        return {k: _redact_args(v) for k, v in list(value.items())[:20]}
    if isinstance(value, list):
        return [_redact_args(v) for v in value[:20]]
    return value


def _tool_result(tool_use_id: str, payload: dict[str, Any], *, is_error: bool) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(payload, ensure_ascii=False, default=str),
    }
    if is_error:
        block["is_error"] = True
    return block


async def execute_tool_call(
    session: AsyncSession,
    *,
    block: dict[str, Any],
    allowed: dict[str, Tool],
    context: ToolContext,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
) -> tuple[dict[str, Any], bool]:
    """Runs one tool_use block. Returns (tool_result block, ok)."""
    name = str(block.get("name", ""))
    raw_input = block.get("input") or {}
    started = perf_counter()
    tool = allowed.get(name)
    decision, status, error_code = "allowed", "ok", None
    payload: dict[str, Any]
    summary: dict[str, Any] = {}

    if tool is None:
        decision, status, error_code = "denied", "denied", "tool_not_available"
        payload = {
            "error": "tool_not_available",
            "message": f"No tool named {name!r} is available.",
        }
    else:
        try:
            args = tool.input_model.model_validate(raw_input)
        except ValidationError as exc:
            decision, status, error_code = "invalid", "error", "invalid_input"
            payload = {
                "error": "invalid_input",
                "details": [
                    {"field": ".".join(str(p) for p in e["loc"]), "problem": e["msg"]}
                    for e in exc.errors()
                ],
            }
        else:
            try:
                payload = await asyncio.wait_for(tool.fn(context, args), timeout=tool.timeout_s)
                summary = {k: len(v) for k, v in payload.items() if isinstance(v, list)}
            except TimeoutError:
                status, error_code = "timeout", "timeout"
                payload = {"error": "timeout", "message": "The lookup took too long."}
            except AppError as exc:
                status, error_code = "error", exc.code
                payload = {"error": exc.code, "message": exc.detail or exc.title}
            except Exception:
                logger.exception("tool_failed", extra={"tool": name})
                await session.rollback()
                status, error_code = "error", "tool_failed"
                payload = {"error": "tool_failed", "message": "The lookup failed."}

    session.add(
        AIToolExecution(
            user_id=context.user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            tool_id=name[:64],
            tool_version=tool.version if tool else "-",
            permission_level=int(tool.level) if tool else 0,
            decision=decision,
            status=status,
            args_redacted=_redact_args(raw_input) if isinstance(raw_input, dict) else {},
            args_hash=hashlib.sha256(
                json.dumps(raw_input, sort_keys=True, default=str).encode()
            ).digest(),
            result_summary=summary,
            latency_ms=int((perf_counter() - started) * 1000),
            error_code=error_code,
        )
    )
    await session.commit()
    ok = status == "ok"
    return _tool_result(str(block.get("id", "")), payload, is_error=not ok), ok


async def run_turn(
    *, session_factory: SessionFactory, model: ChatModel, request: TurnRequest
) -> AsyncIterator[str]:
    """Yields Server-Sent Events: text, tool, done or error."""
    async with session_factory() as session:
        conversation_id, user_id = request.conversation_id, request.user_id
        allowed = {t.name: t for t in request.tools}
        tool_definitions = [t.definition() for t in request.tools]
        context = ToolContext(
            session=session, user_id=user_id, timezone=request.timezone, today=request.today
        )
        local = request.now.astimezone(zone(request.timezone))
        user_content = [
            {
                "type": "text",
                "text": turn_context(
                    local_datetime=local.strftime("%Y-%m-%d %H:%M"),
                    timezone=request.timezone,
                    weekday=local.strftime("%A"),
                ),
            },
            {"type": "text", "text": request.text},
        ]

        history = await service.load_history(session, conversation_id)
        first_message = not history
        seq = await service.next_seq(session, conversation_id)
        await service.append_message(
            session,
            user_id=user_id,
            conversation_id=conversation_id,
            seq=seq,
            role="user",
            content=user_content,
        )
        if history and history[-1]["role"] == "user":  # merge, as load_history does
            history[-1]["content"] = [*history[-1]["content"], *user_content]
            messages = history
        else:
            messages = [*history, {"role": "user", "content": user_content}]

        spent_this_turn = 0
        stop_reason: str | None = None
        yield sse("start", {"conversationId": str(conversation_id)})

        for _iteration in range(request.max_iterations):
            month_spend = await service.month_to_date_micros(
                session, user_id, timezone=request.timezone, today=request.today
            )
            if month_spend >= request.budget_micros:
                yield sse(
                    "error", {"code": "ai_budget_exceeded", "message": "Monthly AI budget reached."}
                )
                break

            final: TurnResult | None = None
            try:
                async for item in model.stream_turn(
                    system=SYSTEM_BLOCKS, tools=tool_definitions, messages=messages
                ):
                    if isinstance(item, TextDelta):
                        yield sse("text", {"delta": item.text})
                    else:
                        final = item
            except ChatModelError as exc:
                yield sse(
                    "error", {"code": exc.code, "message": str(exc), "retryable": exc.retryable}
                )
                break
            if final is None:
                yield sse(
                    "error", {"code": "ai_no_response", "message": "No response from Claude."}
                )
                break

            spent_this_turn += await service.record_usage(
                session,
                user_id=user_id,
                route="chat",
                model=final.model,
                usage=final.usage,
                conversation_id=conversation_id,
                request_id=final.request_id,
            )
            seq += 1
            assistant = await service.append_message(
                session,
                user_id=user_id,
                conversation_id=conversation_id,
                seq=seq,
                role="assistant",
                content=final.content,
                model=final.model,
                stop_reason=final.stop_reason,
            )
            messages.append({"role": "assistant", "content": final.content})
            stop_reason = final.stop_reason
            tool_uses = [b for b in final.content if b.get("type") == "tool_use"]

            if stop_reason == "pause_turn" and not tool_uses:
                continue
            if not tool_uses:
                break

            results: list[dict[str, Any]] = []
            runnable = stop_reason not in ("max_tokens", "refusal")
            for block in tool_uses:
                if not runnable:
                    results.append(
                        _tool_result(
                            str(block.get("id", "")),
                            {"error": "not_run", "message": "Not run: the response was cut off."},
                            is_error=True,
                        )
                    )
                    continue
                yield sse("tool", {"name": block.get("name"), "status": "running"})
                result, ok = await execute_tool_call(
                    session,
                    block=block,
                    allowed=allowed,
                    context=context,
                    conversation_id=conversation_id,
                    message_id=assistant.id,
                )
                results.append(result)
                yield sse("tool", {"name": block.get("name"), "status": "done" if ok else "error"})

            seq += 1
            await service.append_message(
                session,
                user_id=user_id,
                conversation_id=conversation_id,
                seq=seq,
                role="user",
                content=results,
                kind="tool_results",
            )
            messages.append({"role": "user", "content": results})
            if not runnable:
                code = "ai_refused" if stop_reason == "refusal" else "response_truncated"
                yield sse("error", {"code": code, "message": "Claude stopped before finishing."})
                break
        else:
            yield sse(
                "error", {"code": "max_iterations", "message": "Stopped after too many steps."}
            )

        await service.touch_conversation(
            session, conversation_id, first_user_text=request.text if first_message else None
        )
        yield sse(
            "done",
            {
                "stopReason": stop_reason,
                "costUsd": round(spent_this_turn / 1_000_000, 6),
            },
        )
