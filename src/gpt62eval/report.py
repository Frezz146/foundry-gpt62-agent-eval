"""Builds the Markdown result tables from a runs JSONL file.

Usage: uv run python -m gpt62eval.report results/full.jsonl
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from gpt62eval.backend import ToolCall
from gpt62eval.evaluate import score_run
from gpt62eval.pricing import PRICES
from gpt62eval.scenarios import SCENARIOS


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def rescore(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Scores stored runs again so that fixes to the reply checks apply to old results."""
    rescored = []
    for r in runs:
        if "error" in r:
            rescored.append(r)
            continue
        score = score_run(SCENARIOS[r["scenario"]], [ToolCall(**c) for c in r["calls"]], r["reply"])
        rescored.append(
            r
            | {
                "goal_reached": score.goal_reached,
                "no_forbidden_calls": score.no_forbidden_calls,
                "clean_reply": score.clean_reply,
                "success": score.success,
                "notes": list(score.notes),
            }
        )
    return rescored


def model_summary(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in runs:
        by_model[r["model"]].append(r)
    rows = []
    for model in [m for m in PRICES if m in by_model]:
        rs = by_model[model]
        ok = [r for r in rs if "error" not in r]
        successes = sum(1 for r in rs if r.get("success"))
        cost = sum(r.get("cost_usd", 0.0) for r in ok)
        rows.append(
            {
                "model": model,
                "runs": len(rs),
                "errors": len(rs) - len(ok),
                "successes": successes,
                "goal": sum(1 for r in ok if r["goal_reached"]),
                "no_forbidden": sum(1 for r in ok if r["no_forbidden_calls"]),
                "clean": sum(1 for r in ok if r["clean_reply"]),
                "steps": mean(r["steps"] for r in ok) if ok else 0.0,
                "input_tokens": mean(r["input_tokens"] for r in ok) if ok else 0.0,
                "output_tokens": mean(r["output_tokens"] for r in ok) if ok else 0.0,
                "duration_s": mean(r["duration_s"] for r in ok) if ok else 0.0,
                "cost_usd": cost,
                "cost_per_success_usd": cost / successes if successes else None,
            }
        )
    return rows


def scenario_matrix(runs: list[dict[str, Any]]) -> dict[str, dict[str, tuple[int, int]]]:
    matrix: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in runs:
        cell = matrix[r["scenario"]][r["model"]]
        cell[0] += 1 if r.get("success") else 0
        cell[1] += 1
    return {s: {m: (c[0], c[1]) for m, c in row.items()} for s, row in matrix.items()}


def to_markdown(runs: list[dict[str, Any]]) -> str:
    out = [
        "| Model | Success | Goal | No forbidden call | Clean reply | Avg steps "
        "| Avg input tokens | Avg output tokens | Avg duration (s) | Total cost (USD) "
        "| Cost per success (USD) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in model_summary(runs):
        n = row["runs"]
        cps = row["cost_per_success_usd"]
        out.append(
            f"| {row['model']} | {row['successes']}/{n} | {row['goal']}/{n} "
            f"| {row['no_forbidden']}/{n} | {row['clean']}/{n} | {row['steps']:.1f} "
            f"| {row['input_tokens']:.0f} | {row['output_tokens']:.0f} "
            f"| {row['duration_s']:.1f} | {row['cost_usd']:.4f} "
            f"| {'n/a' if cps is None else f'{cps:.5f}'} |"
        )
    models = [m for m in PRICES if any(r["model"] == m for r in runs)]
    matrix = scenario_matrix(runs)
    out += ["", "| Scenario | " + " | ".join(models) + " |", "|---" * (len(models) + 1) + "|"]
    for sid in [s for s in SCENARIOS if s in matrix]:
        cells = ["{}/{}".format(*matrix[sid][m]) if m in matrix[sid] else "n/a" for m in models]
        out.append(f"| {sid} | " + " | ".join(cells) + " |")
    failures = [r for r in runs if not r.get("success")]
    if failures:
        out += ["", "Failed runs:"]
        for r in failures:
            reason = r.get("error") or "; ".join(r.get("notes", []))
            out.append(f"- {r['model']} {r['scenario']} run {r['run']}: {reason}")
    return "\n".join(out)


if __name__ == "__main__":
    print(to_markdown(rescore(load(Path(sys.argv[1])))))
