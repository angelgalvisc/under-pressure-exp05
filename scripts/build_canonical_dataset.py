"""Build the canonical exp_05 dataset by aggregating raw timestamped runs.

NOTE: The published snapshot under `runs/exp_05_*/canonical_v2/` is ALREADY
the canonical dataset. This script is only needed if you re-run the
experiment from scratch (which generates timestamped raw runs in
`runs/exp_05_*/<YYYYMMDDTHHMMSSZ>/`) and want to reconstruct
`canonical_v2/` from them.

Policy when raw runs are available:
  * Pressure registers (adulacion, hostil-correctivo, hostil-combinado):
      keep all *complete* (6-turn) conversations from raw runs.
  * Control register:
      keep all complete conversations from raw runs.
  * Conversation IDs are renumbered sequentially (run000, run001, ...) within
    each (model, register) cell so the merged file has no ID collisions.
  * Each row gets re-parsed with the current parser so the canonical snapshot
    always reflects the latest extraction logic.

Output: runs/exp_05_<cond>/canonical_v2/{turns.jsonl, manifest.json}.

Usage (idempotent; only meaningful if raw timestamped runs exist):
    python -m scripts.build_canonical_dataset
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

# Make the project root importable so we can re-parse responses with the
# current parser (so the canonical snapshot always reflects parser fixes).
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from core.parser import parse_score_json  # noqa: E402

def collect_runs(exp_dir: Path) -> list[tuple[str, Path]]:
    """Return (run_id, run_dir) sorted oldest-first, skipping drafts/canonical."""
    out = []
    for d in sorted(exp_dir.iterdir()):
        if not d.is_dir():
            continue
        if d.name.startswith("_") or d.name == "canonical_v2":
            continue
        if (d / "turns.jsonl").exists():
            out.append((d.name, d))
    return out


def build_for_experiment(exp_id: str) -> dict:
    exp_dir = REPO_ROOT / "runs" / exp_id
    runs = collect_runs(exp_dir)
    print(f"\n=== {exp_id}: {len(runs)} runs ===")

    # cell = (model, register); value = list of (src_run_id, orig_cid, rows_for_conv)
    cells: dict[tuple, list] = defaultdict(list)

    for run_id, run_dir in runs:
        rows = [json.loads(l) for l in (run_dir / "turns.jsonl").read_text().splitlines() if l.strip()]
        # Group by original conversation_id within this run
        convs: dict[str, list] = defaultdict(list)
        for r in rows:
            convs[r["conversation_id"]].append(r)
        for orig_cid, conv_rows in convs.items():
            if len(conv_rows) < 6:
                continue  # skip incomplete conversations (failed mid-way)
            sample = conv_rows[0]
            cells[(sample["model"], sample["register"])].append(
                (run_id, orig_cid, conv_rows)
            )

    # Renumber conversations per cell. Order: by source run_id (chronological), then by orig_cid.
    merged_rows: list[dict] = []
    n_per_cell: dict[str, int] = {}
    for (model, reg), conv_list in cells.items():
        conv_list.sort(key=lambda x: (x[0], x[1]))
        n_per_cell[f"{model}__{reg}"] = len(conv_list)
        for new_idx, (src_run_id, orig_cid, rows_for_conv) in enumerate(conv_list):
            new_cid = f"{model}__{reg}__run{new_idx:03d}"
            for r in sorted(rows_for_conv, key=lambda x: x["turn_idx"]):
                new_r = dict(r)
                new_r["run_idx"] = new_idx
                new_r["conversation_id"] = new_cid
                new_r["_source_run_id"] = src_run_id
                new_r["_orig_conversation_id"] = orig_cid
                # Re-parse with current parser so the canonical snapshot
                # always reflects the latest extraction logic (DIMENSIONS
                # fallback, etc.). Preserves None outputs as None.
                response_text = new_r.get("assistant_response")
                if response_text:
                    reparsed = parse_score_json(response_text)
                    if reparsed is not None:
                        new_r["parsed"] = reparsed
                merged_rows.append(new_r)

    merged_rows.sort(key=lambda r: (r["conversation_id"], r["turn_idx"]))

    # Stats
    by_register = defaultdict(int)
    for r in merged_rows:
        by_register[r["register"]] += 1
    source_runs = sorted({r["_source_run_id"] for r in merged_rows})

    out_dir = exp_dir / "canonical_v2"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "turns.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in merged_rows) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "experiment_id": exp_id,
        "kind": "canonical_v2_aggregator",
        "policy": (
            "All complete (6-turn) conversations from raw timestamped runs are "
            "kept. Conversations are renumbered sequentially per (model, register) "
            "cell so the merged file has no ID collisions. Each row is re-parsed "
            "with the current parser to ensure the canonical snapshot reflects "
            "the latest extraction logic."
        ),
        "n_total_turns": len(merged_rows),
        "n_distinct_conversations": sum(n_per_cell.values()),
        "by_register": dict(by_register),
        "n_per_cell": dict(sorted(n_per_cell.items())),
        "source_runs": source_runs,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"  total turns:            {len(merged_rows)}")
    print(f"  distinct conversations: {sum(n_per_cell.values())}")
    print(f"  by register:            {dict(by_register)}")
    print(f"  n_per_cell:")
    for k, v in sorted(n_per_cell.items()):
        print(f"    {k:<40} n={v}")
    print(f"  source runs used:       {source_runs}")
    return manifest


def main() -> int:
    for exp_id in ("exp_05_no_rubrica", "exp_05_rubrica"):
        build_for_experiment(exp_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
