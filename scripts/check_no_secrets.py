#!/usr/bin/env python3
"""Pre-commit safety scan: detect accidentally committed API keys.

Usage:
    python scripts/check_no_secrets.py

Exit codes:
    0 — clean
    1 — suspicious patterns found

This is a tripwire, not a security guarantee. Use it as one of multiple
layers (along with .gitignore and code review).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Patterns that look like real API keys (with prefix and minimum entropy).
KEY_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),       # Anthropic
    re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}"),      # OpenAI project keys
    re.compile(r"sk-or-[A-Za-z0-9_-]{20,}"),        # OpenRouter
    re.compile(r"sk-[A-Za-z0-9]{40,}"),             # Generic sk- with high entropy
]

# Patterns that look like populated env-vars (KEY=non-empty-value).
ENV_PATTERNS = [
    re.compile(
        r"(ANTHROPIC|OPENAI|OPENROUTER|MOONSHOT)_API_KEY\s*=\s*[A-Za-z0-9][A-Za-z0-9_\-]{8,}"
    ),
]

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ipynb_checkpoints",
    "runs",
    "results",
}

SKIP_FILES = {
    # .env and its variants are the legitimate place for secrets; they are
    # already excluded by .gitignore. We only care about secrets leaking
    # OUTSIDE of these files.
    ".env",
    ".env.local",
    ".env.bak",
    ".env.example",
    "check_no_secrets.py",
}


def _is_env_dotfile(name: str) -> bool:
    """Match .env, .env.bak, .env.local, .env.<anything>.local, etc."""
    return name == ".env" or name.startswith(".env.")

ALLOWED_EXTENSIONS = {
    ".py", ".md", ".txt", ".yaml", ".yml", ".json",
    ".sh", ".cfg", ".ini", ".toml", "",
}


def scan_file(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    for i, line in enumerate(content.splitlines(), 1):
        # Never print the actual line — could expose the very secret we are detecting.
        for pat in KEY_PATTERNS:
            if pat.search(line):
                findings.append(f"{path}:{i}: API key pattern detected (content redacted)")
        for pat in ENV_PATTERNS:
            if pat.search(line):
                findings.append(f"{path}:{i}: populated env var detected (content redacted)")
    return findings


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    findings: list[str] = []

    for path in repo.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.name in SKIP_FILES or _is_env_dotfile(path.name):
            continue
        if path.suffix not in ALLOWED_EXTENSIONS:
            continue
        findings.extend(scan_file(path))

    if findings:
        print("WARNING: possible secrets found:", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        print(f"\nTotal: {len(findings)} suspicious line(s).", file=sys.stderr)
        print("Resolve before committing.", file=sys.stderr)
        return 1

    print("OK: no secrets detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
