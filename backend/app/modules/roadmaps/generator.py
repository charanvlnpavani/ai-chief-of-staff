"""Roadmap drafts from Claude, returned in a fixed, validated shape (structured outputs).

The service depends only on `RoadmapGenerator`, so tests use a scripted fake and never
spend money. The draft is never saved here: the user reviews it first.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import anthropic

from app.ai.client import FALLBACK_BETA
from app.ai.pricing import Usage
from app.core.config import Settings, get_settings
from app.core.errors import ServiceUnavailable
from app.modules.roadmaps.schemas import PlannedRoadmap

logger = logging.getLogger("app.roadmaps.generator")

SYSTEM_PROMPT = """\
You design self-study roadmaps inside Personal OS, a private planning app.

Given a subject, write a roadmap that takes a learner from basics to professional level.
- Group the days into the levels basic, intermediate, advanced and pro, in that order.
  Every level should have at least two days.
- Each day has one to three concrete tasks the learner can finish and tick off that day:
  learn a named concept, build or practise something specific, or review. Avoid vague tasks
  such as "study more".
- A task title says what to do in under 15 words. The detail says how, in one or two
  sentences. Minutes is a realistic estimate; the tasks of one day should add up to about
  the daily time the learner has.
- Roughly every seventh day, make a review or small project day that uses earlier topics.
- Use your own wording. Do not reproduce other roadmaps or course outlines.
- If the subject is not something a person can learn step by step, make the roadmap about
  the closest learnable skill and say so in the title.
"""


@dataclass(frozen=True, slots=True)
class GeneratedRoadmap:
    """`plan` is None when Claude refused or the reply was cut off; usage is still billed."""

    plan: PlannedRoadmap | None
    refused: bool
    model: str
    usage: Usage
    request_id: str | None


class RoadmapGenerator(Protocol):
    async def generate(
        self, *, subject: str, target_days: int, minutes_per_day: int
    ) -> GeneratedRoadmap: ...


class AnthropicRoadmapGenerator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=300.0,
            max_retries=2,
        )

    async def generate(
        self, *, subject: str, target_days: int, minutes_per_day: int
    ) -> GeneratedRoadmap:
        user_text = (
            f"<subject>{subject}</subject>\n"
            f"Plan about {target_days} days with about {minutes_per_day} minutes per day."
        )
        params: dict[str, Any] = {
            "model": self._settings.ai_model_chat,
            "max_tokens": 16000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_text}],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "medium"},
            "output_format": PlannedRoadmap,
        }
        if self._settings.ai_refusal_fallback:
            params |= {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        try:
            response = await self._client.beta.messages.parse(**params)
        except anthropic.RateLimitError as exc:
            raise ServiceUnavailable(
                "Claude is busy; try again shortly.", code="ai_rate_limited"
            ) from exc
        except anthropic.AuthenticationError as exc:
            raise ServiceUnavailable(
                "The Anthropic API key was rejected.", code="ai_auth_failed"
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
        return GeneratedRoadmap(
            plan=response.parsed_output if complete else None,
            refused=refused,
            model=response.model,
            usage=cost_usage,
            request_id=getattr(response, "_request_id", None),
        )


@lru_cache
def _anthropic_generator() -> AnthropicRoadmapGenerator:
    return AnthropicRoadmapGenerator(get_settings())


def get_roadmap_generator() -> RoadmapGenerator:
    if not get_settings().ai_enabled:
        raise ServiceUnavailable(
            "Roadmaps for new subjects need ANTHROPIC_API_KEY in backend/.env. "
            "Built-in roadmaps work without it.",
            code="ai_not_configured",
        )
    return _anthropic_generator()
