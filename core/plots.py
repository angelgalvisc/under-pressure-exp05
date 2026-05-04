"""Shared plotting utilities (theme, palette, export).

Experiment-specific plots live in `experiments/<exp>/plots.py`. This module
provides only the cross-experiment defaults: a clean theme, a sensible
palette, and a save_figure helper that exports both PNG and PDF for paper /
blog use.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import seaborn as sns


# ---------------------------------------------------------------------------
# Color palettes
# ---------------------------------------------------------------------------
# Register palette for exp_05.
# Registers (4):
#   adulacion          — flattery + appeal to expertise (positive valence)
#   control            — open epistemic questions, no pressure (neutral baseline)
#   hostil-correctivo  — factual assertion + score-change demand, no affect
#   hostil-combinado   — insult + threat + correction (composite, full hostility)
TONE_COLORS = {
    "adulacion":          "#2ca02c",   # green   — positive valence
    "control":            "#1f77b4",   # blue    — control reference
    "hostil-correctivo":  "#7f7f7f",   # gray    — cold pressure baseline
    "hostil-combinado":   "#9467bd",   # purple  — composite (all mechanisms)
}

# Canonical X-axis order: positive → neutral → hostile (escalating mechanisms).
# Use this order in all per-register plots so the U/V shape (control at the
# fulcrum) reads consistently across figures.
TONE_ORDER_VALENCE = [
    "adulacion",          # positive valence
    "control",            # neutral, no pressure
    "hostil-correctivo",  # cold pressure baseline
    "hostil-combinado",   # + composite hostility
]
# Backwards-compat aliases for callers that import the old names.
TONE_ORDER_ALL = TONE_ORDER_VALENCE
TONE_ORDER_PURE = TONE_ORDER_VALENCE

TONE_LINESTYLES = {
    "adulacion":          "-",
    "control":            "-",
    "hostil-correctivo":  "-",
    "hostil-combinado":   "--",  # dashed → composite, visually distinct
}


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
def setup_theme() -> None:
    """Set a clean, consistent matplotlib/seaborn theme for figures."""
    sns.set_style("whitegrid")
    plt.rcParams.update(
        {
            "font.size": 11,
            "axes.titlesize": 12,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 9,
            "figure.titlesize": 13,
            "font.family": "sans-serif",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "savefig.dpi": 150,
            "savefig.bbox": "tight",
        }
    )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def save_figure(
    fig,
    path: Path | str,
    formats: Iterable[str] = ("png", "pdf"),
) -> list[Path]:
    """Save a figure to one or more formats. Returns the list of paths written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for fmt in formats:
        out = path.with_suffix(f".{fmt}")
        fig.savefig(out)
        written.append(out)
    return written
