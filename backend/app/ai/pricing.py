"""Model prices used for the usage ledger and the monthly budget.

Prices are USD per million tokens, which is the same number as micro-USD per token, so
cost in micro-USD = tokens x price. Source: Anthropic published rates (cached 2026-11-03).
Cache writes use the 5-minute TTL multiplier (1.25x input). Verify before relying on them
for billing; the Claude Console is the source of truth for invoices.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger("app.ai.pricing")


@dataclass(frozen=True, slots=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write: float


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(input=4.00, output=20.00, cache_read=0.20, cache_write=5.00),
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_read=0.10, cache_write=2.50),
    # Haiku 5.5: cache rates assumed at the usual 0.1x / 1.25x multipliers.
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_read=0.01, cache_write=0.125),
}
_FALLBACK = PRICES["claude-opus-5-5"]  # unknown models are costed conservatively


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def cost_micros(model: str, usage: Usage) -> int:
    price = PRICES.get(model)
    if price is None:
        logger.warning("unknown_model_price", extra={"model": model})
        price = _FALLBACK
    total = (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_tokens * price.cache_read
        + usage.cache_write_tokens * price.cache_write
    )
    return round(total)
