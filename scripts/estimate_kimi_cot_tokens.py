"""Estimate Kimi K2.6's reasoning vs visible token split per turn.

Moonshot's API returns the full `reasoning_content` text but does NOT report
a separate `reasoning_tokens` count — `output_tokens` includes BOTH the visible
response and the internal reasoning, mixed. To produce a fair comparison
against ChatGPT (which separates them natively), we estimate Kimi's split by:

    1. Tokenizing the visible `assistant_response` with tiktoken cl100k_base
       → `visible_tk`
    2. Tokenizing the raw `reasoning_content` with the same tokenizer
       → `reasoning_tk`
    3. Computing the proportion: `prop_reasoning = reasoning_tk /
       (reasoning_tk + visible_tk)`
    4. Applying it to the `output_tokens` reported by Moonshot:
        `cot_tokens_est = output_tokens * prop_reasoning`
        `visible_tokens_est = output_tokens - cot_tokens_est`

The sum equals `output_tokens` exactly, so no double-counting. Caveat:
tiktoken cl100k_base is not Kimi's native tokenizer, but for Spanish text
it gives a stable proportion (typically 86–91% reasoning) — close enough
for a divulgation chart.

This script reads the raw `cot_text_raw` and `assistant_response` from the
ORIGINAL development repository (`under-pressure/`) where they are
preserved, computes the estimates, and writes the numerical estimates
back to the public repo's `turns.jsonl` as new fields:

    cot_tokens_est       — int, estimated reasoning tokens
    visible_tokens_est   — int, estimated visible tokens

The raw reasoning text is NEVER copied to the public repo — only the
two integer estimates. Other models (Opus, GPT) get `cot_tokens_est = None`
since they don't need estimation (GPT has it natively, Opus doesn't expose it).

Usage:
    python -m scripts.estimate_kimi_cot_tokens \\
        --source-repo ../under-pressure
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import tiktoken


REPO_ROOT = Path(__file__).resolve().parents[1]
ENCODING = tiktoken.get_encoding("cl100k_base")


def tokenize_count(text: str) -> int:
    if not text:
        return 0
    return len(ENCODING.encode(text))


def build_source_lookup(source_repo: Path) -> dict:
    """Return {(conversation_id_orig, turn_idx, model, register, run_idx):
              {'cot_text_raw': str, 'assistant_response': str, 'output_tokens': int}}.

    Indexed by the ORIGINAL repo's conversation_id (which differs from the
    public repo's renumbered ids), so we cross-reference by content (model,
    register, response text).
    """
    lookup = {}
    for cond in ("no_rubrica", "rubrica"):
        p = source_repo / f"runs/exp_05_{cond}/canonical_v2/turns.jsonl"
        if not p.exists():
            print(f"[warn] source not found: {p}")
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("model") != "kimi-k2.6":
                continue
            # Index by (model, register, turn_idx, assistant_response head)
            # so we can match to public repo even though run_idx may differ.
            key = (r["model"], r["register"], r["turn_idx"],
                   (r.get("assistant_response") or "")[:200])
            lookup[key] = {
                "cot_text_raw": r.get("cot_text_raw") or "",
                "assistant_response": r.get("assistant_response") or "",
                "output_tokens": r.get("output_tokens") or 0,
            }
    return lookup


def estimate_for_condition(condition: str, source_lookup: dict) -> dict:
    """Read public repo's turns.jsonl, augment Kimi rows with estimates,
    write back. Returns stats dict."""
    p = REPO_ROOT / f"runs/exp_05_{condition}/canonical_v2/turns.jsonl"
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

    matched = 0
    unmatched = 0
    proportions = []
    for r in rows:
        if r.get("model") != "kimi-k2.6":
            continue
        # Match to source by (model, register, turn_idx, response head)
        key = (r["model"], r["register"], r["turn_idx"],
               (r.get("assistant_response") or "")[:200])
        src = source_lookup.get(key)
        if src is None:
            unmatched += 1
            continue
        matched += 1
        cot_text = src["cot_text_raw"]
        vis_text = src["assistant_response"]
        cot_tk = tokenize_count(cot_text)
        vis_tk = tokenize_count(vis_text)
        total_tk = cot_tk + vis_tk
        if total_tk == 0:
            r["cot_tokens_est"] = 0
            r["visible_tokens_est"] = r.get("output_tokens", 0)
            continue
        prop_reasoning = cot_tk / total_tk
        proportions.append(prop_reasoning)
        out_tokens = r.get("output_tokens") or 0
        cot_est = round(out_tokens * prop_reasoning)
        vis_est = out_tokens - cot_est
        r["cot_tokens_est"] = cot_est
        r["visible_tokens_est"] = vis_est

    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )

    return {
        "condition": condition,
        "kimi_turns_matched": matched,
        "kimi_turns_unmatched": unmatched,
        "avg_prop_reasoning": (sum(proportions) / len(proportions)
                               if proportions else 0.0),
        "min_prop_reasoning": min(proportions) if proportions else 0.0,
        "max_prop_reasoning": max(proportions) if proportions else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-repo", required=True,
                        help="Path to the development repo with cot_text_raw preserved.")
    args = parser.parse_args()
    source = Path(args.source_repo).resolve()
    if not source.exists():
        print(f"Source repo not found: {source}", file=sys.stderr)
        return 1
    print(f"Reading source: {source}")
    lookup = build_source_lookup(source)
    print(f"Source lookup entries: {len(lookup)}\n")

    for cond in ("no_rubrica", "rubrica"):
        stats = estimate_for_condition(cond, lookup)
        print(f"=== {cond} ===")
        print(f"  Kimi turns matched:    {stats['kimi_turns_matched']}/120")
        print(f"  Kimi turns unmatched:  {stats['kimi_turns_unmatched']}")
        print(f"  Reasoning proportion:  avg={stats['avg_prop_reasoning']:.3f}, "
              f"range=[{stats['min_prop_reasoning']:.3f}, {stats['max_prop_reasoning']:.3f}]")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
