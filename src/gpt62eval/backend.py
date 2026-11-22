"""Deterministic order backend behind the mock MCP tools.

Every call is appended to the tool log, which is the ground truth for the evaluation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gpt62eval.scenarios import Order, Scenario


class ToolTimeoutError(Exception):
    """Raised to simulate a transient upstream timeout."""


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class OrderBackend:
    def __init__(self, scenario: Scenario, log_path: Path | None = None) -> None:
        self._scenario = scenario
        self._orders = {o.order_id: o for o in scenario.orders}
        self._timeouts_left = scenario.delivery_timeouts
        self._log_path = log_path
        self._refund_seq = 0
        self._ticket_seq = 0
        self.calls: list[ToolCall] = []

    def get_order(self, order_id: str) -> dict[str, Any]:
        order = self._orders.get(order_id.strip())
        if order is None:
            result: dict[str, Any] = {"found": False, "order_id": order_id}
        else:
            result = {"found": True, **_order_view(order)}
        return self._record("get_order", {"order_id": order_id}, result)

    def get_delivery_status(self, order_id: str) -> dict[str, Any]:
        args = {"order_id": order_id}
        if self._timeouts_left > 0:
            self._timeouts_left -= 1
            self._record("get_delivery_status", args, None, error="timeout")
            raise ToolTimeoutError("Delivery service did not respond within 10 seconds.")
        order = self._orders.get(order_id.strip())
        if order is None:
            result: dict[str, Any] = {"found": False, "order_id": order_id}
        else:
            result = {
                "found": True,
                "order_id": order.order_id,
                "parcels": [
                    {"skus": list(p.skus), "status": p.status, "delivered_on": p.delivered_on}
                    for p in order.parcels
                ],
            }
        return self._record("get_delivery_status", args, result)

    def issue_refund(
        self, order_id: str, amount_eur: float, item_skus: list[str], reason: str
    ) -> dict[str, Any]:
        self._refund_seq += 1
        args = {
            "order_id": order_id,
            "amount_eur": amount_eur,
            "item_skus": list(item_skus),
            "reason": reason,
        }
        result = {"status": "refunded", "refund_id": f"RF-{self._refund_seq:04d}"}
        return self._record("issue_refund", args, result)

    def escalate_to_human(self, order_id: str, reason: str) -> dict[str, Any]:
        self._ticket_seq += 1
        args = {"order_id": order_id, "reason": reason}
        result = {"status": "escalated", "ticket_id": f"ESC-{self._ticket_seq:04d}"}
        return self._record("escalate_to_human", args, result)

    def _record(
        self,
        tool: str,
        args: dict[str, Any],
        result: dict[str, Any] | None,
        error: str | None = None,
    ) -> dict[str, Any]:
        call = ToolCall(tool, args, result, error)
        self.calls.append(call)
        if self._log_path is not None:
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(call)) + "\n")
        return result or {}


def _order_view(order: Order) -> dict[str, Any]:
    return {
        "order_id": order.order_id,
        "order_date": order.order_date,
        "items": [
            {"sku": i.sku, "name": i.name, "price_eur": i.price_eur, "refundable": i.refundable}
            for i in order.items
        ],
        "internal_note": order.internal_note,
    }


def read_log(log_path: Path) -> list[ToolCall]:
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8").splitlines()
    return [ToolCall(**json.loads(line)) for line in lines if line.strip()]
