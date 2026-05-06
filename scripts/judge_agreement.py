#!/usr/bin/env python3
"""Report exact agreement between the two judge passes.

The judge emits two labels for every (conversation_id, current_turn) pair.
This script reports how often both passes selected the same label. It does
not change the dataset; it only audits `judge_labels.jsonl`.

Usage:
    python -m scripts.judge_agreement
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONDITIONS = {
    "sin_rubrica": ROOT / "runs/exp_05_no_rubrica/canonical_v2/judge_labels.jsonl",
    "con_rubrica": ROOT / "runs/exp_05_rubrica/canonical_v2/judge_labels.jsonl",
}


def summarize(path: Path) -> dict:
    by_pair: dict[tuple[str, int], dict[int, str]] = defaultdict(dict)
    labels: Counter[str] = Counter()

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = (row["conversation_id"], int(row["current_turn"]))
        pass_idx = int(row["pass_idx"])
        label = row["label"]
        by_pair[key][pass_idx] = label
        labels[label] += 1

    complete_pairs = [v for v in by_pair.values() if 0 in v and 1 in v]
    agreed = sum(1 for v in complete_pairs if v[0] == v[1])
    total = len(complete_pairs)
    return {
        "pairs": len(by_pair),
        "complete_pairs": total,
        "agreement_rate": agreed / total if total else 0.0,
        "disagreement_rate": 1.0 - (agreed / total) if total else 0.0,
        "labels": dict(sorted(labels.items())),
    }


def main() -> int:
    for condition, path in CONDITIONS.items():
        summary = summarize(path)
        print(f"\n{condition}")
        print(f"pairs: {summary['pairs']}")
        print(f"complete_pairs: {summary['complete_pairs']}")
        print(f"judge_agreement_rate: {summary['agreement_rate']:.2%}")
        print(f"label_disagreement_rate: {summary['disagreement_rate']:.2%}")
        print("labels:")
        for label, count in summary["labels"].items():
            print(f"  {label}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
