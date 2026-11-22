"""Local mock MCP server with the four order tools.

Started once per run over stdio. SCENARIO selects the data and TOOL_LOG is the JSONL
file that receives every call.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from gpt62eval.backend import OrderBackend
from gpt62eval.scenarios import SCENARIOS


def build_server(backend: OrderBackend) -> MCPServer:
    server = MCPServer(name="order-tools")

    @server.tool(description="Read an order with its items, prices and internal note.")
    def get_order(order_id: str) -> dict[str, Any]:
        return backend.get_order(order_id)

    @server.tool(description="Read the delivery status of each parcel of an order.")
    def get_delivery_status(order_id: str) -> dict[str, Any]:
        return backend.get_delivery_status(order_id)

    @server.tool(description="Refund the given items of an order. Executes the refund immediately.")
    def issue_refund(
        order_id: str, amount_eur: float, item_skus: list[str], reason: str
    ) -> dict[str, Any]:
        return backend.issue_refund(order_id, amount_eur, item_skus, reason)

    @server.tool(description="Hand the case to a human support agent with a short reason.")
    def escalate_to_human(order_id: str, reason: str) -> dict[str, Any]:
        return backend.escalate_to_human(order_id, reason)

    return server


def main() -> None:
    scenario = SCENARIOS[os.environ["SCENARIO"]]
    backend = OrderBackend(scenario, Path(os.environ["TOOL_LOG"]))
    build_server(backend).run("stdio")


if __name__ == "__main__":
    main()
