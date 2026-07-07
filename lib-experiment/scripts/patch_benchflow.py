#!/usr/bin/env python3
"""Idempotently patch the installed benchflow OpenHands launch_cmd to run the agent
proxy-free.

Why: on this host (China + Clash), the OpenHands install needs the proxy (github),
but the agent's runtime DeepSeek call 502s *through* the proxy while api.deepseek.com
is 100% reliable DIRECT. So we unset the proxy env right before `openhands acp`.

Run once after `uv sync` (the edit lives in the .venv, which is not committed):
  python scripts/patch_benchflow.py [path-to-skillsbench-upstream]
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_UPSTREAM = HERE.parents[2] / "skillsbench-upstream"

NEEDLE = '"openhands acp --always-approve --override-with-envs"'
PATCH = (
    '"unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY; "\n'
    '            "openhands acp --always-approve --override-with-envs"'
)
MARKER = "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY"


def main() -> int:
    upstream = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_UPSTREAM
    reg = upstream / ".venv/lib/python3.12/site-packages/benchflow/agents/registry.py"
    if not reg.is_file():
        raise SystemExit(f"registry.py not found: {reg} (run `uv sync` first)")
    text = reg.read_text(encoding="utf-8")
    if MARKER in text:
        print("already patched.")
        return 0
    if NEEDLE not in text:
        raise SystemExit("launch_cmd line not found — benchflow layout changed; patch manually.")
    text = text.replace(NEEDLE, PATCH, 1)
    reg.write_text(text, encoding="utf-8")
    print(f"patched OpenHands launch_cmd to run proxy-free: {reg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
