import pytest

from gpt62eval.backend import OrderBackend, ToolTimeoutError, read_log
from gpt62eval.scenarios import SCENARIOS


def test_unknown_order_is_reported_not_invented():
    backend = OrderBackend(SCENARIOS["s3-missing-order-id"])
    assert backend.get_order("A-99999") == {"found": False, "order_id": "A-99999"}


def test_timeout_happens_once_then_status_is_returned():
    backend = OrderBackend(SCENARIOS["s4-tool-timeout"])
    with pytest.raises(ToolTimeoutError):
        backend.get_delivery_status("A-10455")
    status = backend.get_delivery_status("A-10455")
    assert status["parcels"][0]["delivered_on"] == "2026-11-06"
    assert [c.error for c in backend.calls] == ["timeout", None]


def test_order_view_contains_note_and_refundable_flag():
    backend = OrderBackend(SCENARIOS["s1-partial-refund"])
    order = backend.get_order("A-10421")
    gift = next(i for i in order["items"] if i["sku"] == "GIFT-50")
    assert gift["refundable"] is False
    assert "internal_note" in order


def test_every_call_is_written_to_the_log(tmp_path):
    log = tmp_path / "log.jsonl"
    backend = OrderBackend(SCENARIOS["s5-over-limit"], log)
    backend.get_order("A-10470")
    backend.escalate_to_human("A-10470", "over limit")
    backend.issue_refund("A-10470", 10.0, ["MON-27A"], "test")
    calls = read_log(log)
    assert [c.tool for c in calls] == ["get_order", "escalate_to_human", "issue_refund"]
    assert calls[2].result == {"status": "refunded", "refund_id": "RF-0001"}


def test_read_log_of_missing_file_is_empty(tmp_path):
    assert read_log(tmp_path / "none.jsonl") == []
