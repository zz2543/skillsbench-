#!/usr/bin/env python3
"""Scrub secrets from text/logs before they are committed.

Masks:
  - the live DeepSeek API key (read at runtime from the gitignored ../DeepSeek-api)
  - any OpenAI/DeepSeek-style `sk-...` token
  - `Authorization: Bearer ...` / `x-api-key: ...` header values

Usage:
  python sanitize.py <path> [<path> ...]      # sanitize files in place
  python sanitize.py --check <path> [...]     # exit 1 if any secret is found (no write)
  echo "text" | python sanitize.py            # filter stdin -> stdout
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # skillsbench-/
KEY_FILE = REPO_ROOT / "DeepSeek-api"

MASK = "***REDACTED***"

# generic secret patterns
PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(x-api-key:\s*)[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(api[_-]?key\"?\s*[:=]\s*\"?)[A-Za-z0-9._\-]{16,}"),
]


def _live_key() -> str | None:
    """Best-effort read of the current DeepSeek key so we can mask it explicitly."""
    try:
        first = KEY_FILE.read_text(encoding="utf-8").splitlines()[0]
        # format: "api:sk-...."
        return first.split(":", 1)[1].strip() if ":" in first else first.strip()
    except Exception:
        return None


def scrub(text: str) -> str:
    key = _live_key()
    if key:
        text = text.replace(key, MASK)
    for pat in PATTERNS:
        if pat.groups:
            text = pat.sub(lambda m: m.group(1) + MASK, text)
        else:
            text = pat.sub(MASK, text)
    return text


def _has_secret(text: str) -> bool:
    key = _live_key()
    if key and key in text:
        return True
    return any(p.search(text) for p in PATTERNS)


def main(argv: list[str]) -> int:
    if not argv:  # stdin filter
        sys.stdout.write(scrub(sys.stdin.read()))
        return 0

    check = argv[0] == "--check"
    paths = argv[1:] if check else argv
    hits = 0
    for p in paths:
        path = Path(p)
        if not path.is_file():
            continue
        try:
            data = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if check:
            if _has_secret(data):
                hits += 1
                print(f"SECRET FOUND: {path}")
        else:
            cleaned = scrub(data)
            if cleaned != data:
                path.write_text(cleaned, encoding="utf-8")
                print(f"sanitized: {path}")
    if check and hits:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
