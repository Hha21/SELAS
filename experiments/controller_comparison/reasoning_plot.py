#!/usr/bin/env python3
"""Utility per model, with and without the elicited reasoning.

One row per model (by family and size; OpenRouter models last), one dot per
run for each arm, a bar at each arm's mean. Reference lines: any given with
--reference (SWIM's PLA and Thallium), doing nothing, and the static
configuration (dimmer 1.0, four servers, held) when given.

    python reasoning_plot.py final_table.json -o figures/models/reasoning \\
        --reference PLA=4089.09 --reference Thallium=4658.65 [--nothing 5101] [--static 12892]

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

ROWS = [  # (table key, label)
    ("gemma4b (CSF)", "gemma-3 4B"), ("gemma12b (CSF)", "gemma-3 12B"), ("gemma27b (CSF)", "gemma-3 27B"),
    ("qwen7b (CSF)", "Qwen2.5 7B"), ("qwen14b (CSF)", "Qwen2.5 14B"), ("qwen32b (CSF)", "Qwen2.5 32B"),
    ("llama8b (CSF)", "Llama-3.1 8B"), ("llama70b (CSF)", "Llama-3.3 70B"),
    ("gpt4omini (OpenRouter)", "gpt-4o-mini*"), ("gpt4o (OpenRouter)", "gpt-4o*"),
    ("deepseekv3 (OpenRouter)", "DeepSeek-V3*"),
]
ARMS = [("cot", "with reasoning"), ("direct", "without reasoning")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("table", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--reference", action="append", default=[], metavar="NAME=VALUE",
                    help="a reference line, e.g. PLA=4089.09 (repeatable)")
    ap.add_argument("--nothing", type=float, default=None, help="utility of doing nothing")
    ap.add_argument("--static", type=float, default=None, help="utility of the static configuration")
    args = ap.parse_args()
    T = json.loads(args.table.read_text())
    rows = [(k, lab) for k, lab in ROWS if k in T]

    _style()
    fig, ax = plt.subplots(figsize=(7.4, 0.42 * len(rows) + 1.3))
    for i, (key, _) in enumerate(rows):
        y0 = len(rows) - 1 - i
        for (arm, label), off, style in zip(ARMS, (0.14, -0.14), SERIES):
            u = T[key][arm]["utility"]
            ax.scatter(u, [y0 + off] * len(u), s=16, color=style["color"], alpha=0.55,
                       edgecolor="none", zorder=3, label=label if i == 0 else None)
            m = st.mean(u)
            ax.plot([m, m], [y0 + off - 0.11, y0 + off + 0.11], color=style["color"], lw=2.2, zorder=4)
    refs = [parse_reference(r) for r in args.reference]
    refs += [(name, x) for name, x in (("do nothing", args.nothing), ("static", args.static)) if x is not None]
    draw_references(ax, refs, len(rows) - 0.45)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([lab for _, lab in reversed(rows)])
    ax.set_ylim(-0.6, len(rows) - 0.1)
    ax.set_xlabel("utility (SWIM, SEAMS 2017A); dots are runs, bars are means", color=INK_SECONDARY)
    ax.grid(axis="x", color=GRID)
    ax.grid(axis="y", visible=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, frameon=False, fontsize=8,
              labelcolor=INK_PRIMARY)
    if any(lab.endswith("*") for _, lab in rows):
        fig.text(0.01, 0.005, "* OpenRouter (the written letter); others vLLM on CSF (the scored letter)",
                 fontsize=7, color=INK_SECONDARY)
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(args.out.with_suffix(f".{ext}"), dpi=200, bbox_inches="tight")
    print(f"wrote {args.out}.png and .pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
