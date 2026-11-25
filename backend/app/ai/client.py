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

from app.ai.pricing import Usage
from app.core.config import Settings, get_settings
from app.core.errors import ServiceUnavailable

logger = logging.getLogger("app.ai.client")

FALLBACK_BETA = "server-side-fallback-2026-07-01"


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

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.model_name = settings.ai_model_chat
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
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
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self._settings.ai_effort_chat},
            # Automatic caching for the growing conversation tail; the system prompt carries
            # its own explicit breakpoint.
            "cache_control": {"type": "ephemeral"},
        }
        try:
            if self._settings.ai_refusal_fallback:
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
            raise ChatModelError("ai_auth_failed", "The Anthropic API key was rejected.") from exc
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


@lru_cache
def _anthropic_model() -> AnthropicChatModel:
    return AnthropicChatModel(get_settings())  # restart the API after rotating the key


def get_chat_model() -> ChatModel:
    if not get_settings().ai_enabled:
        raise ServiceUnavailable(
            "The Chief of Staff needs ANTHROPIC_API_KEY in backend/.env.", code="ai_not_configured"
        )
    return _anthropic_model()
