#!/usr/bin/env python3
"""Merge every task's skills into ONE unified library (the "库化" layer).

Native SkillsBench keeps skills task-local: tasks/<t>/environment/skills/<skill>/.
This script copies them all into a single flat pool so an agent can be shown the
full set of skill metadata and self-select — simulating real library deployment.

Outputs:
  data/library/<skill-name>/           merged skill folders (deduped by name)
  data/library_index.json              [{name, description, source_tasks, n_chars, conflict}]
  data/library_stats.json              summary counts + near-duplicate candidates
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent                                   # lib-experiment/
UPSTREAM = EXP.parents[1] / "skillsbench-upstream"  # sibling of skillsbench-/
TASKS = UPSTREAM / "tasks"
LIB = EXP / "data" / "library"
INDEX = EXP / "data" / "library_index.json"
STATS = EXP / "data" / "library_stats.json"

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict:
    """Extract name/description from SKILL.md YAML frontmatter (no pyyaml dep)."""
    m = FM_RE.match(text)
    block = m.group(1) if m else text[:1500]
    out = {"name": "", "description": ""}
    for key in ("name", "description"):
        km = re.search(rf"^{key}:\s*(.+?)\s*$", block, re.MULTILINE)
        if km:
            val = km.group(1).strip().strip("'\"")
            out[key] = val
    return out


def main() -> int:
    if not TASKS.is_dir():
        raise SystemExit(f"upstream tasks not found: {TASKS}")

    if LIB.exists():
        shutil.rmtree(LIB)
    LIB.mkdir(parents=True, exist_ok=True)

    skill_mds = sorted(TASKS.glob("*/environment/skills/*/SKILL.md"))
    by_name: dict[str, dict] = {}
    conflicts: list[dict] = []

    for md in skill_mds:
        skill_dir = md.parent
        task = md.parents[2].name  # tasks/<task>/environment/skills/<skill>/SKILL.md
        text = md.read_text(encoding="utf-8", errors="replace")
        meta = parse_frontmatter(text)
        name = meta["name"] or skill_dir.name
        digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]

        if name not in by_name:
            by_name[name] = {
                "name": name,
                "description": meta["description"],
                "dir_name": skill_dir.name,
                "source_tasks": [task],
                "digest": digest,
                "n_chars": len(text),
                "conflict": False,
            }
            shutil.copytree(skill_dir, LIB / name, dirs_exist_ok=True)
        else:
            rec = by_name[name]
            rec["source_tasks"].append(task)
            if digest != rec["digest"]:
                # same skill name, different body across tasks — a real conflict
                rec["conflict"] = True
                conflicts.append({
                    "name": name,
                    "task_a": rec["source_tasks"][0],
                    "task_b": task,
                    "digest_a": rec["digest"],
                    "digest_b": digest,
                })

    index = sorted(by_name.values(), key=lambda r: r["name"])
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    # crude near-duplicate candidate detection: shared significant tokens in description
    stop = set("a an the and or to of for with use when working data using this that "
               "in on is are be by from into skill tools techniques".split())

    def toks(s: str) -> set[str]:
        return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 3 and w not in stop}

    names = [r["name"] for r in index]
    descs = [toks(r["description"]) for r in index]
    near_dupes = []
    for i in range(len(index)):
        for j in range(i + 1, len(index)):
            a, b = descs[i], descs[j]
            if not a or not b:
                continue
            jac = len(a & b) / len(a | b)
            if jac >= 0.45:
                near_dupes.append({"a": names[i], "b": names[j], "jaccard": round(jac, 3)})
    near_dupes.sort(key=lambda d: -d["jaccard"])

    stats = {
        "n_skill_md_found": len(skill_mds),
        "n_unique_skills": len(by_name),
        "n_name_collisions_with_diff_body": len(conflicts),
        "collisions": conflicts,
        "n_near_duplicate_candidates": len(near_dupes),
        "near_duplicate_candidates_top": near_dupes[:40],
        "library_dir": str(LIB),
    }
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"SKILL.md found      : {len(skill_mds)}")
    print(f"unique skills       : {len(by_name)}")
    print(f"name collisions     : {len(conflicts)} (same name, different body)")
    print(f"near-dup candidates : {len(near_dupes)} (desc jaccard >= 0.45)")
    print(f"library written to  : {LIB}")
    print(f"index               : {INDEX}")
    if near_dupes[:8]:
        print("top near-duplicate pairs:")
        for d in near_dupes[:8]:
            print(f"  {d['jaccard']:.2f}  {d['a']}  <>  {d['b']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
