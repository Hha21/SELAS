#!/usr/bin/env python3
"""Bar chart of the mediation result: how much the decision changes under each condition.

    python plot_mediation.py DIR -o figures/interp/mediation

DIR holds the per-run summaries written by analyse_mediation.py, named after
their arm: k2-words-s<N>.json (rule 3 removed) and k2-words-no3-s<N>.json
(rule 3 added). Bars are the mean total-variation distance from the original
decision over seeds; dots are the seeds.
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics as st
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "controller_comparison"))
from plot import INK_PRIMARY, SERIES, _style  # noqa: E402

GROUPS = {"rule 3 removed from the\nwords runs": "k2-words-s",
          "rule 3 added to the\nno-rule-3 runs": "k2-words-no3-s"}
CONDS = [("total", "objective swapped,\nreasoning regenerated"),
         ("reason", "new reasoning only\n(objective unchanged)"),
         ("direct", "objective swapped,\noriginal reasoning kept")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    _style()
    fig, ax = plt.subplots(figsize=(7.0, 3.4))
    w = 0.26
    for gi, (gname, prefix) in enumerate(GROUPS.items()):
        files = [f for f in glob.glob(str(args.dir / "*.json"))
                 if Path(f).name.startswith(prefix) and (prefix != "k2-words-s" or "no3" not in f)]
        vals = {c: [list(json.load(open(f)).values())[0][f"tv_{c}"] for f in files] for c, _ in CONDS}
        for ci, (c, label) in enumerate(CONDS):
            m = st.mean(vals[c]); x = gi + (ci - 1) * w
            ax.bar(x, m, w * 0.92, color=SERIES[ci]["color"], label=label if gi == 0 else None, zorder=3)
            ax.scatter([x] * len(vals[c]), vals[c], s=10, color=INK_PRIMARY, zorder=4, linewidths=0)
            ax.annotate(f"{m:.2f}", (x, m), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=8, color=INK_PRIMARY)
    ax.set_xticks(range(len(GROUPS)), [f"{g} ({n} seeds)" for g, n in zip(GROUPS, (4, 3))])
    ax.set_ylabel("change in the decision\n(total variation from original)")
    ax.set_ylim(0, 1.0); ax.grid(axis="y", zorder=0); ax.tick_params(axis="x", length=0)
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    ax.set_title("The objective acts through the written reasoning (gemma-3-27b, CSF)",
                 fontsize=10, color=INK_PRIMARY)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out.with_suffix(".png"), bbox_inches="tight", facecolor="white")
    fig.savefig(args.out.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
