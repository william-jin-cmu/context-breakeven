#!/usr/bin/env python3
"""Summarize harbor jobs produced by run_pilot.sh: per-task pass/fail and token
accounting for each profile, side by side.

Usage: scripts/analyze.py jobs/<job-a> [jobs/<job-b> ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load_trials(job_dir: Path) -> dict[str, dict]:
    trials: dict[str, dict] = {}
    for result_path in sorted(job_dir.rglob("result.json")):
        try:
            result = json.loads(result_path.read_text())
        except json.JSONDecodeError:
            continue
        if "task_name" not in result:
            continue
        task = result["task_name"].split("/")[-1]
        verifier = result.get("verifier_result") or {}
        rewards = verifier.get("rewards") or {}
        reward = None
        if isinstance(rewards, dict) and rewards:
            reward = float(next(iter(rewards.values())))
        agent = result.get("agent_result") or {}
        meta = agent.get("metadata") or {}
        exc = result.get("exception_info") or {}
        trials[task] = {
            "reward": reward,
            "exception": exc.get("exception_type"),
            "steps": meta.get("steps"),
            "uncached": meta.get("uncached_input_tokens"),
            "cached": meta.get("cache_read_tokens"),
            "output": meta.get("output_tokens"),
            "max_prompt": meta.get("max_prompt_tokens"),
            "cost": agent.get("cost_usd"),
            "tool_calls": meta.get("tool_calls") or {},
            "replacements": meta.get("state_replacements"),
            "profile": meta.get("profile"),
            "seconds": _duration(result.get("agent_execution")),
        }
    return trials


def _duration(timing: dict | None) -> float | None:
    if not timing or not timing.get("started_at") or not timing.get("finished_at"):
        return None
    from datetime import datetime

    start = datetime.fromisoformat(timing["started_at"])
    end = datetime.fromisoformat(timing["finished_at"])
    return (end - start).total_seconds()


def fmt(value, width: int = 8) -> str:
    if value is None:
        return "-".rjust(width)
    if isinstance(value, float):
        return f"{value:.2f}".rjust(width)
    return str(value).rjust(width)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    jobs = {Path(p).name: load_trials(Path(p)) for p in argv[1:]}
    tasks = sorted({t for trials in jobs.values() for t in trials})
    for job_name, trials in jobs.items():
        profile = next((t["profile"] for t in trials.values() if t.get("profile")), "?")
        print(f"\n== {job_name} (profile {profile}) ==")
        print(f"{'task':32} {'pass':>5} {'steps':>6} {'uncached':>9} {'cached':>9} {'hit%':>5} {'output':>8} {'maxPrompt':>9} {'cost$':>6} {'sec':>6} {'upd':>4} {'srch':>4} {'repl':>4}")
        agg = {"pass": 0, "n": 0, "uncached": 0, "cached": 0, "output": 0, "cost": 0.0}
        for task in tasks:
            t = trials.get(task)
            if t is None:
                continue
            total_in = (t["uncached"] or 0) + (t["cached"] or 0)
            hit = (100.0 * (t["cached"] or 0) / total_in) if total_in else None
            passed = None if t["reward"] is None else (t["reward"] >= 1.0)
            agg["n"] += 1
            agg["pass"] += 1 if passed else 0
            agg["uncached"] += t["uncached"] or 0
            agg["cached"] += t["cached"] or 0
            agg["output"] += t["output"] or 0
            agg["cost"] += t["cost"] or 0.0
            calls = t["tool_calls"]
            print(
                f"{task:32} {fmt('Y' if passed else ('N' if passed is False else 'ERR' if t['exception'] else '?'),5)} {fmt(t['steps'],6)} "
                f"{fmt(t['uncached'],9)} {fmt(t['cached'],9)} {fmt(None if hit is None else round(hit),5)} {fmt(t['output'],8)} "
                f"{fmt(t['max_prompt'],9)} {fmt(t['cost'],6)} {fmt(None if t['seconds'] is None else round(t['seconds']),6)} "
                f"{fmt(calls.get('update_state'),4)} {fmt(calls.get('search_history'),4)} {fmt(t['replacements'],4)}"
            )
        total_in = agg["uncached"] + agg["cached"]
        hit = (100.0 * agg["cached"] / total_in) if total_in else 0.0
        print(
            f"{'TOTAL':32} {agg['pass']}/{agg['n']} uncached={agg['uncached']:,} cached={agg['cached']:,} hit={hit:.0f}% "
            f"output={agg['output']:,} cost=${agg['cost']:.2f}"
        )
    if len(jobs) == 2:
        (name_a, a), (name_b, b) = jobs.items()
        print(f"\n== per-task delta ({name_b} vs {name_a}) ==")
        for task in tasks:
            if task in a and task in b:
                ta, tb = a[task], b[task]
                ia = (ta["uncached"] or 0) + (ta["cached"] or 0)
                ib = (tb["uncached"] or 0) + (tb["cached"] or 0)
                ratio = (ib / ia) if ia else None
                pa = ta["reward"]
                pb = tb["reward"]
                print(f"{task:32} pass {fmt(pa,4)} -> {fmt(pb,4)}  prompt tokens x{fmt(ratio,5)}  cost {fmt(ta['cost'],6)} -> {fmt(tb['cost'],6)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
