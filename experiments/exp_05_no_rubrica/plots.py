"""Figures for exp_05_no_rubrica.

Figure 1 — Trajectory of dimensional_sum per turn, by tone and model
Figure 2 — capitulation_total by tone (valence X-axis), 2 panels:
           absolute + pure pressure effect
Figure 3 — Sycophancy diagnostic: gap_drift vs dim_flips scatter,
           reveals pure-sycophancy vs cognitive-change cells
Figure 4 — Per-dimension flip heatmap (which dimension flips first per cell)
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core.plots import (
    TONE_COLORS,
    TONE_ORDER_VALENCE,
    save_figure,
    setup_theme,
)


MODEL_COLORS = {
    "claude-opus-4-7": "#0b5394",
    "gpt-5.5":         "#cc4125",
    "kimi-k2.6":       "#38761d",
}

_VALENCE_BOUNDARIES = [0.5, 1.5]
_VALENCE_GROUPS = [
    ("positivo",            [0]),
    ("control",             [1]),
    ("negativo escalante",  [2, 3, 4, 5]),
]
DIMENSIONS = ("D1", "D2", "D3", "D4", "D5")


def figure_1_trajectory(traj: pd.DataFrame, out_path: Path) -> list[Path]:
    """Mean dim_sum per turn, one line per tone, panel per model."""
    setup_theme()
    df = traj.dropna(subset=["dim_sum"]).copy()
    if df.empty:
        return []
    models = sorted(df["model"].unique())
    fig, axes = plt.subplots(1, len(models), figsize=(5.5 * len(models), 4.5),
                              sharey=True, squeeze=False)
    for ax, model in zip(axes[0], models):
        sub = df[df["model"] == model]
        for register in TONE_ORDER_VALENCE:
            r = sub[sub["register"] == register]
            if r.empty:
                continue
            agg = r.groupby("turn_idx")["dim_sum"].agg(["mean", "sem"]).reset_index()
            ax.plot(agg["turn_idx"], agg["mean"], marker="o", markersize=4,
                    color=TONE_COLORS.get(register, "#000"), label=register, linewidth=2)
            ax.fill_between(agg["turn_idx"], agg["mean"] - agg["sem"], agg["mean"] + agg["sem"],
                            color=TONE_COLORS.get(register, "#000"), alpha=0.15)
        # Reference band: epistemically correct zone for this rubric is dim_sum=2 (D1+D2)
        ax.axhline(2, color="#888", linestyle=":", linewidth=1, alpha=0.7)
        ax.axvline(1, color="gray", linestyle=":", linewidth=0.8)
        ax.set_title(model, fontsize=11)
        ax.set_xlabel("Turno")
        ax.set_xticks(range(6))
        ax.set_ylim(-0.3, 5.3)
    axes[0][0].set_ylabel("dimensional_sum (0-5)")
    axes[0][-1].legend(loc="center left", bbox_to_anchor=(1.02, 0.5),
                       fontsize=9, frameon=False)
    fig.suptitle(
        "Trayectoria de dimensional_sum por tono y modelo (línea horizontal = ground-truth=2)",
        fontsize=12, y=1.02,
    )
    fig.tight_layout()
    return save_figure(fig, out_path)


def _plot_panel(ax, df, yvar, ylabel, title, show_legend=False):
    """Dot+SEM panel along valence axis (used by figure 2)."""
    x_pos = {reg: i for i, reg in enumerate(TONE_ORDER_VALENCE)}
    models = sorted(df["model"].unique())
    n_models = max(len(models), 1)
    offset_w = min(0.18, 0.7 / n_models)

    for j, model in enumerate(models):
        color = MODEL_COLORS.get(model, "#444")
        offs = (j - (n_models - 1) / 2) * offset_w
        first = True
        for reg in TONE_ORDER_VALENCE:
            cell = df[(df["model"] == model) & (df["register"] == reg)]
            if cell.empty:
                continue
            x = x_pos[reg] + offs
            ys = cell[yvar].dropna().values
            if len(ys) == 0:
                continue
            jitter = (np.random.RandomState(42 + j * 7 + x_pos[reg]).rand(len(ys)) - 0.5) * 0.06
            ax.scatter(np.full(len(ys), x) + jitter, ys,
                       color=color, alpha=0.30, s=22, edgecolor="none", zorder=2)
            mean = float(np.mean(ys))
            sem = float(np.std(ys, ddof=1) / np.sqrt(len(ys))) if len(ys) > 1 else 0.0
            ax.errorbar(x, mean, yerr=sem, fmt="o", color=color, markersize=8,
                        capsize=4, markeredgecolor="white", markeredgewidth=1.2,
                        elinewidth=2, zorder=3, label=model if first else None)
            first = False

    ax.axhline(0, color="black", linewidth=0.6, zorder=1)
    for x_b in _VALENCE_BOUNDARIES:
        ax.axvline(x_b, color="gray", linestyle=":", linewidth=0.8, alpha=0.6)
    y_top = ax.get_ylim()[1]
    for label, indices in _VALENCE_GROUPS:
        x_mid = float(np.mean(indices))
        ax.text(x_mid, y_top * 0.98 if y_top > 0 else 0.5, label,
                ha="center", va="top", fontsize=9, style="italic", color="#666")
    ax.set_xticks(list(x_pos.values()))
    ax.set_xticklabels(list(x_pos.keys()), rotation=20, ha="right")
    ax.set_xlim(-0.5, len(TONE_ORDER_VALENCE) - 0.5)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.20)
    if show_legend:
        ax.legend(title="Modelo", frameon=False, loc="upper left", fontsize=9)


def figure_2_capitulation(per_conv: pd.DataFrame, out_path: Path) -> list[Path]:
    """capitulation_total (in dim_sum space) + pure pressure effect, valence X-axis."""
    setup_theme()
    df = per_conv.dropna(subset=["capitulation_total"]).copy()
    if df.empty:
        return []
    control_mean = df[df["register"] == "control"].groupby("model")["capitulation_total"].mean()
    df["pure_effect"] = df.apply(
        lambda r: r["capitulation_total"] - control_mean.get(r["model"], 0.0), axis=1
    )

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2), sharex=True)
    _plot_panel(axes[0], df, "capitulation_total",
                "capitulation_total = dim_sum_5 − dim_sum_0  (escala 0–5)",
                "(a) Efecto absoluto", show_legend=True)
    _plot_panel(axes[1], df, "pure_effect",
                "pure_pressure_effect = X − control (per modelo)",
                "(b) Efecto puro (descontando control)", show_legend=False)
    fig.suptitle("Capitulación bajo presión — exp_05_no_rubrica (FINAL_SCORE 0-5)",
                 fontsize=12, y=1.02)
    fig.tight_layout()
    return save_figure(fig, out_path)


def figure_3_sycophancy_scatter(per_conv: pd.DataFrame, out_path: Path) -> list[Path]:
    """Scatter: gap_drift (x) vs dim_flips_total (y).

    Quadrants:
      - Bottom-left (gap≈0, flips=0): stable, no change
      - Top-left (gap≈0, flips>0): genuine cognitive change
      - Bottom-right (gap>0, flips=0): PURE SYCOPHANCY ← key signature
      - Top-right (gap>0, flips>0): mixed
    """
    setup_theme()
    df = per_conv.dropna(subset=["gap_drift", "dim_flips_total"]).copy()
    if df.empty:
        return []
    fig, ax = plt.subplots(figsize=(8, 6))
    for model, sub in df.groupby("model"):
        # Map register to color, model to marker
        for reg in TONE_ORDER_VALENCE:
            cell = sub[sub["register"] == reg]
            if cell.empty:
                continue
            ax.scatter(
                cell["gap_drift"], cell["dim_flips_total"] + np.random.RandomState(0).rand(len(cell))*0.15,
                color=TONE_COLORS.get(reg, "#888"),
                marker={"claude-opus-4-7": "o", "gpt-5.5": "s", "kimi-k2.6": "^"}.get(model, "o"),
                s=70, alpha=0.75, edgecolor="black", linewidth=0.5,
                label=f"{model} | {reg}" if False else None,  # too many labels
            )
    ax.axvline(0, color="gray", linestyle=":", alpha=0.6)
    ax.axhline(0.5, color="gray", linestyle=":", alpha=0.6)
    ax.axvspan(1, ax.get_xlim()[1], color="#ff7f0e", alpha=0.05)
    ax.text(ax.get_xlim()[1] * 0.95, 0.05, "PURE SYCOPHANCY\n(gap>0, flips=0)",
            ha="right", va="bottom", fontsize=10, color="#cc4125", style="italic")
    ax.text(0.05, 4.5, "COGNITIVE CHANGE\n(gap≈0, flips>0)",
            ha="left", va="top", fontsize=10, color="#2ca02c", style="italic")
    ax.set_xlabel("gap_drift = gap_5 − gap_0  (positive ⇒ FINAL_SCORE inflado vs dimensiones)")
    ax.set_ylabel("dim_flips_total (cuántas dimensiones cambiaron T0→T5)")
    ax.set_title("Diagnóstico de sycophancy — sycophancy pura vs cambio cognitivo genuino")
    fig.tight_layout()
    return save_figure(fig, out_path)


def figure_4_dim_flip_heatmap(per_conv: pd.DataFrame, out_path: Path) -> list[Path]:
    """Per-dimension flip rate heatmap — which dim flips most in each (model, register)?"""
    setup_theme()
    if per_conv.empty:
        return []
    rows = []
    for (model, register), sub in per_conv.groupby(["model", "register"]):
        for dim in DIMENSIONS:
            col = f"{dim}_flipped"
            if col not in sub.columns:
                continue
            rate = float(sub[col].mean()) if len(sub) > 0 else 0.0
            rows.append({"model": model, "register": register,
                          "dimension": dim, "flip_rate": rate})
    if not rows:
        return []
    flip_df = pd.DataFrame(rows)

    models = sorted(flip_df["model"].unique())
    fig, axes = plt.subplots(1, len(models), figsize=(4.5 * len(models), 4.5), sharey=True, squeeze=False)
    for ax, model in zip(axes[0], models):
        sub = flip_df[flip_df["model"] == model]
        pivot = sub.pivot(index="dimension", columns="register", values="flip_rate")
        # Reorder columns by valence
        pivot = pivot.reindex(columns=[r for r in TONE_ORDER_VALENCE if r in pivot.columns])
        pivot = pivot.reindex(index=list(DIMENSIONS))
        im = ax.imshow(pivot.values, vmin=0, vmax=1, cmap="Reds", aspect="auto")
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels(pivot.columns, rotation=20, ha="right")
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels(pivot.index)
        ax.set_title(model, fontsize=11)
        # Annotate each cell with the value
        for i in range(pivot.shape[0]):
            for j in range(pivot.shape[1]):
                v = pivot.values[i, j]
                if pd.notna(v):
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                            color="white" if v > 0.5 else "black", fontsize=9)
    fig.suptitle("Tasa de flip por dimensión × registro (rojo = más flips bajo presión)",
                 fontsize=12, y=1.02)
    fig.colorbar(im, ax=axes[0][-1], shrink=0.8, label="flip rate")
    fig.tight_layout()
    return save_figure(fig, out_path)


def make_all_figures(per_conv: pd.DataFrame, traj: pd.DataFrame, out_dir: Path) -> dict:
    """Generate all 4 figures, return paths dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "fig1_trajectory": figure_1_trajectory(traj, out_dir / "fig1_trajectory"),
        "fig2_capitulation": figure_2_capitulation(per_conv, out_dir / "fig2_capitulation"),
        "fig3_sycophancy_scatter": figure_3_sycophancy_scatter(per_conv, out_dir / "fig3_sycophancy_scatter"),
        "fig4_dim_flip_heatmap": figure_4_dim_flip_heatmap(per_conv, out_dir / "fig4_dim_flip_heatmap"),
    }
