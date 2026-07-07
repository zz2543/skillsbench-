#!/usr/bin/env python3
"""Drive SkillsBench eval through the OpenHands harness on DeepSeek V4 Pro.

For each task x condition we invoke the OFFICIAL benchflow runner (same harness the
leaderboard uses), so results are comparable to the official DeepSeek Pro numbers.

Conditions:
  no-skill : --skill-mode no-skill                          (floor)
  library  : --skill-mode with-skill --skills-dir <library>  (全量库化, agent self-selects)

Reads the DeepSeek key from the gitignored ../DeepSeek-api and injects it only into
the subprocess env (never written to disk in the repo). Results are sanitized and
copied under results/runs/<task>/<cond>/. Resumable: a task/cond with a recorded
reward is skipped.

Usage:
  python run_eval.py                          # all subset_10 tasks, both conditions
  python run_eval.py --tasks a,b --conditions library --limit 2
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
REPO = EXP.parent                       # skillsbench-/
UPSTREAM = REPO.parent / "skillsbench-upstream"
LIBRARY = EXP / "data" / "library"
SUBSET = EXP / "data" / "subset_10.json"
RUNS = EXP / "results" / "runs"
RUNLOG = EXP / "results" / "run_log.jsonl"
KEY_FILE = REPO / "DeepSeek-api"

sys.path.insert(0, str(HERE))
from sanitize import scrub  # noqa: E402

CONDITIONS = {
    "no-skill": ["--skill-mode", "no-skill"],
    "library": ["--skill-mode", "with-skill", "--skills-dir", str(LIBRARY)],
}


def deepseek_key() -> str:
    first = KEY_FILE.read_text(encoding="utf-8").splitlines()[0]
    return first.split(":", 1)[1].strip() if ":" in first else first.strip()


def load_tasks(arg_tasks: str | None) -> list[str]:
    if arg_tasks:
        return [t.strip() for t in arg_tasks.split(",") if t.strip()]
    data = json.loads(SUBSET.read_text(encoding="utf-8"))
    return [t["task"] for t in data]


def already_done(task: str, cond: str) -> bool:
    r = RUNS / task / cond / "result.json"
    if not r.is_file():
        return False
    try:
        d = json.loads(r.read_text(encoding="utf-8"))
        return d.get("rewards", {}).get("reward") is not None
    except Exception:
        return False


def collect(job_dir: Path, dest: Path) -> dict:
    """Copy result.json / reward.txt / sanitized trajectory into dest; return summary."""
    dest.mkdir(parents=True, exist_ok=True)
    out = {"reward": None, "n_tool_calls": None, "n_skill_invocations": None,
           "skills_used": None, "usage": None}
    result_files = list(job_dir.rglob("result.json"))
    if result_files:
        rj = json.loads(result_files[0].read_text(encoding="utf-8"))
        (dest / "result.json").write_text(json.dumps(rj, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
        out["reward"] = rj.get("rewards", {}).get("reward")
        out["n_tool_calls"] = rj.get("n_tool_calls")
        out["n_skill_invocations"] = rj.get("n_skill_invocations")
        out["usage"] = rj.get("usage") or rj.get("agent_result", {}).get("usage")
    # sanitized trajectory (may embed auth headers)
    for tj in job_dir.rglob("acp_trajectory.jsonl"):
        raw = tj.read_text(encoding="utf-8", errors="replace")
        (dest / "trajectory.sanitized.jsonl").write_text(scrub(raw), encoding="utf-8")
        break
    # skills used, if the harness recorded any
    skdir = None
    for p in job_dir.rglob("agent/skills"):
        skdir = p
        break
    if skdir and skdir.is_dir():
        out["skills_used"] = sorted(x.name for x in skdir.iterdir() if x.is_dir())
    # copy the run-level summary too
    for sm in job_dir.glob("*/summary.json"):
        (dest / "summary.json").write_text(scrub(sm.read_text(encoding="utf-8")),
                                           encoding="utf-8")
        break
    return out


def run_one(task: str, cond: str, model: str, env: dict, timeout: int) -> dict:
    job_dir = EXP / "results" / "_jobs" / f"{task}__{cond}"
    if job_dir.exists():
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "uv", "run", "bench", "eval", "run",
        "--tasks-dir", f"tasks/{task}",
        "--agent", "openhands",
        "--model", model,
        "--sandbox", "docker",
        "--usage-tracking", "required",
        "--jobs-dir", str(job_dir),
        *CONDITIONS[cond],
    ]
    t0 = time.time()
    log = {"task": task, "cond": cond, "model": model,
           "ts": datetime.now(timezone.utc).isoformat(), "cmd": " ".join(cmd)}
    try:
        p = subprocess.run(cmd, cwd=str(UPSTREAM), env=env, timeout=timeout,
                           capture_output=True, text=True)
        stdout_tail = scrub("\n".join(p.stdout.splitlines()[-25:]))
        log["returncode"] = p.returncode
        log["stdout_tail"] = stdout_tail
    except subprocess.TimeoutExpired:
        log["returncode"] = -1
        log["error"] = f"timeout after {timeout}s"
    log["elapsed_sec"] = round(time.time() - t0, 1)
    summ = collect(job_dir, RUNS / task / cond)
    log.update(summ)
    with RUNLOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log, ensure_ascii=False) + "\n")
    return log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=None, help="comma list; default = subset_10.json")
    ap.add_argument("--conditions", default="no-skill,library")
    ap.add_argument("--model", default="deepseek-v4-pro")
    ap.add_argument("--timeout", type=int, default=2700, help="per-run seconds")
    ap.add_argument("--limit", type=int, default=0, help="max tasks (0 = all)")
    ap.add_argument("--force", action="store_true", help="re-run even if done")
    args = ap.parse_args()

    if not LIBRARY.is_dir():
        raise SystemExit(f"library not built: {LIBRARY} (run build_library.py first)")

    tasks = load_tasks(args.tasks)
    if args.limit:
        tasks = tasks[: args.limit]
    conds = [c.strip() for c in args.conditions.split(",") if c.strip()]

    env = dict(os.environ)
    env["DEEPSEEK_API_KEY"] = deepseek_key()
    env.setdefault("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

    RUNS.mkdir(parents=True, exist_ok=True)
    print(f"tasks={len(tasks)} conditions={conds} model={args.model}")
    for i, task in enumerate(tasks, 1):
        for cond in conds:
            if not args.force and already_done(task, cond):
                print(f"[{i}/{len(tasks)}] {task}/{cond}: SKIP (done)")
                continue
            print(f"[{i}/{len(tasks)}] {task}/{cond}: running ...", flush=True)
            log = run_one(task, cond, args.model, env, args.timeout)
            print(f"    reward={log.get('reward')} elapsed={log.get('elapsed_sec')}s "
                  f"rc={log.get('returncode')} tools={log.get('n_tool_calls')} "
                  f"skill_inv={log.get('n_skill_invocations')}")
    print("done. per-run outputs under results/runs/, log at results/run_log.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
