"""Append-only JSONL logger for runs.

Every record is one JSON object on its own line. The logger flushes after
each write, so a crash mid-run preserves everything written up to that point.

Thread-safe: uses a per-file lock so concurrent writes from a thread pool
never interleave within a record.

Conventions:
    turns.jsonl           — one record per (conversation, turn)
    judge_pairs.jsonl     — one record per (conversation, turn pair) sent to the judge
    judge_labels.jsonl    — one record per judge response
    errors.jsonl          — provider failures, parse failures, refusals worth flagging
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


class JSONLLogger:
    """Tiny append-only JSONL writer with one file per kind of record. Thread-safe."""

    def __init__(self, run_dir: Path | str):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        # One global lock per logger instance — fine-grained per-file locks are
        # not worth the complexity at our scale (a few hundred writes per run).
        self._lock = threading.Lock()

    # -- core write -----------------------------------------------------
    def log(self, kind: str, record: dict) -> None:
        """Append a record to <kind>.jsonl in the run dir.

        The record must be JSON-serializable. Non-serializable fields are
        coerced via str() as a fallback. Safe to call from multiple threads.
        """
        path = self.run_dir / f"{kind}.jsonl"
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.flush()

    # -- typed helpers --------------------------------------------------
    def log_turn(self, record: dict) -> None:
        self.log("turns", record)

    def log_error(self, record: dict) -> None:
        self.log("errors", record)

    def log_judge_pair(self, record: dict) -> None:
        self.log("judge_pairs", record)

    def log_judge_label(self, record: dict) -> None:
        self.log("judge_labels", record)


def read_jsonl(path: Path | str) -> list[dict]:
    """Read a JSONL file into a list of dicts. Empty/missing file → []."""
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
