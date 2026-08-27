#!/usr/bin/env python
"""
Figure: does the NLA reconstruct runtime activations as well as the corpus it
was trained on?

Form: overlaid densities, one panel per metric (never a dual axis -- two metrics
on different scales get two panels). Distribution rather than a bar of means,
because the claim is about a *shift*, and a mean would hide the spread that
tells you whether the shift is real.

Encoding: hue = condition (categorical slots 1-2, blue/orange); line style =
real vs shuffled control. Identity is therefore never carried by colour alone,
which is what keeps it readable under CVD and in greyscale print.

The shuffled control is the point of the dashed curves: it is the same
activation scored against a *different* sample's explanation. The gap between
solid and dashed is how much the explanation actually says about this
activation; if that gap collapses on POLARIS, the AV is emitting plausible text
rather than reading the state.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
RES  = HERE / "results"

# Reference palette, categorical slots 1 and 2 (light mode).
# Reference palette, categorical slots 1-3 (light mode). Three series sits in
# the band where colour alone is comfortable; ordered in-distribution -> out.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#1a1a19", "#5c5b55", "#dcdcd6"

COND = {"fineweb":   ("FineWeb — NLA training corpus", BLUE),
        "ultrachat": ("UltraChat — chat format, general domain", AQUA),
        "polaris":   ("POLARIS — chat format, adaptation domain", ORANGE)}


def kde(x, grid, bw=None):
    """Gaussian KDE without scipy. Silverman bandwidth unless overridden."""
    x = np.asarray(x, float)
    n = len(x)
    if bw is None:
        sd = x.std(ddof=1)
        iqr = np.subtract(*np.percentile(x, [75, 25]))
        a = min(sd, iqr / 1.349) if iqr > 0 else sd
        bw = 0.9 * a * n ** (-1 / 5)
    bw = max(bw, 1e-3)
    z = (grid[:, None] - x[None, :]) / bw
    return np.exp(-0.5 * z ** 2).sum(axis=1) / (n * bw * np.sqrt(2 * np.pi))


def load(path):
    rows = list(csv.DictReader(path.open()))
    for r in rows:
        for k in ("cosine", "cosine_shuffled", "fve_own", "fve_pooled",
                  "fve_shuffled", "recon_scale_ratio"):
            if r.get(k) not in (None, ""):
                r[k] = float(r[k])
    return rows


def panel(ax, rows, key, title, xlabel, key_sh=None, zero_ref=False):
    vals = [r[key] for r in rows] + ([r[key_sh] for r in rows] if key_sh else [])
    lo, hi = min(vals), max(vals)
    pad = 0.08 * (hi - lo)
    grid = np.linspace(lo - pad, hi + pad, 400)

    for cond, (label, colour) in COND.items():
        sel = [r for r in rows if r["condition"] == cond]
        if not sel:
            continue
        real = np.array([r[key] for r in sel])
        ax.plot(grid, kde(real, grid), color=colour, lw=2, zorder=3, label=label)
        ax.plot([real.mean()], [0], marker="v", ms=7, color=colour,
                clip_on=False, zorder=4)
        if key_sh:
            sh = np.array([r[key_sh] for r in sel])
            ax.plot(grid, kde(sh, grid), color=colour, lw=1.4,
                    ls=(0, (4, 3)), alpha=0.7, zorder=2)

    if zero_ref:
        # FVE has its own interpretable origin, so it needs no shuffled curve:
        # 0 means "no better than predicting the corpus mean activation".
        ax.axvline(0, color=MUTED, lw=1.2, ls=(0, (2, 2)), zorder=1)
        ax.annotate("no better than\ncorpus mean", xy=(0, ax.get_ylim()[1] * 0.82),
                    xytext=(6, 0), textcoords="offset points",
                    fontsize=7.5, color=MUTED, va="top")

    ax.set_title(title, fontsize=10.5, color=INK, pad=8, loc="left")
    ax.set_xlabel(xlabel, fontsize=9.5, color=MUTED)
    ax.set_ylabel("density", fontsize=9.5, color=MUTED)
    ax.tick_params(labelsize=8.5, colors=MUTED, length=3)
    ax.grid(color=GRID, lw=0.6, alpha=0.7)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(GRID)
    ax.set_ylim(bottom=0)


def main():
    rows = load(RES / "samples.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    fig.patch.set_facecolor("white")

    panel(axes[0], rows, "cosine",
          "a. Reconstruction cosine", r"cosine$(z_\ell,\ \hat{z}_\ell)$",
          key_sh="cosine_shuffled")
    panel(axes[1], rows, "fve_pooled",
          "b. Fraction of variance explained", "FVE (pooled baseline)",
          zero_ref=True)

    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=c, lw=2, label=l) for l, c in COND.values()]
    handles.append(Line2D([], [], color=MUTED, lw=1.4, ls=(0, (4, 3)),
                          label="shuffled-explanation control"))
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False,
               fontsize=8.5, bbox_to_anchor=(0.5, -0.10), labelcolor=INK)

    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(RES / f"distribution_shift.{ext}", dpi=200,
                    bbox_inches="tight", facecolor="white")
    print(f"wrote {RES/'distribution_shift.png'} and .pdf\n")

    for cond, (label, _) in COND.items():
        sel = [r for r in rows if r["condition"] == cond]
        if not sel:
            continue
        c = np.array([r["cosine"] for r in sel])
        sh = np.array([r["cosine_shuffled"] for r in sel])
        f = np.array([r["fve_pooled"] for r in sel])
        sr = np.array([r.get("recon_scale_ratio", np.nan) for r in sel], float)
        print(f"{cond:10s} n={len(sel):3d}  cos {c.mean():+.3f}+-{c.std():.3f}  "
              f"shuf {sh.mean():+.3f}  delta {c.mean()-sh.mean():+.3f}  "
              f"FVE {f.mean():+.3f}+-{f.std():.3f}  scale {np.nanmean(sr):.2f}x")


if __name__ == "__main__":
    main()
