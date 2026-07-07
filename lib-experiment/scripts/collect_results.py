#!/usr/bin/env python3
"""Aggregate per-run results into summary.json and print a comparison vs official.

Reads results/runs/<task>/<cond>/result.json (the benchflow rollout result) for each
task and condition, computes the library-ization delta (library - no-skill) per task
and in aggregate, counts negative-gain tasks, sums token/cost, and positions the
library-ized mean against the official DeepSeek V4 Pro leaderboard number.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
RUNS = EXP / "results" / "runs"
SUBSET = EXP / "data" / "subset_10.json"
BASELINE = EXP / "data" / "official_baseline.json"
OUT = EXP / "results" / "summary.json"

CONDS = ["no-skill", "library"]


def read_run(task: str, cond: str) -> dict | None:
    f = RUNS / task / cond / "result.json"
    if not f.is_file():
        return None
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None
    rewards = d.get("rewards")
    reward = rewards.get("reward") if isinstance(rewards, dict) else None
    fm = d.get("final_metrics") or {}
    return {
        "reward": reward,
        "error": d.get("error"),
        "error_category": d.get("error_category"),
        "n_tool_calls": d.get("n_tool_calls"),
        "n_skill_invocations": d.get("n_skill_invocations"),
        "cost_usd": fm.get("total_cost_usd"),
        "prompt_tokens": fm.get("total_prompt_tokens"),
        "completion_tokens": fm.get("total_completion_tokens"),
    }


def main() -> int:
    subset = json.loads(SUBSET.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.is_file() else {}

    per_task = []
    for t in subset:
        task = t["task"]
        row = {"task": task, "category": t.get("category"),
               "n_native_skills": t.get("n_native_skills")}
        for cond in CONDS:
            r = read_run(task, cond)
            row[cond] = r
        ns = (row.get("no-skill") or {}).get("reward")
        lib = (row.get("library") or {}).get("reward")
        row["library_delta"] = (lib - ns) if (ns is not None and lib is not None) else None
        per_task.append(row)

    def mean_reward(cond: str):
        vals = [ (r.get(cond) or {}).get("reward") for r in per_task ]
        vals = [v for v in vals if v is not None]
        return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)

    def total_cost():
        c = 0.0
        for r in per_task:
            for cond in CONDS:
                v = (r.get(cond) or {}).get("cost_usd")
                if v:
                    c += v
        return round(c, 4)

    ns_mean, ns_n = mean_reward("no-skill")
    lib_mean, lib_n = mean_reward("library")
    neg = [r["task"] for r in per_task if (r.get("library_delta") or 0) < 0]
    helped = [r["task"] for r in per_task if (r.get("library_delta") or 0) > 0]

    summary = {
        "n_tasks_in_subset": len(subset),
        "conditions": CONDS,
        "our_no_skill_mean": round(ns_mean, 4) if ns_mean is not None else None,
        "our_no_skill_n": ns_n,
        "our_library_mean": round(lib_mean, 4) if lib_mean is not None else None,
        "our_library_n": lib_n,
        "our_library_minus_noskill_pp": (round((lib_mean - ns_mean) * 100, 1)
                                         if (ns_mean is not None and lib_mean is not None) else None),
        "negative_gain_tasks": neg,
        "helped_tasks": helped,
        "total_cost_usd": total_cost(),
        "official_deepseek_v4_pro": {
            "no_skill_pass_rate": baseline.get("no_skill_pass_rate"),
            "with_skill_pass_rate": baseline.get("with_skill_pass_rate"),
            "skill_gain_pp": baseline.get("skill_gain_pp"),
            "harness": baseline.get("harness"),
            "source_url": baseline.get("source_url"),
            "protocol": "task-native skills (oracle)",
        },
        "per_task": per_task,
    }
    # library-ized vs official (percentage points), if comparable
    off_ws = baseline.get("with_skill_pass_rate")
    off_ns = baseline.get("no_skill_pass_rate")
    if lib_mean is not None and off_ws is not None:
        summary["library_vs_official_withskill_pp"] = round(lib_mean * 100 - off_ws, 1)
    if ns_mean is not None and off_ns is not None:
        summary["our_noskill_vs_official_noskill_pp"] = round(ns_mean * 100 - off_ns, 1)

    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"tasks with data: no-skill={ns_n}, library={lib_n}")
    print(f"our no-skill mean : {summary['our_no_skill_mean']}")
    print(f"our library mean  : {summary['our_library_mean']}")
    print(f"library - no-skill: {summary['our_library_minus_noskill_pp']} pp")
    print(f"official DS V4 Pro : no-skill {off_ns}% -> with-skill {off_ws}%")
    print(f"negative-gain tasks: {neg}")
    print(f"total cost (USD)   : {summary['total_cost_usd']}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
