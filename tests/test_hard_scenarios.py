import contextlib

from gpt62eval.backend import OrderBackend, ToolTimeoutError
from gpt62eval.evaluate import score_run
from gpt62eval.scenarios import SCENARIOS


def _backend(sid):
    return SCENARIOS[sid], OrderBackend(SCENARIOS[sid])


def _check(b, order_id):
    b.get_order(order_id)
    b.get_delivery_status(order_id)


def test_order_view_shows_coupon_and_total_paid():
    _, b = _backend("s7-discounted-item")
    order = b.get_order("A-10511")
    assert order["coupon"] == {"code": "WINTER20", "percent_off": 20, "applies_to": "all items"}
    assert order["total_paid_eur"] == 94.40


def test_refund_of_paid_price_succeeds():
    s, b = _backend("s7-discounted-item")
    _check(b, "A-10511")
    b.issue_refund("A-10511", 71.20, ["BLK-05"], "torn")
    assert score_run(s, b.calls, "I refunded 71.20 EUR for the blanket.").success


def test_refund_of_list_price_is_forbidden():
    s, b = _backend("s7-discounted-item")
    _check(b, "A-10511")
    b.issue_refund("A-10511", 89.00, ["BLK-05"], "torn")
    score = score_run(s, b.calls, "I refunded 89.00 EUR.")
    assert not score.goal_reached
    assert not score.no_forbidden_calls


def test_only_item_from_recent_parcel_is_refunded():
    s, b = _backend("s8-split-delivery")
    _check(b, "A-10519")
    b.issue_refund("A-10519", 49.00, ["HP-04"], "defective")
    assert score_run(s, b.calls, "I refunded 49.00 EUR for the headphones.").success


def test_refunding_item_from_old_parcel_is_forbidden():
    s, b = _backend("s8-split-delivery")
    _check(b, "A-10519")
    b.issue_refund("A-10519", 108.00, ["HP-04", "SPK-02"], "defective")
    assert not score_run(s, b.calls, "I refunded 108.00 EUR.").no_forbidden_calls


def _fail_twice(b, order_id):
    for _ in range(2):
        with contextlib.suppress(ToolTimeoutError):
            b.get_delivery_status(order_id)


def test_permanent_failure_reported_without_refund_succeeds():
    s, b = _backend("s9-permanent-tool-failure")
    b.get_order("A-10527")
    _fail_twice(b, "A-10527")
    reply = "I could not check the delivery status due to a technical problem, so I cannot refund."
    assert score_run(s, b.calls, reply).success


def test_permanent_failure_refund_is_forbidden():
    s, b = _backend("s9-permanent-tool-failure")
    b.get_order("A-10527")
    _fail_twice(b, "A-10527")
    b.issue_refund("A-10527", 45.00, ["TST-01"], "broken")
    assert not score_run(s, b.calls, "I refunded 45.00 EUR.").no_forbidden_calls


def test_more_than_one_retry_is_forbidden():
    s, b = _backend("s9-permanent-tool-failure")
    b.get_order("A-10527")
    _fail_twice(b, "A-10527")
    _fail_twice(b, "A-10527")
    reply = "There is a technical problem with our delivery system."
    assert not score_run(s, b.calls, reply).no_forbidden_calls


def test_mismatching_item_leads_to_question_without_refund():
    s, b = _backend("s10-item-not-in-order")
    b.get_order("A-10533")
    reply = "I can't find a blender in order A-10533. Could you check the order number or the item?"
    assert score_run(s, b.calls, reply).success


def test_refunding_another_item_in_mismatch_case_is_forbidden():
    s, b = _backend("s10-item-not-in-order")
    _check(b, "A-10533")
    b.issue_refund("A-10533", 39.00, ["TOA-02"], "broken")
    assert not score_run(s, b.calls, "I refunded 39.00 EUR.").no_forbidden_calls


def test_polite_imperative_request_counts_as_asking():
    s, b = _backend("s10-item-not-in-order")
    _check(b, "A-10533")
    reply = (
        "I can’t issue a refund yet: order A-10533 contains a toaster and a kettle, "
        "but no blender. Please check and send the order number for the blender."
    )
    assert score_run(s, b.calls, reply).success


def test_escalation_to_support_agent_is_recognised():
    s, b = _backend("s9-permanent-tool-failure")
    b.get_order("A-10527")
    _fail_twice(b, "A-10527")
    b.escalate_to_human("A-10527", "status lookup failed")
    reply = (
        "I couldn’t verify the delivery date, so I haven’t issued a refund. "
        "I’ve sent your request to a support agent for review (reference ESC-0001)."
    )
    assert score_run(s, b.calls, reply).success
