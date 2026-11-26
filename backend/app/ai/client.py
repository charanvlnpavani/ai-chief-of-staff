"""Model client: a small interface plus the Anthropic implementation.

The orchestrator depends only on `ChatModel`, so tests run against a scripted fake and never
spend money. The real client streams text as it is generated and returns the final message
(content blocks kept verbatim for replay).
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol

import anthropic

from app.ai import connections
from app.ai.pricing import Usage
from app.api.deps import CurrentAuth, SessionDep, SettingsDep
from app.core.config import Settings, get_settings

logger = logging.getLogger("app.ai.client")

FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Current-generation Claude models accept adaptive thinking and `effort`; older ones may not.
ADAPTIVE_MODELS = frozenset({"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"})
# Server-side refusal fallback ("default" routing) is offered for these, not for Haiku.
FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-sonnet-5-5"})


def claude_features(model: str) -> dict[str, Any]:
    """Request options a given Claude model supports."""
    params: dict[str, Any] = {}
    if model in ADAPTIVE_MODELS:
        params["thinking"] = {"type": "adaptive"}
    return params


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class TurnResult:
    content: list[dict[str, Any]]
    stop_reason: str | None
    model: str
    usage: Usage
    request_id: str | None = None
    free: bool = False  # costs nothing (local Ollama, OpenRouter `:free` models)
    extra: dict[str, Any] = field(default_factory=dict)


class ChatModelError(Exception):
    """A model call failed; `code` is safe to show the user."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ChatModel(Protocol):
    model_name: str

    def stream_turn(
        self,
        *,
        system: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[TextDelta | TurnResult]: ...


class AnthropicChatModel:
    """Claude via the official SDK: adaptive thinking, per-route effort, prompt caching and
    server-side refusal fallback (on by default; set AI_REFUSAL_FALLBACK=false to turn off)."""

    def __init__(self, settings: Settings, api_key: str, model: str | None = None) -> None:
        self._settings = settings
        self.model_name = model or settings.ai_model_chat
        self.free = False
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=120.0,
            max_retries=2,
        )

    async def stream_turn(
        self,
        *,
        system: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[TextDelta | TurnResult]:
        params: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": self._settings.ai_max_tokens,
            "system": system,
            "tools": tools,
            "messages": messages,
            **claude_features(self.model_name),
            # Automatic caching for the growing conversation tail; the system prompt carries
            # its own explicit breakpoint.
            "cache_control": {"type": "ephemeral"},
        }
        try:
            if self.model_name in ADAPTIVE_MODELS:
                params["output_config"] = {"effort": self._settings.ai_effort_chat}
            if self._settings.ai_refusal_fallback and self.model_name in FALLBACK_MODELS:
                manager: Any = self._client.beta.messages.stream(
                    **params, betas=[FALLBACK_BETA], fallbacks="default"
                )
            else:
                manager = self._client.messages.stream(**params)
            async with manager as stream:
                async for event in stream:
                    if event.type == "text":
                        yield TextDelta(event.text)
                final = await stream.get_final_message()
        except anthropic.RateLimitError as exc:
            raise ChatModelError(
                "ai_rate_limited", "Claude is busy; try again shortly.", retryable=True
            ) from exc
        except anthropic.AuthenticationError as exc:
            raise ChatModelError(
                "ai_auth_failed", "Anthropic rejected your API key. Update it in Settings."
            ) from exc
        except anthropic.APIStatusError as exc:
            logger.warning("anthropic_status_error", extra={"status": exc.status_code})
            raise ChatModelError(
                "ai_unavailable", "Claude returned an error.", retryable=exc.status_code >= 500
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ChatModelError(
                "ai_unreachable", "Could not reach Claude.", retryable=True
            ) from exc
        except ValueError as exc:  # tool input the SDK could not parse at all
            raise ChatModelError(
                "ai_bad_output", "Claude returned malformed tool input.", retryable=True
            ) from exc

        usage = final.usage
        yield TurnResult(
            content=[block.model_dump(mode="json", exclude_none=True) for block in final.content],
            stop_reason=final.stop_reason,
            model=final.model,
            usage=Usage(
                input_tokens=usage.input_tokens or 0,
                output_tokens=usage.output_tokens or 0,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            ),
            request_id=getattr(final, "_request_id", None),
        )


@lru_cache(maxsize=128)
def model_for_connection(connection: connections.Connection) -> ChatModel:
    """One client (and connection pool) per user connection; calls run on the user's key."""
    settings = get_settings()
    if connection.kind == "anthropic":
        return AnthropicChatModel(settings, connection.api_key or "", connection.model)
    from app.ai.openai_compat import OpenAICompatibleChatModel

    return OpenAICompatibleChatModel(
        provider=connection.provider,
        api_key=connection.api_key,
        base_url=connection.base_url or "",
        model=connection.model,
        max_tokens=settings.ai_max_tokens,
        free=connection.free,
        allow_private=settings.private_endpoints_allowed,
    )


async def get_chat_model(
    auth: CurrentAuth, session: SessionDep, settings: SettingsDep
) -> ChatModel:
    """The signed-in user's model client. Without a usable connection: 403 ai_key_required."""
    return model_for_connection(
        await connections.require_connection(session, auth.user.id, settings)
    )
