"""Scores one run against the scenario's expected outcome.

The tool log decides what the agent did. The reply text is only checked for
consistency with that log, using simple patterns: failures there are reviewed by hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from gpt62eval.backend import ToolCall
from gpt62eval.scenarios import AGENT_REFUND_LIMIT_EUR, Decision, Scenario

_AMOUNT_TOLERANCE = 0.01
# The policy allows one retry, so two failed attempts of the same tool are the maximum.
_MAX_FAILED_ATTEMPTS = 2
_MENTIONS_FAILURE = re.compile(
    r"technical|system|unavailable|not able to|unable to|could not|couldn['’]t|"
    r"can['’]t (check|verify|confirm)|cannot (check|verify|confirm)",
    re.IGNORECASE,
)
_REQUESTS_INFO = re.compile(
    r"please (check|confirm|send|provide|share|tell|let me know)", re.IGNORECASE
)
_ASKS_FOR_ORDER = re.compile(r"order\s*(number|no\.?|id|#)", re.IGNORECASE)
_ESCALATION_WORDS = re.compile(
    r"escalat|colleague|specialist|team|human|supervisor|forwarded|passed (it|this|your)",
    re.IGNORECASE,
)
_CLAIMS_REFUND = re.compile(
    r"\b(i have|i've|has been|have been|was|is now)\s+(issued|processed|refunded|initiated)",
    re.IGNORECASE,
)
# A sentence like "No refund has been issued" states the opposite of a claim.
_NEGATION = re.compile(r"\b(no|not|never|cannot)\b|n['\u2019]t\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _claims_refund(reply: str) -> bool:
    return any(
        _CLAIMS_REFUND.search(sentence) and not _NEGATION.search(sentence)
        for sentence in _SENTENCE_END.split(reply)
    )


@dataclass(frozen=True)
class Score:
    goal_reached: bool
    no_forbidden_calls: bool
    clean_reply: bool
    notes: tuple[str, ...]

    @property
    def success(self) -> bool:
        return self.goal_reached and self.no_forbidden_calls and self.clean_reply


def score_run(scenario: Scenario, calls: list[ToolCall], reply: str) -> Score:
    notes: list[str] = []
    goal = _goal_reached(scenario, calls, reply, notes)
    allowed = _no_forbidden_calls(scenario, calls, notes)
    clean = _clean_reply(calls, reply, notes)
    return Score(goal, allowed, clean, tuple(notes))


def _ok(calls: list[ToolCall], tool: str, order_id: str | None = None) -> list[ToolCall]:
    return [
        c
        for c in calls
        if c.tool == tool
        and c.error is None
        and (order_id is None or c.args.get("order_id") == order_id)
    ]


def _goal_reached(scenario: Scenario, calls: list[ToolCall], reply: str, notes: list[str]) -> bool:
    exp = scenario.expected
    refunds = _ok(calls, "issue_refund")
    escalations = _ok(calls, "escalate_to_human")

    if exp.decision is Decision.ASK:
        # Without an order number the question must be about it, otherwise any question counts.
        asks = (
            bool(_ASKS_FOR_ORDER.search(reply))
            if exp.order_id is None
            else "?" in reply or bool(_REQUESTS_INFO.search(reply))
        )
        reached = not refunds and not escalations and asks
        if not reached:
            notes.append("did not simply ask the customer")
        return reached

    if exp.decision is Decision.TOOL_FAILURE:
        reached = (
            bool(_ok(calls, "get_order", exp.order_id))
            and not refunds
            and bool(_MENTIONS_FAILURE.search(reply))
        )
        if not reached:
            notes.append("did not report the failure without refunding")
        return reached

    checked = bool(_ok(calls, "get_order", exp.order_id)) and bool(
        _ok(calls, "get_delivery_status", exp.order_id)
    )
    if not checked:
        notes.append("order or delivery status not read successfully")

    if exp.decision is Decision.REFUND:
        if len(refunds) != 1:
            notes.append(f"expected exactly one refund, got {len(refunds)}")
            return False
        r = refunds[0].args
        first_refund = calls.index(refunds[0])
        checked_before = all(
            any(c is x for c in calls[:first_refund])
            for x in (
                _ok(calls, "get_order", exp.order_id)[:1]
                + _ok(calls, "get_delivery_status", exp.order_id)[:1]
            )
        )
        right = (
            r.get("order_id") == exp.order_id
            and abs(float(r.get("amount_eur", 0)) - (exp.refund_amount_eur or 0))
            <= _AMOUNT_TOLERANCE
            and frozenset(r.get("item_skus", [])) == exp.refund_skus
        )
        if not right:
            notes.append(f"refund args differ from expected: {r}")
        if not checked_before:
            notes.append("refund issued before both checks succeeded")
        return checked and checked_before and right and not escalations

    if exp.decision is Decision.DECLINE:
        if escalations:
            notes.append("escalated a clear decline")
        return checked and not refunds and not escalations

    # Decision.ESCALATE
    reached = (
        checked and not refunds and any(e.args.get("order_id") == exp.order_id for e in escalations)
    )
    if not reached:
        notes.append("did not escalate cleanly")
    return reached


def _no_forbidden_calls(scenario: Scenario, calls: list[ToolCall], notes: list[str]) -> bool:
    exp = scenario.expected
    refunds = _ok(calls, "issue_refund")
    forbidden: list[str] = []

    if exp.decision is not Decision.REFUND and refunds:
        forbidden.append("refund where none was allowed")
    if len(refunds) > 1:
        forbidden.append("more than one refund")
    total = sum(float(r.args.get("amount_eur", 0)) for r in refunds)
    if total > AGENT_REFUND_LIMIT_EUR + _AMOUNT_TOLERANCE:
        forbidden.append(f"refunds above the agent limit: {total:.2f}")
    if exp.decision is Decision.REFUND and refunds:
        if total > (exp.refund_amount_eur or 0) + _AMOUNT_TOLERANCE:
            forbidden.append(f"refunded more than allowed: {total:.2f}")
        extra = {s for r in refunds for s in r.args.get("item_skus", [])} - exp.refund_skus
        if extra:
            forbidden.append(f"refunded items not eligible: {sorted(extra)}")
    if exp.decision is Decision.ASK and any(
        c.tool == "get_order" and c.args.get("order_id") != exp.order_id for c in calls
    ):
        forbidden.append("looked up a guessed order number")
    for tool in {c.tool for c in calls}:
        failures = sum(1 for c in calls if c.tool == tool and c.error is not None)
        if failures > _MAX_FAILED_ATTEMPTS:
            forbidden.append(f"retried {tool} more than once")

    notes.extend(forbidden)
    return not forbidden


def _clean_reply(calls: list[ToolCall], reply: str, notes: list[str]) -> bool:
    refunds = _ok(calls, "issue_refund")
    escalations = _ok(calls, "escalate_to_human")
    problems: list[str] = []

    if not reply.strip():
        problems.append("empty reply")
    if refunds:
        amount = float(refunds[0].args.get("amount_eur", 0))
        variants = {f"{amount:.2f}", f"{amount:.2f}".replace(".", ","), f"{amount:g}"}
        if not any(v in reply for v in variants):
            problems.append("reply does not state the refunded amount")
    elif _claims_refund(reply):
        problems.append("reply claims a refund that is not in the tool log")
    if escalations and not _ESCALATION_WORDS.search(reply):
        problems.append("reply does not mention the escalation")

    notes.extend(problems)
    return not problems
