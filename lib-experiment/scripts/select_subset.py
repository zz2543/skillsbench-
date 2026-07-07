#!/usr/bin/env python3
"""Pick a 10-task subset, stratified across categories, favouring multi-skill tasks.

Reads each upstream task's task.md frontmatter (metadata.category / difficulty) and
counts its native skills. Prefers tasks with >=2 skills (composition is where library
interference can show up) and spreads picks across the 8 SkillsBench categories.

Output: data/subset_10.json  [{task, category, difficulty, n_native_skills, native_skills}]
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
UPSTREAM = EXP.parents[1] / "skillsbench-upstream"
TASKS = UPSTREAM / "tasks"
OUT = EXP / "data" / "subset_10.json"

N_TARGET = 10
# deterministic tie-breaking
SEED_ORDER = "abcdefghijklmnopqrstuvwxyz"


def read_meta(task_dir: Path) -> dict:
    md = task_dir / "task.md"
    cat, diff = "unknown", "unknown"
    if md.is_file():
        text = md.read_text(encoding="utf-8", errors="replace")
        fm = text.split("---", 2)
        block = fm[1] if len(fm) >= 3 else text[:1500]
        cm = re.search(r"^\s*category:\s*(.+?)\s*$", block, re.MULTILINE)
        dm = re.search(r"^\s*difficulty:\s*(.+?)\s*$", block, re.MULTILINE)
        if cm:
            cat = cm.group(1).strip().strip("'\"")
        if dm:
            diff = dm.group(1).strip().strip("'\"")
    skills_dir = task_dir / "environment" / "skills"
    skills = sorted(p.name for p in skills_dir.iterdir()) if skills_dir.is_dir() else []
    return {"category": cat, "difficulty": diff, "native_skills": skills,
            "n_native_skills": len(skills)}


def main() -> int:
    tasks = []
    for td in sorted(TASKS.iterdir()):
        if not td.is_dir() or not (td / "task.md").is_file():
            continue
        m = read_meta(td)
        m["task"] = td.name
        tasks.append(m)

    # candidates: multi-skill preferred
    multi = [t for t in tasks if t["n_native_skills"] >= 2]
    pool = multi if len(multi) >= N_TARGET else tasks

    # group by category, round-robin pick to spread across categories.
    by_cat: dict[str, list] = defaultdict(list)
    for t in sorted(pool, key=lambda x: (-x["n_native_skills"], x["task"])):
        by_cat[t["category"]].append(t)

    picked, seen = [], set()
    cats = sorted(by_cat)
    i = 0
    while len(picked) < N_TARGET and any(by_cat.values()):
        cat = cats[i % len(cats)]
        if by_cat[cat]:
            t = by_cat[cat].pop(0)
            if t["task"] not in seen:
                picked.append(t)
                seen.add(t["task"])
        i += 1
        if i > 10000:
            break

    picked = sorted(picked, key=lambda x: (x["category"], x["task"]))[:N_TARGET]
    OUT.write_text(json.dumps(picked, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"total tasks scanned : {len(tasks)}")
    print(f"multi-skill tasks   : {len(multi)}")
    print(f"selected            : {len(picked)}")
    for t in picked:
        print(f"  [{t['category']:>28}] {t['task']:<34} skills={t['n_native_skills']} ({t['difficulty']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
