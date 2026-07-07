#!/usr/bin/env python3
"""Fetch the official SkillsBench DeepSeek V4 Pro leaderboard score.

The official leaderboard runs the SAME OpenHands harness we use, so its DeepSeek
V4 Pro number (task-native skills = the "with-skill" protocol) is our comparison
baseline. arXiv HTML is network-blocked here, so we try, in order:
  1. skillsbench.ai leaderboard page (embedded __NEXT_DATA__ / JSON)
  2. HuggingFace dataset benchflow/skillsbench (any results file)
  3. arXiv 2602.12670 HTML via curl

Whatever is found is written to data/official_baseline.json with provenance.
If nothing parses automatically, the file is created with source="MANUAL_TODO"
so the value can be filled in by hand (with the URL noted).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data" / "official_baseline.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def curl(url: str, timeout: int = 30) -> str:
    try:
        p = subprocess.run(
            ["curl", "-fsSL", "-A", UA, "-m", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        return p.stdout if p.returncode == 0 else ""
    except Exception:
        return ""


def _flatten(text: str) -> str:
    import html as _html
    return _html.unescape(re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", " ", text)))


def parse_main_row(text: str, model_name: str) -> dict | None:
    """Parse the main results row: '<model> <no-skill> <with-skill> +<gain> ...'."""
    flat = _flatten(text)
    # e.g. "DeepSeek V4 Pro 26.9 50.1 +23.2 31.8 261/261 OpenHands"
    pat = re.compile(
        re.escape(model_name)
        + r"\s+(\d{1,3}\.\d)\s+(\d{1,3}\.\d)\s+\+(\d{1,3}\.\d)\s+[\d.]+\s+(\d+)/(\d+)\s+OpenHands"
    )
    m = pat.search(flat)
    if not m:
        # looser: model + three numbers with a +gain
        m = re.search(re.escape(model_name) + r"\s+(\d{1,3}\.\d)\s+(\d{1,3}\.\d)\s+\+(\d{1,3}\.\d)", flat)
        if not m:
            return None
        return {"no_skill": float(m.group(1)), "with_skill": float(m.group(2)),
                "gain_pp": float(m.group(3))}
    return {"no_skill": float(m.group(1)), "with_skill": float(m.group(2)),
            "gain_pp": float(m.group(3)), "n_runs": int(m.group(4)),
            "n_task_instances": int(m.group(5))}


def find_deepseek_scores(text: str) -> list[dict]:
    """Heuristically pull DeepSeek V4 Pro numbers near the token in JSON/HTML."""
    hits = []
    for m in re.finditer(r"deepseek[\s\-_]*v?4[\s\-_]*pro", text, re.IGNORECASE):
        window = text[m.start(): m.start() + 400]
        nums = re.findall(r"(\d{1,3}(?:\.\d+)?)\s*%|\"[a-z_]*score[a-z_]*\"\s*:\s*(\d+\.?\d*)|:\s*(0\.\d+)", window)
        flat = [n for grp in nums for n in grp if n]
        if flat:
            hits.append({"context": window[:160], "numbers": flat[:6]})
    return hits


def main() -> int:
    result = {
        "model": "deepseek-v4-pro",
        "harness": "OpenHands",
        "protocol_note": "official = task-native skills (with-skill); ours(library) = all skills merged, agent self-selects",
        "sources_tried": [],
        "with_skill_pass_rate": None,
        "no_skill_pass_rate": None,
        "raw_hits": [],
        "source": None,
        "source_url": None,
    }

    candidates = [
        ("skillsbench.ai", "https://www.skillsbench.ai/leaderboard"),
        ("skillsbench.ai-root", "https://www.skillsbench.ai/"),
        ("arxiv", "https://arxiv.org/html/2602.12670v4"),
        ("arxiv-abs", "https://arxiv.org/abs/2602.12670"),
        ("hf-dataset", "https://huggingface.co/datasets/benchflow/skillsbench/raw/main/README.md"),
    ]
    for name, url in candidates:
        text = curl(url)
        result["sources_tried"].append({"name": name, "url": url, "bytes": len(text)})
        if not text:
            continue
        hits = find_deepseek_scores(text)
        if hits:
            result["raw_hits"].append({"source": name, "url": url, "hits": hits})
        row = parse_main_row(text, "DeepSeek V4 Pro")
        if row and result["with_skill_pass_rate"] is None:
            result["no_skill_pass_rate"] = row["no_skill"]
            result["with_skill_pass_rate"] = row["with_skill"]
            result["skill_gain_pp"] = row.get("gain_pp")
            result["n_task_instances"] = row.get("n_task_instances")
            result["n_tasks"] = (row.get("n_task_instances") or 0) // 3 or None
            result["source"] = name
            result["source_url"] = url
        # secondary reference: V4 Flash
        flash = parse_main_row(text, "DeepSeek V4 Flash")
        if flash and "flash_reference" not in result:
            result["flash_reference"] = flash

    if result["source"] is None:
        result["source"] = "MANUAL_TODO"
        result["note"] = ("Automated fetch found no parseable DeepSeek V4 Pro score. "
                          "Fill with_skill_pass_rate / no_skill_pass_rate by hand from "
                          "the leaderboard at https://www.skillsbench.ai/leaderboard and "
                          "note the URL.")

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"source={result['source']}")
    for h in result["raw_hits"]:
        print(f"  hit from {h['source']}: {h['hits'][:2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
