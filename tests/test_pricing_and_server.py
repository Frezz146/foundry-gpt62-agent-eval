import pytest

from gpt62eval.backend import OrderBackend
from gpt62eval.mcp_server import build_server
from gpt62eval.pricing import cost_usd
from gpt62eval.scenarios import SCENARIOS


def test_cost_uses_cached_and_output_rates():
    # 1M input of which 500k cached, 100k output on GPT-6.2 Sol
    assert cost_usd("gpt-6.2-sol", 1_000_000, 500_000, 100_000) == pytest.approx(
        0.5 * 2.00 + 0.5 * 0.10 + 0.1 * 10.00
    )


def test_cost_bills_cache_writes_separately():
    assert cost_usd("gpt-6.2-astra", 1_000_000, 0, 0, 1_000_000) == pytest.approx(10.00)


def test_cost_rejects_inconsistent_token_counts():
    with pytest.raises(ValueError):
        cost_usd("gpt-6.2-sol", 10, 20, 0)


async def test_server_exposes_exactly_four_tools():
    server = build_server(OrderBackend(SCENARIOS["s1-partial-refund"]))
    names = sorted(t.name for t in await server.list_tools())
    assert names == ["escalate_to_human", "get_delivery_status", "get_order", "issue_refund"]
