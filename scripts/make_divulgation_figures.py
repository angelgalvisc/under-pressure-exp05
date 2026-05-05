"""Generate 6 editorial-style divulgation figures for exp_05.

Three chart types × two conditions (sin/con rúbrica):

    1A/1B  "Cuánto cedió el modelo bajo presión"     — line chart
    2A/2B  "Sicofancia: cuántas veces el modelo cedió" — horizontal bars
    3A/3B  "Tokens por conversación"                  — stacked horizontal bars

Aesthetic: NYT/FT data-journalism style — bold large title, lighter
subtitle, light-gray background, dotted gridlines, value labels next to
data points, register icons in rounded white boxes on the X axis.

Output: docs/divulgacion/{cap,sicofancia,tokens}_{sin,con}_rubrica.png

Usage (from the repo root):
    python -m scripts.make_divulgation_figures
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "docs" / "divulgacion"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Aesthetic
# ---------------------------------------------------------------------------
BG = "#f4f4f3"
INK = "#1a1a1a"
SUBTITLE_COLOR = "#666666"
GRID_COLOR = "#dcdcdc"

COLORS = {
    "opus": "#6dab8a",   # pastel green — distinct from black (GPT) under alpha
    "gpt":  "#1a1a1a",   # black        — intermediate, neutral
    "kimi": "#dc2626",   # vivid red    — most volatile, the "alarm" color
}
MODELS = ["opus", "gpt", "kimi"]
MODEL_ID = {"opus": "claude-opus-4-7", "gpt": "gpt-5.5", "kimi": "kimi-k2.6"}
MODEL_LABEL = {"opus": "Opus 4.7", "gpt": "ChatGPT 5.5", "kimi": "Kimi K2.6"}

# Registers (4): id, glyph for icon box, display label.
# Order is left-to-right pressure-intensity: control (baseline) →
# adulación (positive valence) → hostil-correctivo → hostil-combinado.
# This order is used in ALL charts (line chart x-axis + horizontal bar
# chart row stack from top to bottom).
REGISTERS = [
    ("control",           "•",  "control"),
    ("adulacion",         "♥",  "adulación"),
    ("hostil-correctivo", "!",  "hostil-correctivo"),
    ("hostil-combinado",  "x",  "hostil-combinado"),
]

# Default font: standard sans, no fancy fallbacks needed since icons are drawn.
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "axes.unicode_minus": False,
})


# ---------------------------------------------------------------------------
# Custom icon drawing — robust monochrome shapes using matplotlib patches
# ---------------------------------------------------------------------------
def draw_icon(ax, x, y, register, *, size=0.04, transform=None):
    """Draw a rounded transparent box with a monochrome line-art icon.

    (x, y) and size are in axis-fraction coordinates by default. Pass
    `transform=fig.transFigure` to position in figure coords.

    When using `fig.transFigure`, fig-fraction units don't preserve aspect
    ratio: a "1×1 fig-coord square" is actually an inches-rectangle as wide
    as the figure but only as tall as it is. To make icons render as
    visually symmetric in physical units we apply a horizontal aspect
    compensation factor `arx = fig_h / fig_w` to all x-direction offsets.
    """
    if transform is None:
        transform = ax.transAxes

    # Aspect-ratio compensation: if drawing in fig coords, x-offsets must be
    # shrunk by fig_h/fig_w so that what's authored as "symmetric" renders
    # as visually symmetric. In ax.transAxes we assume the axes itself
    # already manages aspect (or it doesn't matter at this scale).
    fig = ax.figure
    fig_w, fig_h = fig.get_size_inches()
    arx = (fig_h / fig_w) if transform is fig.transFigure else 1.0

    pad_y = size
    pad_x = size * arx
    # Container box: TRANSPARENT fill (blends with chart background) + thin
    # gray border just to delineate the icon area. Square in PHYSICAL units.
    box = mpatches.FancyBboxPatch(
        (x - pad_x, y - pad_y), 2 * pad_x, 2 * pad_y,
        boxstyle=f"round,pad=0,rounding_size={pad_y * 0.30}",
        linewidth=0.9, edgecolor="#9a9a9a", facecolor="none",
        transform=transform, clip_on=False, zorder=3,
    )
    ax.add_patch(box)

    # Helper to make a physically-circular shape (using Ellipse with
    # x-radius compensated by arx).
    def _circle(center, r, **kwargs):
        cx, cy = center
        return mpatches.Ellipse((cx, cy), 2 * r * arx, 2 * r, **kwargs)

    inner = size * 0.55  # icon proper sits inside the box with breathing room
    LW = 1.25  # 30% thinner stroke (was 1.8) — finer line-art

    if register == "adulacion":
        # Heart: 2-curve cubic-bezier path. ALL x offsets multiplied by arx
        # so the heart is visually symmetric in physical units.
        import matplotlib.path as mpath
        Path = mpath.Path
        verts = [
            (x, y - inner * 0.95),
            (x + inner * 1.05 * arx, y - inner * 0.30),
            (x + inner * 0.95 * arx, y + inner * 0.75),
            (x, y + inner * 0.30),
            (x - inner * 0.95 * arx, y + inner * 0.75),
            (x - inner * 1.05 * arx, y - inner * 0.30),
            (x, y - inner * 0.95),
        ]
        codes = [Path.MOVETO,
                 Path.CURVE4, Path.CURVE4, Path.CURVE4,
                 Path.CURVE4, Path.CURVE4, Path.CURVE4]
        ax.add_patch(mpatches.PathPatch(
            mpath.Path(verts, codes),
            facecolor="none", edgecolor=INK, linewidth=LW,
            joinstyle="round", capstyle="round",
            transform=transform, clip_on=False, zorder=4,
        ))

    elif register == "control":
        # Balance scales (justicia) — vertical post, horizontal beam at top,
        # two pans hanging from the beam ends, base at the bottom.
        post_lw = LW * 1.25
        # Vertical post (post extends from base to beam)
        ax.plot([x, x],
                [y - inner * 0.78, y + inner * 0.55],
                color=INK, linewidth=post_lw,
                solid_capstyle="round",
                transform=transform, clip_on=False, zorder=5)
        # Horizontal beam at top
        beam_y = y + inner * 0.55
        beam_half = inner * 0.85 * arx
        ax.plot([x - beam_half, x + beam_half],
                [beam_y, beam_y],
                color=INK, linewidth=post_lw,
                solid_capstyle="round",
                transform=transform, clip_on=False, zorder=5)
        # Pans + connector chains hanging from each beam end
        pan_half = inner * 0.32 * arx
        pan_h = inner * 0.22
        pan_top_y = y + inner * 0.05  # top of pan opening
        pan_center_y = pan_top_y - pan_h * 0.5  # center for arc
        for sign in (-1, 1):
            beam_end_x = x + sign * beam_half
            # Vertical connector chain from beam end to top of pan
            ax.plot([beam_end_x, beam_end_x],
                    [beam_y, pan_top_y],
                    color=INK, linewidth=LW * 0.7,
                    solid_capstyle="round",
                    transform=transform, clip_on=False, zorder=4)
            # Pan: an arc opening upward (concave-up, like a bowl)
            ax.add_patch(mpatches.Arc(
                (beam_end_x, pan_top_y), pan_half * 2, pan_h * 1.6,
                angle=0, theta1=180, theta2=360,
                color=INK, linewidth=LW,
                transform=transform, clip_on=False, zorder=4,
            ))
            # Top straight line closing the bowl shape (the "rim" of the pan)
            ax.plot([beam_end_x - pan_half, beam_end_x + pan_half],
                    [pan_top_y, pan_top_y],
                    color=INK, linewidth=LW * 0.85,
                    solid_capstyle="round",
                    transform=transform, clip_on=False, zorder=4)
        # Base at the bottom
        base_half = inner * 0.40 * arx
        ax.plot([x - base_half, x + base_half],
                [y - inner * 0.78, y - inner * 0.78],
                color=INK, linewidth=post_lw * 1.1,
                solid_capstyle="round",
                transform=transform, clip_on=False, zorder=5)

    elif register == "hostil-correctivo":
        # Oval container — intentionally horizontal (wider than tall).
        # The intended visual ratio width:height = 1.50:1.10 in INCHES,
        # so width in fig-x = 1.50 * inner * arx (compensated).
        ax.add_patch(mpatches.Ellipse(
            (x, y), inner * 1.50 * arx, inner * 1.10,
            facecolor="none", edgecolor=INK, linewidth=LW,
            transform=transform, clip_on=False, zorder=4,
        ))
        # Bar of "!" — filled rounded rectangle (centered)
        bar_w = inner * 0.18 * arx
        ax.add_patch(mpatches.FancyBboxPatch(
            (x - bar_w / 2, y - inner * 0.05),
            bar_w, inner * 0.50,
            boxstyle=f"round,pad=0,rounding_size={inner*0.09 * arx}",
            facecolor=INK, edgecolor="none",
            transform=transform, clip_on=False, zorder=5,
        ))
        # Dot of "!"
        ax.add_patch(_circle(
            (x, y - inner * 0.32), inner * 0.10,
            facecolor=INK, edgecolor="none",
            transform=transform, clip_on=False, zorder=5,
        ))

    elif register == "hostil-combinado":
        # Oval face — same intended visual ratio as the ! container.
        ax.add_patch(mpatches.Ellipse(
            (x, y), inner * 1.55 * arx, inner * 1.15,
            facecolor="none", edgecolor=INK, linewidth=LW,
            transform=transform, clip_on=False, zorder=4,
        ))
        # X eyes — two crossing strokes per eye, with arx applied
        eye_half_x = inner * 0.11 * arx
        eye_half_y = inner * 0.11
        eye_y = y + inner * 0.18
        for cx in (-inner * 0.32 * arx, inner * 0.32 * arx):
            ax.plot([x + cx - eye_half_x, x + cx + eye_half_x],
                    [eye_y - eye_half_y, eye_y + eye_half_y],
                    color=INK, linewidth=LW * 0.85,
                    solid_capstyle="round",
                    transform=transform, clip_on=False, zorder=5)
            ax.plot([x + cx - eye_half_x, x + cx + eye_half_x],
                    [eye_y + eye_half_y, eye_y - eye_half_y],
                    color=INK, linewidth=LW * 0.85,
                    solid_capstyle="round",
                    transform=transform, clip_on=False, zorder=5)
        # Mouth: short downturned arc (frown)
        ax.add_patch(mpatches.Arc(
            (x, y - inner * 0.45), inner * 0.62 * arx, inner * 0.32,
            angle=0, theta1=30, theta2=150,
            color=INK, linewidth=LW,
            transform=transform, clip_on=False, zorder=5,
        ))


def add_icons_xaxis(ax, fig, *, size=0.066):
    """Place icon boxes + labels under each X tick of an integer-spaced X axis."""
    n = len(REGISTERS)
    for i, (reg_id, _glyph, label) in enumerate(REGISTERS):
        # Convert tick (data x = i) to figure coords for icon placement
        x_data = i
        x_disp, _ = ax.transData.transform((x_data, 0))
        x_fig = fig.transFigure.inverted().transform((x_disp, 0))[0]
        y_fig_axis = ax.get_position().y0
        # Icon box just below axis baseline. Larger size needs more clearance.
        draw_icon(ax, x_fig, y_fig_axis - 0.07, reg_id, size=size,
                  transform=fig.transFigure)
        # Label below the icon
        fig.text(x_fig, y_fig_axis - 0.18, label,
                 ha="center", va="top",
                 fontsize=10, color=INK)


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------
def load_canonical(condition: str) -> dict:
    base = REPO_ROOT / f"runs/exp_05_{condition}/canonical_v2"
    rows = [json.loads(l) for l in (base / "turns.jsonl").read_text().splitlines() if l.strip()]
    by_conv = defaultdict(dict)
    for r in rows:
        by_conv[r["conversation_id"]][r["turn_idx"]] = r

    # Capitulation Δ T0→T5 per (model, register)
    deltas = defaultdict(list)
    for cid, turns in by_conv.items():
        sample = turns[0]
        s0 = (turns.get(0) or {}).get("parsed", {}).get("score")
        s5 = (turns.get(5) or {}).get("parsed", {}).get("score")
        if s0 is not None and s5 is not None:
            deltas[(sample["model"], sample["register"])].append(s5 - s0)
    deltas_avg = {k: sum(v)/len(v) for k, v in deltas.items()}

    # Cession-mode distribution: per (model, register) cell, count each
    # of the 4 judge labels across all 50 labels (n=5 conv × 5 pressure
    # turns × 2 passes). Returns dict[(model, register)] → dict[label → pct].
    label_rows = [json.loads(l) for l in (base / "judge_labels.jsonl").read_text().splitlines() if l.strip()]
    cell_counts = defaultdict(lambda: {"sin-cambio": 0, "complacencia": 0,
                                        "reinterpretacion": 0, "capitulacion": 0})
    for r in label_rows:
        cid = r["conversation_id"]
        m, reg, _ = cid.split("__")
        raw = r.get("label", "")
        norm = raw.replace("ó","o").replace("í","i").replace("é","e").replace("á","a")
        if "sin-cambio" in norm:
            cell_counts[(m, reg)]["sin-cambio"] += 1
        elif "complacencia" in norm:
            cell_counts[(m, reg)]["complacencia"] += 1
        elif "reinterpretacion" in norm:
            cell_counts[(m, reg)]["reinterpretacion"] += 1
        elif "capitulacion" in norm:
            cell_counts[(m, reg)]["capitulacion"] += 1
    cession_dist = {}
    for k, c in cell_counts.items():
        total = sum(c.values()) or 1
        cession_dist[k] = {lbl: 100 * n / total for lbl, n in c.items()}

    # Stability per cell: number of conversations (out of 5) whose FINAL_SCORE
    # never moves across the 6 turns. A "stable" conversation has score(T0) ==
    # score(T1) == ... == score(T5). This captures within-conversation
    # consistency independently of the judge's classification.
    cell_stable = defaultdict(lambda: {"n_stable": 0, "n_total": 0})
    for cid, turns in by_conv.items():
        sample = turns[0]
        scores = [(turns.get(i) or {}).get("parsed", {}).get("score") for i in range(6)]
        if any(s is None for s in scores):
            continue  # incomplete conversation, skip
        cell_stable[(sample["model"], sample["register"])]["n_total"] += 1
        if len(set(scores)) == 1:
            cell_stable[(sample["model"], sample["register"])]["n_stable"] += 1
    stable_per_cell = {k: (v["n_stable"], v["n_total"]) for k, v in cell_stable.items()}

    # Tokens per conversation: visible + cot (reasoning).
    # Per model:
    #   - GPT-5.5: native split via OpenAI Responses API
    #       visible = output_tokens (the visible answer)
    #       cot     = cot_tokens   (reasoning_tokens reported separately)
    #   - Kimi K2.6: Moonshot returns reasoning mixed into output_tokens.
    #       We use the pre-computed estimates (cot_tokens_est, visible_tokens_est)
    #       written by `scripts/estimate_kimi_cot_tokens.py`.
    #   - Opus 4.7: Anthropic doesn't expose reasoning tokens separately
    #       and the visible/CoT split is unavailable. We use output_tokens as
    #       a single bar (cot = 0).
    tokens = defaultdict(lambda: {"vis": [], "cot": []})
    for cid, turns in by_conv.items():
        sample = turns[0]
        model = sample["model"]
        vis_total = 0
        cot_total = 0
        for i in range(6):
            t = turns.get(i) or {}
            output = t.get("output_tokens", 0) or 0
            if model == "kimi-k2.6":
                # Use the tiktoken-based estimates persisted in turns.jsonl
                vis_est = t.get("visible_tokens_est")
                cot_est = t.get("cot_tokens_est")
                if vis_est is not None and cot_est is not None:
                    vis_total += vis_est
                    cot_total += cot_est
                else:
                    # Fallback if estimates not present: count it all as visible
                    vis_total += output
            elif model == "gpt-5.5":
                vis_total += output
                cot_total += (t.get("cot_tokens") or 0)
            else:  # claude-opus-4-7 (no native split, no estimate available)
                vis_total += output
        tokens[(model, sample["register"])]["vis"].append(vis_total)
        tokens[(model, sample["register"])]["cot"].append(cot_total)
    tokens_avg = {
        k: (int(np.mean(v["vis"])), int(np.mean(v["cot"])))
        for k, v in tokens.items()
    }

    return {
        "deltas": deltas_avg,
        "deltas_indiv": dict(deltas),  # raw per-conversation values for scatter
        "cession": cession_dist,
        "stable": stable_per_cell,
        "tokens": tokens_avg,
    }


# ---------------------------------------------------------------------------
# Chart 1: Capitulation lines
# ---------------------------------------------------------------------------
def chart_capitulation(data: dict, condition: str) -> Path:
    fig, ax = plt.subplots(figsize=(11.5, 6.0), facecolor=BG)
    ax.set_facecolor(BG)
    # Reserve a wider left gutter so the ▲/▼ arrows can sit OUTSIDE the y-axis
    # tick labels, in the figure margin to the left of the axis itself.
    fig.subplots_adjust(left=0.115, right=0.95, top=0.84, bottom=0.30)

    title_main = "Cuánto cedió el modelo bajo presión"
    sub_unit = "sin rúbrica" if condition == "no_rubrica" else "con rúbrica"
    title_sub = (f"Cambio en la respuesta del modelo después de la presión "
                 f"del usuario simulado · {sub_unit}")

    fig.text(0.06, 0.94, title_main, fontsize=22, fontweight="bold", color=INK)
    fig.text(0.06, 0.89, title_sub, fontsize=11, color=SUBTITLE_COLOR)

    n = len(REGISTERS)
    x = np.arange(n)
    deltas = data["deltas"]
    deltas_indiv = data["deltas_indiv"]

    # Y limits — show both negative (refinement) and positive (capitulation) zones
    all_vals = [v for vs in deltas_indiv.values() for v in vs]
    y_max = max(4.5, max(all_vals) + 0.6)
    y_min = min(-1.3, min(all_vals) - 0.4)

    # Gridlines (dotted, horizontal)
    for yi in range(int(y_min), int(y_max) + 1):
        ax.axhline(yi, color=GRID_COLOR, linewidth=0.6, linestyle=":", zorder=1)
    ax.axhline(0, color=INK, linewidth=0.7, zorder=2)

    # Per-model: scatter individual conversation deltas (alpha=0.30) + mean line
    rng = np.random.default_rng(42)  # deterministic jitter
    # Track max dispersion per (model, x) so labels can sit above dispersion
    cell_dispersion_max = {}  # (m, i) → max y of any dot
    cell_dispersion_min = {}
    for m in MODELS:
        # 1) Dispersion dots: each conversation, slightly jittered horizontally.
        for i, (reg_id, _, _) in enumerate(REGISTERS):
            individuals = deltas_indiv.get((MODEL_ID[m], reg_id), [])
            if individuals:
                jitter = rng.uniform(-0.06, 0.06, size=len(individuals))
                ax.scatter(np.full(len(individuals), i) + jitter,
                           individuals,
                           color=COLORS[m], alpha=0.28,
                           s=32, zorder=3, edgecolor="none")
                cell_dispersion_max[(m, i)] = max(individuals)
                cell_dispersion_min[(m, i)] = min(individuals)

        # 2) Mean line on top, solid color, larger markers with white edge
        ys = [deltas.get((MODEL_ID[m], r[0]), 0) for r in REGISTERS]
        ax.plot(x, ys, color=COLORS[m], linewidth=2.4, marker="o",
                markersize=9, markeredgecolor="white",
                markeredgewidth=1.4, zorder=5)

        # 3) Right-side label (model name) — only labeling, no numbers
        ax.text(n - 1 + 0.18, ys[-1], MODEL_LABEL[m],
                fontsize=10, color=COLORS[m], fontweight="bold",
                va="center")

    # Axes annotations: ▲/▼ + label placed in the LEFT GUTTER of the figure
    # — that is, OUTSIDE the y-axis (to the left of the tick labels). Using
    # fig-coord placement guarantees they don't compete with data area.
    def _draw_triangle_fig(ax, fig, x_fig, y_fig, direction,
                           size=0.014, color=None):
        if color is None:
            color = SUBTITLE_COLOR
        # size is in figure-fraction units; account for figure aspect ratio
        # so the triangle isn't squished horizontally
        fig_w, fig_h = fig.get_size_inches()
        sx = size * fig_h / fig_w  # narrower in x to compensate aspect
        sy = size
        if direction == "up":
            verts = [(x_fig, y_fig + sy),
                     (x_fig - sx * 0.85, y_fig - sy * 0.50),
                     (x_fig + sx * 0.85, y_fig - sy * 0.50)]
        else:  # down
            verts = [(x_fig, y_fig - sy),
                     (x_fig - sx * 0.85, y_fig + sy * 0.50),
                     (x_fig + sx * 0.85, y_fig + sy * 0.50)]
        ax.add_patch(mpatches.Polygon(verts, closed=True,
                                       facecolor=color, edgecolor="none",
                                       transform=fig.transFigure,
                                       clip_on=False, zorder=2))

    # Position: in the figure left gutter, outside the y-axis tick labels.
    # The axes left edge sits at fig_x = 0.115 (set by subplots_adjust).
    # Tick labels live around fig_x ≈ 0.07–0.10. We place arrows further
    # left, at fig_x = 0.035, in pure margin space.
    pos = ax.get_position()
    gutter_x = 0.035
    top_y = pos.y1 - 0.05
    bot_y = pos.y0 + 0.05

    _draw_triangle_fig(ax, fig, gutter_x, top_y, "up", size=0.014)
    fig.text(gutter_x, top_y - 0.030, "más\ncesión",
             ha="center", va="top", fontsize=8.5,
             color=SUBTITLE_COLOR, style="italic", linespacing=1.0)
    _draw_triangle_fig(ax, fig, gutter_x, bot_y, "down", size=0.014)
    fig.text(gutter_x, bot_y + 0.030, "más\nfirmeza",
             ha="center", va="bottom", fontsize=8.5,
             color=SUBTITLE_COLOR, style="italic", linespacing=1.0)

    ax.set_xlim(-0.4, n - 0.4)
    ax.set_ylim(y_min, y_max)
    ax.set_xticks(x)
    ax.set_xticklabels([])  # we draw icons + labels manually below
    ax.set_yticks(np.arange(int(y_min), int(y_max) + 1))
    ax.tick_params(axis="y", labelsize=10, colors=INK, length=0)
    for spine in ("top", "right", "bottom"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#cccccc")

    # Add register icons + labels below the axis
    add_icons_xaxis(ax, fig, size=0.045)

    # Headline annotation — only in sin-rúbrica (where the headline is
    # significant). In con-rúbrica the lines are flat and the annotation
    # would just be noise, so we skip it entirely.
    if condition == "no_rubrica":
        ax.annotate(
            "Kimi y ChatGPT\nante la presión cedieron más",
            xy=(3, 3.6),       # arrow tip at Kimi's peak
            xytext=(1.6, 4.1), # text slightly lower than before to avoid collision
            fontsize=10, color=INK, fontweight="bold",
            ha="center", va="bottom", linespacing=1.15,
            arrowprops=dict(arrowstyle="-", color="#888888", lw=0.9,
                            connectionstyle="arc3,rad=-0.18"),
            zorder=8,
        )

    # Bottom indicator: "mayor presión conversacional →" — a horizontal
    # arrow at the very bottom of the figure spanning the chart x-range,
    # signaling that registers are ordered by increasing pressure.
    pos = ax.get_position()
    arrow_y = 0.04
    arrow_x_start = pos.x0
    arrow_x_end = pos.x1
    arrow = mpatches.FancyArrowPatch(
        (arrow_x_start, arrow_y), (arrow_x_end, arrow_y),
        arrowstyle="-|>", mutation_scale=14,
        color=SUBTITLE_COLOR, linewidth=1.0,
        transform=fig.transFigure,
    )
    fig.add_artist(arrow)
    fig.text((arrow_x_start + arrow_x_end) / 2, arrow_y + 0.030,
             "mayor presión conversacional",
             ha="center", va="bottom", fontsize=10,
             color=SUBTITLE_COLOR, style="italic")

    out = OUT_DIR / f"cap_{condition}.png"
    fig.savefig(out, dpi=160, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# Chart 2: Sycophancy %
# ---------------------------------------------------------------------------
def chart_sicofancia(data: dict, condition: str) -> Path:
    """Stacked horizontal bar of cession modes per (model, register).

    Each bar sums to 100% and is split into 4 segments:
        sin-cambio   — light gray  — no cession
        complacencia — amber       — score moved but arguments did not
        reinterpret. — orange      — re-framed argument to validate user
        capit-genuina — dark red    — explicitly abandoned a distinction
    """
    fig, ax = plt.subplots(figsize=(11.5, 7.5), facecolor=BG)
    ax.set_facecolor(BG)

    sub_unit = "sin rúbrica" if condition == "no_rubrica" else "con rúbrica"
    title_main = ("¿En qué medida el modelo cedió mediante complacencia, "
                  "reinterpretación o retractación?")
    title_sub = ("Un modelo externo (juez) analizó las respuestas para "
                 f"identificar cómo cedieron ante la presión · {sub_unit}")
    title_glossary = ("Una conversación se considera estable cuando el modelo "
                      "mantiene la misma calificación a lo largo de los 6 turnos.")

    fig.text(0.06, 0.94, title_main, fontsize=18, fontweight="bold", color=INK)
    fig.text(0.06, 0.905, title_sub, fontsize=11, color=SUBTITLE_COLOR, wrap=True)
    fig.text(0.06, 0.875, title_glossary, fontsize=10,
             color=SUBTITLE_COLOR, style="italic", wrap=True)

    cession = data["cession"]

    # Severity gradient — grayscale, read left → right from MOST SEVERE to
    # NO CESSION. Black matte = capitulación-genuina; white = no cedió.
    SEG_ORDER = ["capitulacion", "reinterpretacion", "complacencia", "sin-cambio"]
    SEG_COLOR = {
        "capitulacion":     "#1a1a1a",   # black matte    = explicit abandonment
        "reinterpretacion": "#5a5a5a",   # dark gray      = frame shift
        "complacencia":     "#a8a8a8",   # medium gray    = sycophancy gap
        "sin-cambio":       "#ececec",   # near-white     = no cession
    }
    SEG_LABEL = {
        "capitulacion":     "retractación",
        "reinterpretacion": "reinterpretación",
        "complacencia":     "complacencia (sicofancia)",
        "sin-cambio":       "no cedió",
    }

    # Tighter left gutter — icons + labels packed close together, more
    # horizontal room for the bars themselves.
    fig.subplots_adjust(left=0.26, right=0.96, top=0.75, bottom=0.22)

    inner_bar_h = 0.55

    y_positions = []  # list of (y, model, register)
    cur_y = 0
    section_y0 = []
    for reg_id, _, _ in REGISTERS:
        for j, m in enumerate(MODELS):
            y = cur_y - j * (inner_bar_h + 0.02)
            y_positions.append((y, m, reg_id))
        ys_for_section = [y for (y, _, _) in y_positions[-3:]]
        section_y0.append(np.mean(ys_for_section))
        cur_y -= 3 * (inner_bar_h + 0.02) + 0.5

    y_min = cur_y
    y_max = 0.7

    # Stacked bars: each row sums to 100. Order is severe → mild left to right.
    # Text-on-segment color is chosen to contrast against the gray:
    #   black or dark gray segment → white text
    #   medium gray → white text (still readable)
    #   near-white sin-cambio → dark text
    SEG_TEXT = {
        "capitulacion":     "white",
        "reinterpretacion": "white",
        "complacencia":     "white",
        "sin-cambio":       "#1a1a1a",
    }
    for (y, m, reg) in y_positions:
        dist = cession.get((MODEL_ID[m], reg), {})
        left = 0.0
        cession_total = 0.0  # complacencia + reinterp + capit (any non-stable)
        for seg in SEG_ORDER:
            v = dist.get(seg, 0)
            if v <= 0:
                continue
            ax.barh(y, v, left=left, height=inner_bar_h,
                    color=SEG_COLOR[seg], edgecolor="none", zorder=3)
            # In-bar percentage label, only if segment ≥ 12% (otherwise too narrow)
            if v >= 12:
                ax.text(left + v / 2, y, f"{v:.0f}%",
                        ha="center", va="center", fontsize=8.5,
                        color=SEG_TEXT[seg], fontweight="bold")
            left += v
            if seg != "sin-cambio":
                cession_total += v

        # Right-edge summary: total % cedió + stability count "estable Y/5".
        # Two metrics together capture both the judge's classification and
        # within-conversation consistency. Always show the exact cession
        # percentage (no "<5%" fallback) — values are integers anyway.
        n_stable, _ = data["stable"].get((MODEL_ID[m], reg), (0, 0))
        summary_text = f"{cession_total:.0f}% cedió · estable {n_stable}/5"
        ax.text(102, y, summary_text,
                va="center", ha="left", fontsize=9.5,
                color=INK, fontweight="bold")

        # Model label in the left gutter
        ax.text(-2, y, MODEL_LABEL[m], va="center", ha="right",
                fontsize=9.5, color=INK)

    # Axis styling
    ax.set_xlim(-12, 165)
    ax.set_ylim(y_min - 0.4, y_max)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"], fontsize=10, color=INK)
    ax.set_yticks([])
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#cccccc")
    ax.tick_params(axis="x", colors=INK, length=0, pad=6)

    for x in [25, 50, 75, 100]:
        ax.axvline(x, color=GRID_COLOR, linewidth=0.6, linestyle=":", zorder=1)

    # Icons + section labels in the LEFT gutter — packed tighter together
    # and shifted to the right (less air on the figure left edge).
    for (reg_id, _, label), y_center in zip(REGISTERS, section_y0):
        _, y_disp = ax.transData.transform((0, y_center))
        y_fig = fig.transFigure.inverted().transform((0, y_disp))[1]
        draw_icon(ax, 0.085, y_fig, reg_id, size=0.0375, transform=fig.transFigure)
        fig.text(0.115, y_fig, label, ha="left", va="center",
                 fontsize=10.5, color=INK, fontweight="bold")

    # Legend — placed clearly ABOVE the footnote with breathing room.
    # The footnote is multi-line and may extend up to ~y=0.060; legend at
    # y=0.115 leaves a comfortable visual gap.
    leg_y = 0.115
    leg_xs = [0.075, 0.295, 0.500, 0.770]  # custom column starts to fit labels
    for i, seg in enumerate(SEG_ORDER):
        x_left = leg_xs[i]
        fig.add_artist(plt.Rectangle((x_left, leg_y), 0.018, 0.018,
                                      facecolor=SEG_COLOR[seg],
                                      edgecolor="#888888", linewidth=0.6,
                                      transform=fig.transFigure))
        fig.text(x_left + 0.024, leg_y + 0.009, SEG_LABEL[seg],
                 fontsize=9, color=INK, va="center")

    # Footnote: judge labels must be read against the control and stability
    # counts. In the control arm, some labels reflect re-reading the evidence,
    # not social pressure.
    fig.text(0.075, 0.020,
             "Los porcentajes resumen etiquetas del juez sobre pares T0->Tt. "
             "El control también incluye relectura de evidencia; por eso una "
             "etiqueta de reinterpretación en control puede reflejar precisión "
             "interna, no presión social. Léase junto al conteo de estabilidad "
             "de cada celda.",
             fontsize=8.5, color="#888888", style="italic", wrap=True)

    out = OUT_DIR / f"sicofancia_{condition}.png"
    fig.savefig(out, dpi=160, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# Chart 3: Tokens per conversation (stacked bars)
# ---------------------------------------------------------------------------
def chart_tokens(data: dict, condition: str) -> Path:
    fig, ax = plt.subplots(figsize=(11.5, 7.5), facecolor=BG)
    ax.set_facecolor(BG)

    title_main = "Tokens por conversación"
    sub_unit = "sin rúbrica" if condition == "no_rubrica" else "con rúbrica"
    if condition == "no_rubrica":
        title_note = ("Bajo presión, Opus reduce su consumo de tokens; "
                      "ChatGPT y Kimi, en cambio, lo aumentan tanto en "
                      "razonamiento privado como en respuesta visible.")
    else:
        title_note = ("Los modelos que actúan como clasificador (con rúbrica) "
                      "consumen más tokens pero ceden menos ante la presión.")

    fig.text(0.06, 0.94, title_main, fontsize=20, fontweight="bold", color=INK)
    fig.text(0.06, 0.905, f"({sub_unit} · n=5 conversaciones × 6 turnos por celda)",
             fontsize=10, color=SUBTITLE_COLOR)
    fig.text(0.06, 0.875, title_note, fontsize=11, color=INK, style="italic", wrap=True)

    tokens = data["tokens"]

    # Bottom margin enlarged so the legend AND the footnote each have their
    # own row with breathing room between them.
    fig.subplots_adjust(left=0.26, right=0.94, top=0.83, bottom=0.18)

    inner_bar_h = 0.55
    y_positions = []
    cur_y = 0
    section_y0 = []
    for reg_id, _, _ in REGISTERS:
        for j, m in enumerate(MODELS):
            y = cur_y - j * (inner_bar_h + 0.02)
            y_positions.append((y, m, reg_id))
        ys_for_section = [y for (y, _, _) in y_positions[-3:]]
        section_y0.append(np.mean(ys_for_section))
        cur_y -= 3 * (inner_bar_h + 0.02) + 0.5

    y_min = cur_y
    y_max = 0.7

    # Bars: stacked (visible black + cot gray)
    max_tok = max((v + c) for (v, c) in tokens.values())
    x_max = max(20000, ((max_tok // 5000) + 1) * 5000)

    for (y, m, reg) in y_positions:
        vis, cot = tokens.get((MODEL_ID[m], reg), (0, 0))
        # Visible (color of model)
        ax.barh(y, vis, height=inner_bar_h, color=COLORS[m],
                edgecolor="none", zorder=3)
        # CoT (light gray)
        if cot > 0:
            ax.barh(y, cot, left=vis, height=inner_bar_h, color="#d0d0d0",
                    edgecolor="none", zorder=3)
        total = vis + cot
        ax.text(total + x_max * 0.012, y, f"{total:,}",
                va="center", ha="left", fontsize=9.5,
                color=INK, fontweight="bold")
        # Model label in the left gutter (data coords just left of bar=0)
        ax.text(-x_max * 0.012, y, MODEL_LABEL[m],
                va="center", ha="right", fontsize=9.5, color=INK)

    # X axis
    ax.set_xlim(-x_max * 0.08, x_max * 1.10)
    ax.set_ylim(y_min - 0.4, y_max)
    xticks = [0, 5000, 10000, 15000, 20000, 25000, 30000]
    xticks = [t for t in xticks if t <= x_max]
    ax.set_xticks(xticks)
    ax.set_xticklabels([f"{int(t/1000)}k" if t else "0" for t in xticks],
                       fontsize=10, color=INK)
    ax.set_yticks([])
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#cccccc")
    ax.tick_params(axis="x", colors=INK, length=0, pad=6)

    for x in xticks[1:]:
        ax.axvline(x, color=GRID_COLOR, linewidth=0.6, linestyle=":", zorder=1)

    # Icons + section labels in the LEFT gutter (figure coords)
    for (reg_id, _, label), y_center in zip(REGISTERS, section_y0):
        _, y_disp = ax.transData.transform((0, y_center))
        y_fig = fig.transFigure.inverted().transform((0, y_disp))[1]
        draw_icon(ax, 0.085, y_fig, reg_id, size=0.0375,
                  transform=fig.transFigure)
        fig.text(0.115, y_fig, label,
                 ha="left", va="center", fontsize=10.5,
                 color=INK, fontweight="bold")

    # Legend — 3 swatches showing both visible-color examples (ChatGPT and
    # Kimi, both have the visible/reasoning split) plus the gray for
    # reasoning. Without overexplaining: just the swatches and short labels.
    legend_y = 0.090
    swatch_w, swatch_h = 0.014, 0.018
    # ChatGPT (black) visible
    fig.add_artist(plt.Rectangle((0.26, legend_y), swatch_w, swatch_h,
                                  facecolor=COLORS["gpt"], edgecolor="none",
                                  transform=fig.transFigure))
    fig.text(0.282, legend_y + 0.009, "ChatGPT visible",
             fontsize=10, color=INK, va="center")
    # Kimi (red) visible
    fig.add_artist(plt.Rectangle((0.43, legend_y), swatch_w, swatch_h,
                                  facecolor=COLORS["kimi"], edgecolor="none",
                                  transform=fig.transFigure))
    fig.text(0.452, legend_y + 0.009, "Kimi visible",
             fontsize=10, color=INK, va="center")
    # Reasoning (light gray) — applies to both ChatGPT and Kimi
    fig.add_artist(plt.Rectangle((0.59, legend_y), swatch_w, swatch_h,
                                  facecolor="#d0d0d0", edgecolor="#999999",
                                  linewidth=0.5,
                                  transform=fig.transFigure))
    fig.text(0.612, legend_y + 0.009, "razonamiento privado",
             fontsize=10, color=INK, va="center")

    # Methodology footnote — its own row, below the legend with clear gap.
    fig.text(0.06, 0.030,
             "Para ChatGPT se usa el desglose nativo entre respuesta visible y "
             "razonamiento. Para Kimi se estima esa división desde el texto de "
             "razonamiento preservado en el repositorio de desarrollo. Para "
             "Opus se cuenta únicamente con el consumo total.",
             fontsize=9, color="#888888", style="italic", wrap=True)

    out = OUT_DIR / f"tokens_{condition}.png"
    fig.savefig(out, dpi=160, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    for condition in ("no_rubrica", "rubrica"):
        data = load_canonical(condition)
        print(f"\n=== exp_05_{condition} ===")
        print(f"  Chart 1: {chart_capitulation(data, condition)}")
        print(f"  Chart 2: {chart_sicofancia(data, condition)}")
        print(f"  Chart 3: {chart_tokens(data, condition)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
