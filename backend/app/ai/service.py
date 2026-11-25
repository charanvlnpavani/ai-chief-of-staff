"""Conversations, encrypted message storage, usage ledger and budget."""

import json
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.models import AIConversation, AIMessage, AIUsageLedger
from app.ai.pricing import Usage, cost_micros
from app.ai.schemas import (
    ConversationDetailOut,
    ConversationOut,
    DisplayMessage,
    ToolCallOut,
    UsageByRoute,
)
from app.core.config import Settings
from app.core.crypto import get_keyring
from app.core.errors import NotFound
from app.core.time import local_day_start, utc_now

# ------------------------------------------------------------------ conversations


async def create_conversation(
    session: AsyncSession, user_id: uuid.UUID, *, title: str | None, settings: Settings
) -> AIConversation:
    now = utc_now()
    conversation = AIConversation(
        user_id=user_id,
        title=title,
        last_message_at=now,
        retention_until=now + timedelta(days=settings.ai_conversation_retention_days),
    )
    session.add(conversation)
    await session.commit()
    return conversation


async def get_conversation(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> AIConversation:
    conversation = await session.scalar(
        select(AIConversation).where(
            AIConversation.id == conversation_id,
            AIConversation.user_id == user_id,
            AIConversation.deleted_at.is_(None),
        )
    )
    if conversation is None:
        raise NotFound("Conversation not found.")
    return conversation


async def list_conversations(
    session: AsyncSession, user_id: uuid.UUID, *, limit: int = 30
) -> list[AIConversation]:
    rows = await session.scalars(
        select(AIConversation)
        .where(AIConversation.user_id == user_id, AIConversation.deleted_at.is_(None))
        .order_by(AIConversation.last_message_at.desc())
        .limit(limit)
    )
    return list(rows)


async def delete_conversation(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> None:
    conversation = await get_conversation(session, user_id, conversation_id)
    await session.delete(conversation)  # messages cascade; nothing is kept
    await session.commit()


# ------------------------------------------------------------------ messages


def _aad(conversation_id: uuid.UUID, seq: int) -> bytes:
    return f"{conversation_id}:{seq}".encode()


def _encrypt(conversation_id: uuid.UUID, seq: int, content: list[dict[str, Any]]) -> bytes:
    raw = json.dumps(content, separators=(",", ":"), ensure_ascii=False).encode()
    return get_keyring().encrypt(raw, aad=_aad(conversation_id, seq))


def _decrypt(message: AIMessage) -> list[dict[str, Any]]:
    raw = get_keyring().decrypt(message.content_enc, aad=_aad(message.conversation_id, message.seq))
    content: list[dict[str, Any]] = json.loads(raw)
    return content


async def next_seq(session: AsyncSession, conversation_id: uuid.UUID) -> int:
    current = await session.scalar(
        select(func.max(AIMessage.seq)).where(AIMessage.conversation_id == conversation_id)
    )
    return (current or 0) + 1


async def append_message(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    seq: int,
    role: str,
    content: list[dict[str, Any]],
    kind: str = "message",
    model: str | None = None,
    stop_reason: str | None = None,
) -> AIMessage:
    message = AIMessage(
        user_id=user_id,
        conversation_id=conversation_id,
        seq=seq,
        role=role,
        kind=kind,
        content_enc=_encrypt(conversation_id, seq, content),
        model=model,
        stop_reason=stop_reason,
    )
    session.add(message)
    await session.commit()
    return message


async def load_history(session: AsyncSession, conversation_id: uuid.UUID) -> list[dict[str, Any]]:
    """Messages in API shape. Consecutive same-role turns are merged deterministically."""
    rows = await session.scalars(
        select(AIMessage)
        .where(AIMessage.conversation_id == conversation_id)
        .order_by(AIMessage.seq)
    )
    history: list[dict[str, Any]] = []
    for message in rows:
        content = _decrypt(message)
        if history and history[-1]["role"] == message.role:
            history[-1]["content"] = [*history[-1]["content"], *content]
        else:
            history.append({"role": message.role, "content": content})
    return history


async def conversation_detail(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> ConversationDetailOut:
    conversation = await get_conversation(session, user_id, conversation_id)
    rows = list(
        await session.scalars(
            select(AIMessage)
            .where(AIMessage.conversation_id == conversation.id)
            .order_by(AIMessage.seq)
        )
    )
    results: dict[str, bool] = {}
    decrypted = [(m, _decrypt(m)) for m in rows]
    for message, content in decrypted:
        if message.kind == "tool_results":
            for block in content:
                if block.get("type") == "tool_result":
                    results[str(block.get("tool_use_id"))] = not block.get("is_error", False)

    display: list[DisplayMessage] = []
    for message, content in decrypted:
        if message.kind == "tool_results":
            continue
        texts = [
            str(b.get("text", ""))
            for b in content
            if b.get("type") == "text" and not str(b.get("text", "")).startswith("<context>")
        ]
        tool_calls = [
            ToolCallOut(name=str(b.get("name")), ok=results.get(str(b.get("id")), False))
            for b in content
            if b.get("type") == "tool_use"
        ]
        text = "\n\n".join(t for t in texts if t)
        if not text and not tool_calls:
            continue
        if display and display[-1].role == message.role == "assistant":
            previous = display[-1]
            display[-1] = previous.model_copy(
                update={
                    "text": "\n\n".join(t for t in (previous.text, text) if t),
                    "tool_calls": [*previous.tool_calls, *tool_calls],
                }
            )
            continue
        display.append(
            DisplayMessage(
                id=message.id,
                role=message.role,
                text=text,
                tool_calls=tool_calls,
                created_at=message.created_at,
            )
        )
    return ConversationDetailOut(
        conversation=ConversationOut.model_validate(conversation), messages=display
    )


async def touch_conversation(
    session: AsyncSession, conversation_id: uuid.UUID, *, first_user_text: str | None
) -> None:
    conversation = await session.get(AIConversation, conversation_id)
    if conversation is None:
        return
    conversation.last_message_at = utc_now()
    if not conversation.title and first_user_text:
        title = " ".join(first_user_text.split())
        conversation.title = title[:80] + ("…" if len(title) > 80 else "")
    await session.commit()


# ------------------------------------------------------------------ usage and budget


async def record_usage(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    route: str,
    model: str,
    usage: Usage,
    conversation_id: uuid.UUID | None,
    request_id: str | None,
) -> int:
    micros = cost_micros(model, usage)
    session.add(
        AIUsageLedger(
            user_id=user_id,
            route=route,
            model=model,
            api_request_id=request_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            cost_usd_micros=micros,
            conversation_id=conversation_id,
        )
    )
    await session.commit()
    return micros


def month_start(timezone: str, today: date) -> datetime:
    return local_day_start(timezone, today.replace(day=1))


async def month_to_date_micros(
    session: AsyncSession, user_id: uuid.UUID, *, timezone: str, today: date
) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(AIUsageLedger.cost_usd_micros), 0)).where(
            AIUsageLedger.user_id == user_id,
            AIUsageLedger.created_at >= month_start(timezone, today),
        )
    )
    return int(total or 0)


async def usage_by_route(
    session: AsyncSession, user_id: uuid.UUID, *, timezone: str, today: date
) -> list[UsageByRoute]:
    rows = await session.execute(
        select(
            AIUsageLedger.route,
            func.count(),
            func.sum(AIUsageLedger.cost_usd_micros),
            func.sum(AIUsageLedger.input_tokens),
            func.sum(AIUsageLedger.output_tokens),
            func.sum(AIUsageLedger.cache_read_tokens),
        )
        .where(
            AIUsageLedger.user_id == user_id,
            AIUsageLedger.created_at >= month_start(timezone, today),
        )
        .group_by(AIUsageLedger.route)
        .order_by(AIUsageLedger.route)
    )
    return [
        UsageByRoute(
            route=route,
            requests=int(count),
            cost_usd=round(int(micros or 0) / 1_000_000, 4),
            input_tokens=int(inp or 0),
            output_tokens=int(out or 0),
            cache_read_tokens=int(cached or 0),
        )
        for route, count, micros, inp, out, cached in rows
    ]
