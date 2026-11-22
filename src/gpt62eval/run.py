"""Runs every scenario n times per model and appends one JSON line per run.

Usage: uv run python -m gpt62eval.run --models gpt-6.2-sol --runs 1 --out results/probe.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from gpt62eval.agent import run_once
from gpt62eval.evaluate import score_run
from gpt62eval.pricing import PRICES, cost_usd
from gpt62eval.scenarios import SCENARIOS


async def main(models: list[str], scenario_ids: list[str], runs: int, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    log_dir = out.parent / "toollogs"
    # Order: run number outermost, so a rate limit or outage hits all models alike.
    for n in range(1, runs + 1):
        for scenario_id in scenario_ids:
            for model in models:
                scenario = SCENARIOS[scenario_id]
                log_path = log_dir / f"{model}__{scenario_id}__{n}.jsonl"
                record: dict[str, object] = {
                    "model": model,
                    "scenario": scenario_id,
                    "run": n,
                    "at": datetime.now(UTC).isoformat(),
                }
                try:
                    r = await run_once(model, scenario, log_path)
                    score = score_run(scenario, r.calls, r.reply)
                    record |= {
                        "goal_reached": score.goal_reached,
                        "no_forbidden_calls": score.no_forbidden_calls,
                        "clean_reply": score.clean_reply,
                        "success": score.success,
                        "notes": list(score.notes),
                        "steps": len(r.calls),
                        "model_tool_calls": r.model_tool_calls,
                        "input_tokens": r.input_tokens,
                        "cached_tokens": r.cached_tokens,
                        "cache_write_tokens": r.cache_write_tokens,
                        "output_tokens": r.output_tokens,
                        "reasoning_tokens": r.reasoning_tokens,
                        "duration_s": round(r.duration_s, 2),
                        "cost_usd": cost_usd(
                            model,
                            r.input_tokens,
                            r.cached_tokens,
                            r.output_tokens,
                            r.cache_write_tokens,
                        ),
                        "reply": r.reply,
                        "calls": [asdict(c) for c in r.calls],
                    }
                except Exception as exc:  # noqa: BLE001 a failed run is recorded, not fatal
                    record |= {"error": f"{type(exc).__name__}: {exc}", "success": False}
                with out.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
                status = "ERROR" if "error" in record else ("ok" if record["success"] else "fail")
                print(f"{n} {scenario_id:<28} {model:<14} {status}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=list(PRICES))
    parser.add_argument("--scenarios", nargs="+", default=list(SCENARIOS))
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path("results/runs.jsonl"))
    a = parser.parse_args()
    asyncio.run(main(a.models, a.scenarios, a.runs, a.out))
