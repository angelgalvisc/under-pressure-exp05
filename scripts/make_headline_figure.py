"""Generate the headline figure for the README of exp_05.

Bar chart: Δ_neta (capitulation − control) per model × register × condition.
Shows the rubric-protection effect at a glance: with rubric the bars
collapse toward zero; without rubric the hostile registers tower.

Output: docs/headline_capitulation.{png,pdf}
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "docs"
OUT_DIR.mkdir(exist_ok=True)


def load_deltas(canonical_path: Path) -> dict:
    """Compute mean Δ T0→T5 per (model, register) from canonical_v2/turns.jsonl."""
    rows = [json.loads(l) for l in canonical_path.read_text().splitlines() if l.strip()]
    by_conv: dict = {}
    for r in rows:
        by_conv.setdefault(r["conversation_id"], {})[r["turn_idx"]] = r
    cell_scores: dict = {}
    for cid, turns in by_conv.items():
        sample = turns[0]
        s0 = (turns.get(0) or {}).get("parsed", {}).get("score")
        s5 = (turns.get(5) or {}).get("parsed", {}).get("score")
        if s0 is None or s5 is None:
            continue
        key = (sample["model"], sample["register"])
        cell_scores.setdefault(key, []).append(s5 - s0)
    cell_means = {k: float(np.mean(v)) for k, v in cell_scores.items()}
    return cell_means


def compute_neta(cell_means: dict, models: list, registers: list) -> dict:
    """Δ_neta = Δ(register) - Δ(control), per model."""
    out = {}
    for m in models:
        ctrl = cell_means.get((m, "control"), 0.0)
        for reg in registers:
            d = cell_means.get((m, reg), 0.0)
            out[(m, reg)] = d - ctrl
    return out


MODELS = ["claude-opus-4-7", "gpt-5.5", "kimi-k2.6"]
MODEL_LABELS = {"claude-opus-4-7": "Opus 4.7",
                "gpt-5.5": "GPT-5.5",
                "kimi-k2.6": "Kimi K2.6"}
REGISTERS = ["adulacion", "hostil-correctivo", "hostil-combinado"]
REGISTER_LABELS = {"adulacion": "adulación",
                   "hostil-correctivo": "hostil-correctivo",
                   "hostil-combinado": "hostil-combinado"}
REGISTER_COLORS = {"adulacion": "#2ca02c",
                   "hostil-correctivo": "#7f7f7f",
                   "hostil-combinado": "#9467bd"}


def main() -> int:
    sin_rubrica = compute_neta(
        load_deltas(REPO_ROOT / "runs/exp_05_no_rubrica/canonical_v2/turns.jsonl"),
        MODELS, REGISTERS,
    )
    con_rubrica = compute_neta(
        load_deltas(REPO_ROOT / "runs/exp_05_rubrica/canonical_v2/turns.jsonl"),
        MODELS, REGISTERS,
    )

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    x = np.arange(len(MODELS))
    width = 0.27

    for ax, data, title in [
        (axes[0], sin_rubrica, "Sin rúbrica (FINAL_SCORE 0–5)"),
        (axes[1], con_rubrica, "Con rúbrica (5 dimensiones binarias)"),
    ]:
        for i, reg in enumerate(REGISTERS):
            vals = [data.get((m, reg), 0.0) for m in MODELS]
            offset = (i - 1) * width
            bars = ax.bar(
                x + offset, vals, width,
                label=REGISTER_LABELS[reg],
                color=REGISTER_COLORS[reg],
                edgecolor="black", linewidth=0.5,
            )
            for b, v in zip(bars, vals):
                # Label above bar always, regardless of sign, to avoid overlapping
                # the X-axis labels (model names).
                y_pos = v + 0.08 if v >= 0 else v + 0.08
                ax.text(b.get_x() + b.get_width() / 2, y_pos,
                        f"{v:+.2f}", ha="center", fontsize=8, color="black")
        ax.axhline(0, color="black", linewidth=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels([MODEL_LABELS[m] for m in MODELS])
        ax.set_title(title, fontsize=11)
        ax.set_ylim(-1.0, 4.4)
        ax.grid(axis="y", linestyle=":", alpha=0.4)

    axes[0].set_ylabel("Δ_neta = Δ(presión) − Δ(control)\nen escala 0–5", fontsize=10)
    axes[1].legend(loc="upper right", fontsize=9, frameon=True)

    fig.suptitle(
        "La rúbrica dimensional reduce la capitulación bajo presión social en los 3 modelos",
        fontsize=12.5, y=1.00,
    )
    fig.tight_layout()

    png_path = OUT_DIR / "headline_capitulation.png"
    pdf_path = OUT_DIR / "headline_capitulation.pdf"
    fig.savefig(png_path, dpi=160, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    print(f"Saved {png_path}")
    print(f"Saved {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
