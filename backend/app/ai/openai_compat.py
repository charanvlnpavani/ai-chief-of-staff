"""OpenAI-compatible Chat Completions adapter (OpenAI, Gemini, OpenRouter, Groq, Ollama, ...).

The orchestrator and stored history use Anthropic-style content blocks (text, tool_use,
tool_result). This module translates them to Chat Completions messages on the way out and
turns the streamed reply back into blocks, so the same Chief of Staff loop and tools run on
any model that supports function calling.
"""

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import openai

from app.ai.client import ChatModelError, TextDelta, TurnResult
from app.ai.pricing import Usage
from app.ai.providers import openai_http_client

logger = logging.getLogger("app.ai.openai_compat")

PLACEHOLDER_KEY = "not-needed"  # local servers ignore the key, but the SDK requires one

FINISH_TO_STOP = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}


# ------------------------------------------------------------------ outgoing translation


def system_text(system: list[dict[str, Any]]) -> str:
    return "\n\n".join(b["text"] for b in system if b.get("type") == "text")


def to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return json.dumps(content)


def to_openai_messages(
    system: list[dict[str, Any]], messages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Anthropic-style history -> Chat Completions messages. Thinking blocks are dropped."""
    out: list[dict[str, Any]] = []
    text = system_text(system)
    if text:
        out.append({"role": "system", "content": text})
    for message in messages:
        role, content = message["role"], message["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if role == "assistant":
            texts = [b["text"] for b in content if b.get("type") == "text" and b.get("text")]
            calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b.get("input", {}))},
                }
                for b in content
                if b.get("type") == "tool_use"
            ]
            entry: dict[str, Any] = {"role": "assistant", "content": "\n".join(texts) or None}
            if calls:
                entry["tool_calls"] = calls
            out.append(entry)
            continue
        # user turn: tool results become `tool` messages (they must follow the assistant
        # turn that asked for them), any remaining text becomes a user message
        for block in content:
            if block.get("type") == "tool_result":
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": _result_text(block.get("content", "")),
                    }
                )
        user_text = "\n".join(b["text"] for b in content if b.get("type") == "text")
        if user_text:
            out.append({"role": "user", "content": user_text})
    return out


# ------------------------------------------------------------------ incoming assembly


@dataclass
class _Call:
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class StreamAssembler:
    """Collects streamed chunks into text, tool calls, finish reason and usage."""

    text: list[str] = field(default_factory=list)
    calls: dict[int, _Call] = field(default_factory=dict)
    finish_reason: str | None = None
    model: str | None = None
    usage: Usage = field(default_factory=Usage)

    def add(self, chunk: Any) -> str | None:
        """Feed one chunk; returns any new text to show the user."""
        self.model = getattr(chunk, "model", None) or self.model
        if getattr(chunk, "usage", None):
            u = chunk.usage
            details = getattr(u, "prompt_tokens_details", None)
            cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
            self.usage = Usage(
                input_tokens=max((u.prompt_tokens or 0) - cached, 0),
                output_tokens=u.completion_tokens or 0,
                cache_read_tokens=cached,
            )
        new_text = None
        for choice in getattr(chunk, "choices", None) or []:
            delta = choice.delta
            if getattr(delta, "content", None):
                self.text.append(delta.content)
                new_text = (new_text or "") + delta.content
            for call in getattr(delta, "tool_calls", None) or []:
                slot = self.calls.setdefault(call.index, _Call())
                slot.id = call.id or slot.id
                if call.function is not None:
                    slot.name = call.function.name or slot.name
                    slot.arguments += call.function.arguments or ""
            if choice.finish_reason:
                self.finish_reason = choice.finish_reason
        return new_text

    def blocks(self) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        text = "".join(self.text)
        if text:
            content.append({"type": "text", "text": text})
        for index in sorted(self.calls):
            call = self.calls[index]
            try:
                arguments = json.loads(call.arguments) if call.arguments.strip() else {}
            except json.JSONDecodeError:
                arguments = {"_unparsed": call.arguments[:2000]}  # the tool rejects it cleanly
            content.append(
                {
                    "type": "tool_use",
                    "id": call.id or f"call_{index}",
                    "name": call.name,
                    "input": arguments if isinstance(arguments, dict) else {"value": arguments},
                }
            )
        return content

    def stop_reason(self) -> str:
        if self.calls:
            return "tool_use"
        return FINISH_TO_STOP.get(self.finish_reason or "stop", "end_turn")


# ------------------------------------------------------------------ the model


def make_client(
    api_key: str | None, base_url: str, *, allow_private: bool, timeout: float = 120.0
) -> openai.AsyncOpenAI:
    return openai.AsyncOpenAI(
        api_key=api_key or PLACEHOLDER_KEY,
        base_url=base_url,
        timeout=timeout,
        max_retries=2,
        http_client=openai_http_client(allow_private=allow_private),
    )


def map_error(exc: openai.OpenAIError) -> ChatModelError:
    if isinstance(exc, openai.RateLimitError):
        return ChatModelError(
            "ai_rate_limited",
            "The AI provider is busy or out of free quota; try again shortly.",
            retryable=True,
        )
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return ChatModelError(
            "ai_auth_failed", "The AI provider rejected your API key. Update it in Settings."
        )
    if isinstance(exc, openai.NotFoundError):
        return ChatModelError(
            "ai_model_unavailable", "That model is not available. Pick another in Settings."
        )
    if isinstance(exc, openai.BadRequestError):
        return ChatModelError(
            "ai_bad_request",
            "The AI provider refused the request. The model may not support tool use; "
            "try another model.",
        )
    if isinstance(exc, openai.APIStatusError):
        logger.warning("openai_compat_status_error", extra={"status": exc.status_code})
        return ChatModelError(
            "ai_unavailable", "The AI provider returned an error.", retryable=exc.status_code >= 500
        )
    return ChatModelError("ai_unreachable", "Could not reach the AI provider.", retryable=True)


class OpenAICompatibleChatModel:
    def __init__(
        self,
        *,
        provider: str,
        api_key: str | None,
        base_url: str,
        model: str,
        max_tokens: int,
        free: bool,
        allow_private: bool = False,
    ) -> None:
        self.provider = provider
        self.model_name = model
        self.free = free
        self._max_tokens = max_tokens
        self._client = make_client(api_key, base_url, allow_private=allow_private)

    async def stream_turn(
        self,
        *,
        system: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[TextDelta | TurnResult]:
        params: dict[str, Any] = {
            "model": self.model_name,
            "messages": to_openai_messages(system, messages),
            "max_tokens": self._max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            params["tools"] = to_openai_tools(tools)
        assembler = StreamAssembler()
        try:
            stream = await self._client.chat.completions.create(**params)
            async for chunk in stream:
                new_text = assembler.add(chunk)
                if new_text:
                    yield TextDelta(new_text)
        except openai.OpenAIError as exc:
            raise map_error(exc) from exc
        yield TurnResult(
            content=assembler.blocks(),
            stop_reason=assembler.stop_reason(),
            model=assembler.model or self.model_name,
            usage=assembler.usage,
            free=self.free,
        )
