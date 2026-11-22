from gpt62eval.report import model_summary, scenario_matrix, to_markdown


def _run(model, scenario, success, cost=0.01, **extra):
    base = {
        "model": model,
        "scenario": scenario,
        "run": 1,
        "success": success,
        "goal_reached": success,
        "no_forbidden_calls": True,
        "clean_reply": success,
        "steps": 3,
        "input_tokens": 1000,
        "output_tokens": 100,
        "duration_s": 5.0,
        "cost_usd": cost,
        "notes": [] if success else ["did not escalate cleanly"],
    }
    return base | extra


def test_cost_per_success_divides_total_cost_by_successes():
    runs = [
        _run("gpt-6.2-sol", "s1-partial-refund", True),
        _run("gpt-6.2-sol", "s2-deadline-contradiction", False),
    ]
    row = model_summary(runs)[0]
    assert row["successes"] == 1
    assert row["cost_per_success_usd"] == 0.02


def test_errored_runs_count_as_failures_and_are_excluded_from_averages():
    runs = [
        _run("gpt-6-astra", "s1-partial-refund", True),
        {
            "model": "gpt-6-astra",
            "scenario": "s1-partial-refund",
            "run": 2,
            "success": False,
            "error": "RateLimitError: 429",
        },
    ]
    row = model_summary(runs)[0]
    assert (row["runs"], row["errors"], row["successes"]) == (2, 1, 1)
    assert row["steps"] == 3


def test_no_success_gives_no_cost_per_success():
    row = model_summary([_run("gpt-6.1-sol", "s5-over-limit", False)])[0]
    assert row["cost_per_success_usd"] is None


def test_matrix_and_markdown_list_failures():
    runs = [_run("gpt-6.2-astra", "s5-over-limit", False)]
    assert scenario_matrix(runs) == {"s5-over-limit": {"gpt-6.2-astra": (0, 1)}}
    md = to_markdown(runs)
    assert "| s5-over-limit | 0/1 |" in md
    assert "gpt-6.2-astra s5-over-limit run 1: did not escalate cleanly" in md


def test_rescore_uses_current_evaluator_on_stored_calls():
    from gpt62eval.report import rescore

    run = {
        "model": "gpt-6.2-sol",
        "scenario": "s3-missing-order-id",
        "run": 1,
        "success": False,
        "calls": [],
        "reply": "Could you send me your order number?",
        "notes": ["old note"],
    }
    r = rescore([run])[0]
    assert r["success"] is True
    assert r["notes"] == []
