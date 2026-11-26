"""Provider adapters for roadmap drafting: one validated structured reply per call.

`drafting.py` decides what to ask; these classes only send one request to the user's own
provider and return the reply parsed into the requested Pydantic schema. The service depends
only on the `RoadmapGenerator` protocol, so tests use a scripted fake and never spend money.
Nothing is saved here: the user reviews the draft first.
"""

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import anthropic
import openai
from pydantic import BaseModel, ValidationError

from app.ai.client import ADAPTIVE_MODELS, FALLBACK_BETA, FALLBACK_MODELS, claude_features
from app.ai.connections import Connection
from app.ai.openai_compat import map_error
from app.ai.pricing import Usage
from app.core.config import Settings, get_settings
from app.core.errors import ServiceUnavailable

logger = logging.getLogger("app.roadmaps.generator")


@dataclass(frozen=True, slots=True)
class AIReply[T: BaseModel]:
    """`parsed` is None when the model refused, was cut off or broke the schema.

    Usage is billed either way, so every reply is recorded in the ledger.
    """

    parsed: T | None
    refused: bool
    model: str
    usage: Usage
    request_id: str | None
    free: bool = False


class RoadmapGenerator(Protocol):
    async def complete[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], max_tokens: int
    ) -> AIReply[T]: ...


class AnthropicRoadmapGenerator:
    def __init__(self, settings: Settings, api_key: str, model: str) -> None:
        self._settings = settings
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=300.0, max_retries=2)

    async def complete[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], max_tokens: int
    ) -> AIReply[T]:
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_format": schema,
            **claude_features(self._model),
        }
        if self._model in ADAPTIVE_MODELS:
            params["output_config"] = {"effort": "medium"}
        if self._settings.ai_refusal_fallback and self._model in FALLBACK_MODELS:
            params |= {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        try:
            response = await self._client.beta.messages.parse(**params)
        except anthropic.RateLimitError as exc:
            raise ServiceUnavailable(
                "Claude is busy; try again shortly.", code="ai_rate_limited"
            ) from exc
        except anthropic.AuthenticationError as exc:
            raise ServiceUnavailable(
                "Anthropic rejected your API key. Update it in Settings.", code="ai_auth_failed"
            ) from exc
        except anthropic.APIStatusError as exc:
            logger.warning("anthropic_status_error", extra={"status": exc.status_code})
            raise ServiceUnavailable("Claude returned an error.", code="ai_unavailable") from exc
        except anthropic.APIConnectionError as exc:
            raise ServiceUnavailable("Could not reach Claude.", code="ai_unreachable") from exc

        usage = response.usage
        cost_usage = Usage(
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )
        refused = response.stop_reason == "refusal"
        complete = not refused and response.stop_reason != "max_tokens"
        parsed = response.parsed_output if complete else None
        return AIReply(
            parsed=parsed if isinstance(parsed, schema) else None,
            refused=refused,
            model=response.model,
            usage=cost_usage,
            request_id=getattr(response, "_request_id", None),
        )


JSON_INSTRUCTIONS = (
    "Reply with one JSON object only, no prose and no code fences, matching this JSON "
    "Schema:\n{schema}"
)


def parse_json[T: BaseModel](text: str, schema: type[T]) -> T | None:
    """Pull the JSON object out of a model reply and validate it; None if it does not fit."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return schema.model_validate_json(text[start : end + 1])
    except ValidationError:
        return None


class OpenAICompatibleRoadmapGenerator:
    """Replies from OpenAI, Gemini, OpenRouter, Groq, Ollama or a custom endpoint.

    Asks for JSON matching the schema (response_format when the provider supports it, plain
    instructions otherwise) and validates the reply before anyone sees it.
    """

    def __init__(self, *, api_key: str | None, base_url: str, model: str, free: bool) -> None:
        self._model = model
        self._free = free
        # Learned on the first refusal, so a draft's later calls skip the failing attempt.
        self._structured = True
        self._client = openai.AsyncOpenAI(
            api_key=api_key or "not-needed", base_url=base_url, timeout=300.0, max_retries=2
        )

    async def complete[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], max_tokens: int
    ) -> AIReply[T]:
        json_schema = schema.model_json_schema()
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": system
                    + "\n\n"
                    + JSON_INSTRUCTIONS.format(schema=json.dumps(json_schema)),
                },
                {"role": "user", "content": user},
            ],
        }
        structured: Any = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": json_schema},
        }
        try:
            response = None
            if self._structured:
                try:
                    response = await self._client.chat.completions.create(
                        **params, response_format=structured
                    )
                except openai.BadRequestError:
                    # Not every provider or model supports structured output; plain JSON it is.
                    self._structured = False
            if response is None:
                response = await self._client.chat.completions.create(**params)
        except openai.OpenAIError as exc:
            error = map_error(exc)
            raise ServiceUnavailable(str(error), code=error.code) from exc

        usage = response.usage
        cost_usage = Usage(
            input_tokens=(usage.prompt_tokens or 0) if usage else 0,
            output_tokens=(usage.completion_tokens or 0) if usage else 0,
        )
        choice = response.choices[0] if response.choices else None
        finish = choice.finish_reason if choice else None
        text = (choice.message.content or "") if choice else ""
        refused = finish == "content_filter" or bool(choice and choice.message.refusal)
        parsed = None if refused or finish == "length" else parse_json(text, schema)
        return AIReply(
            parsed=parsed,
            refused=refused,
            model=response.model or self._model,
            usage=cost_usage,
            request_id=getattr(response, "_request_id", None),
            free=self._free,
        )


@lru_cache(maxsize=128)
def generator_for_connection(connection: Connection) -> RoadmapGenerator:
    """One client per user connection: drafts bill to the requesting user's own account."""
    if connection.kind == "anthropic":
        return AnthropicRoadmapGenerator(get_settings(), connection.api_key or "", connection.model)
    return OpenAICompatibleRoadmapGenerator(
        api_key=connection.api_key,
        base_url=connection.base_url or "",
        model=connection.model,
        free=connection.free,
    )
