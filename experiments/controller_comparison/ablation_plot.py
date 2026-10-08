#!/usr/bin/env python3
"""The objective ablation: utility per model, objective stated or not, with
and without the elicited reasoning.

Two panels sharing the model rows: left the objective is stated (Part A's
``cot`` / ``direct``), right it is not (``cot-noobj`` / ``direct-noobj``: no
objective block and no utility lines). In each, one dot per run for each arm
and a bar at its mean, as in reasoning_plot.py; reference lines from
--reference (SWIM's PLA and Thallium) and --nothing. An arm with no runs
yet is marked "pending".

    python ablation_plot.py final_table.json -o figures/models/ablation \\
        --reference PLA=4089.09 --reference Thallium=4658.65

Reads the JSON final_table.py writes.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plot import GRID, INK_PRIMARY, INK_SECONDARY, SERIES, _style, draw_references, parse_reference
from reasoning_plot import ROWS

PANELS = [("objective stated", ("cot", "direct")),
          ("no objective", ("cot-noobj", "direct-noobj"))]
LABELS = ("with reasoning", "without reasoning")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("table", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--reference", action="append", default=[], metavar="NAME=VALUE",
                    help="a reference line, e.g. PLA=4089.09 (repeatable)")
    ap.add_argument("--nothing", type=float, default=None, help="utility of doing nothing")
    ap.add_argument("--title", default=None, help="optional figure title (e.g. for a preview)")
    args = ap.parse_args()
    T = json.loads(args.table.read_text())
    rows = [(k, lab) for k, lab in ROWS if k in T]

    _style()
    fig, axes = plt.subplots(1, 2, sharey=True, sharex=True,
                             figsize=(8.6, 0.42 * len(rows) + 1.4))
    for ax, (title, arms) in zip(axes, PANELS):
        for i, (key, _) in enumerate(rows):
            y0 = len(rows) - 1 - i
            for arm, label, off, style in zip(arms, LABELS, (0.14, -0.14), SERIES):
                u = (T[key].get(arm) or {}).get("utility") or []
                if not u:
                    ax.text(0.98, y0 + off, "pending", transform=ax.get_yaxis_transform(),
                            ha="right", va="center", fontsize=6.5, color=style["color"])
                    continue
                ax.scatter(u, [y0 + off] * len(u), s=16, color=style["color"], alpha=0.55,
                           edgecolor="none", zorder=3,
                           label=label if (i == 0 and ax is axes[0]) else None)
                m = st.mean(u)
                ax.plot([m, m], [y0 + off - 0.11, y0 + off + 0.11], color=style["color"], lw=2.2, zorder=4)
        refs = [parse_reference(r) for r in args.reference]
        if args.nothing is not None:
            refs.append(("do nothing", args.nothing))
        draw_references(ax, refs, len(rows) - 0.45)
        ax.set_title(title, color=INK_PRIMARY, pad=14)
        ax.grid(axis="x", color=GRID)
        ax.grid(axis="y", visible=False)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].set_yticks(range(len(rows)))
    axes[0].set_yticklabels([lab for _, lab in reversed(rows)])
    axes[0].set_ylim(-0.6, len(rows) - 0.1)
    fig.supxlabel("utility (SWIM, SEAMS 2017A); dots are runs, bars are means",
                  color=INK_SECONDARY, fontsize=9)
    fig.legend(loc="upper center", bbox_to_anchor=(0.55, 1.0), ncol=2, frameon=False, fontsize=8,
               labelcolor=INK_PRIMARY)
    if args.title:
        fig.suptitle(args.title, y=1.06, color="#b3261e", fontsize=10)
    if any(lab.endswith("*") for _, lab in rows):
        fig.text(0.01, -0.01, "* OpenRouter (the written letter); others vLLM on CSF (the scored letter)",
                 fontsize=7, color=INK_SECONDARY)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(args.out.with_suffix(f".{ext}"), dpi=200, bbox_inches="tight")
    print(f"wrote {args.out}.png and .pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
