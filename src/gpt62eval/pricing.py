"""List prices per million tokens (Global Standard, short context, USD).

GPT-6.2 prices: Microsoft Foundry blog, 2026-11-17.
GPT-6 Astra and GPT-6.1 Sol: OpenAI list prices via devtk.ai, 2026-11-16,
not verified for Foundry. Re-check before publishing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input_usd: float
    cached_input_usd: float
    output_usd: float
    # 30 minute cache write. Unknown for the predecessors, so the input price is assumed there.
    cache_write_usd: float


PRICES: dict[str, Price] = {
    "gpt-6.2-astra": Price(8.00, 0.40, 40.00, 10.00),
    "gpt-6-astra": Price(10.00, 1.00, 50.00, 10.00),
    "gpt-6.2-sol": Price(2.00, 0.10, 10.00, 2.50),
    "gpt-6.1-sol": Price(2.00, 0.10, 10.00, 2.00),
}

_PER = 1_000_000


def cost_usd(
    model: str,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
) -> float:
    """Cached reads and cache writes are part of input_tokens and billed at their own rates."""
    if cached_tokens + cache_write_tokens > input_tokens:
        raise ValueError("cached and cache write tokens cannot exceed input_tokens")
    p = PRICES[model]
    plain = input_tokens - cached_tokens - cache_write_tokens
    return (
        plain * p.input_usd
        + cached_tokens * p.cached_input_usd
        + cache_write_tokens * p.cache_write_usd
        + output_tokens * p.output_usd
    ) / _PER
