#!/usr/bin/env python3
"""Edit and patch: how often the choice moves to the option the edited NLA
explanation names, against the patch strength, for each direction.

Two panels (decisions to do nothing, decisions to act); one line per
direction (NLA edit, class-mean difference, random), with the run-resampled
95% interval as a band. The x axis is the patch size as a fraction of the
activation's norm (alpha 1 = keep what the explanation does not capture, swap
what it does).

    python plot_patch.py PATCH_DIR/patch.json PATCH_DIR/patched.jsonl -o figures/nla/patch
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller_comparison"))
from plot import GRID, INK_PRIMARY, INK_SECONDARY, _style  # noqa: E402

DIRECTIONS = [("nla", "NLA edit", "#2a78d6"), ("meandiff", "class-mean difference", "#1baf7a"),
              ("random", "random", "#8a8a85")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("summary", type=Path, help="patch.json from analyse_patch.py")
    ap.add_argument("patched", type=Path, help="patched.jsonl, for the patch size relative to |h|")
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    M = json.loads(args.summary.read_text())["measures"]

    base, rel = {}, defaultdict(list)
    rows = [json.loads(l) for l in args.patched.read_text().splitlines() if l.strip()]
    for r in rows:
        if r["cond"] == "unpatched":
            base[(r["run"], r["period"])] = r["h_norm"]
    for r in rows:
        if r["cond"] == "nla":
            rel[r["alpha"]].append(r["delta_norm"] / base[(r["run"], r["period"])])
    alphas = sorted(rel)
    x = [st.median(rel[a]) for a in alphas]

    _style()
    fig, axes = plt.subplots(1, 2, sharey=True, figsize=(7.2, 2.8))
    for ax, (split, title) in zip(axes, (("no_op", "decisions to do nothing"), ("action", "decisions to act"))):
        for cond, label, color in DIRECTIONS:
            s = [M.get(f"{cond}|{a}|to target|{split}") for a in alphas]
            pts = [(xi, v) for xi, v in zip(x, s) if v]
            if not pts:
                continue
            xs = [p[0] for p in pts]
            ax.fill_between(xs, [100 * p[1]["lo"] for p in pts], [100 * p[1]["hi"] for p in pts],
                            color=color, alpha=0.15, lw=0)
            ax.plot(xs, [100 * p[1]["rate"] for p in pts], marker="o", ms=3.5, color=color, lw=1.6,
                    label=label if ax is axes[0] else None)
        ax.set_title(title, color=INK_PRIMARY)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{v:.2f}\n(α={a:g})" for v, a in zip(x, alphas)], fontsize=7)
        ax.grid(color=GRID)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axes[0].set_ylabel("choice moves to the edited option (%)", color=INK_SECONDARY)
    axes[0].set_ylim(-3, 103)
    fig.supxlabel("patch size / |activation|  (layer 41, action cue)", color=INK_SECONDARY, fontsize=9)
    fig.legend(loc="upper center", bbox_to_anchor=(0.5, 1.04), ncol=3, frameon=False, fontsize=8,
               labelcolor=INK_PRIMARY)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(args.out.with_suffix(f".{ext}"), dpi=200, bbox_inches="tight")
    print(f"wrote {args.out}.png and .pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
