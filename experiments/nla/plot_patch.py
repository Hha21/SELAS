#!/usr/bin/env python3
"""Edit and patch: how often the choice moves to the option the edited NLA
explanation names, against the patch strength, for each direction.

Two panels (decisions to do nothing, decisions to act); one line per
direction (NLA edit, class-mean difference, random), with the run-resampled
95% interval as a band. The x axis is the patch size as a fraction of the
activation's norm (alpha 1 = keep what the explanation does not capture, swap
what it does). Several patch directories (e.g. with and without reasoning)
become rows, named by --label.

    python plot_patch.py PATCH_DIR [PATCH_DIR ...] [--label NAME ...] -o figures/nla/patch

Each PATCH_DIR holds analyse_patch.py's patch.json and edit_patch.py's
patched.jsonl.
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


def load(d: Path):
    """The measures and, per alpha, the median patch size relative to |h|."""
    M = json.loads((d / "patch.json").read_text())["measures"]
    base, rel = {}, defaultdict(list)
    rows = [json.loads(l) for l in (d / "patched.jsonl").read_text().splitlines() if l.strip()]
    for r in rows:
        if r["cond"] == "unpatched":
            base[(r["run"], r["period"])] = r["h_norm"]
    for r in rows:
        if r["cond"] == "nla":
            rel[r["alpha"]].append(r["delta_norm"] / base[(r["run"], r["period"])])
    alphas = sorted(rel)
    return M, alphas, [st.median(rel[a]) for a in alphas]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", type=Path, nargs="+", help="patch directories, one row each")
    ap.add_argument("--label", action="append", default=[], help="row name, one per directory")
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    if args.label and len(args.label) != len(args.dirs):
        ap.error("give one --label per directory")

    _style()
    nrow = len(args.dirs)
    fig, axes = plt.subplots(nrow, 2, sharey=True, squeeze=False, figsize=(7.2, 2.6 * nrow + 0.2))
    for r, d in enumerate(args.dirs):
        M, alphas, x = load(d)
        for ax, (split, title) in zip(axes[r], (("no_op", "decisions to do nothing"),
                                                 ("action", "decisions to act"))):
            for cond, label, color in DIRECTIONS:
                s = [M.get(f"{cond}|{a}|to target|{split}") for a in alphas]
                pts = [(xi, v) for xi, v in zip(x, s) if v]
                if not pts:
                    continue
                xs = [p[0] for p in pts]
                ax.fill_between(xs, [100 * p[1]["lo"] for p in pts], [100 * p[1]["hi"] for p in pts],
                                color=color, alpha=0.15, lw=0)
                ax.plot(xs, [100 * p[1]["rate"] for p in pts], marker="o", ms=3.5, color=color, lw=1.6,
                        label=label if (r == 0 and ax is axes[0, 0]) else None)
            ax.set_title(title, color=INK_PRIMARY, fontsize=9)
            ax.set_xticks(x)
            ax.set_xticklabels([f"{v:.2f}\n(α={a:g})" for v, a in zip(x, alphas)], fontsize=7)
            ax.grid(color=GRID)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
        axes[r, 0].set_ylabel("choice moves to the\nedited option (%)", color=INK_SECONDARY)
        if args.label:
            axes[r, 0].annotate(args.label[r], xy=(0, 0.5), xycoords="axes fraction", xytext=(-62, 0),
                                textcoords="offset points", rotation=90, ha="center", va="center",
                                fontsize=10, fontweight="bold", color=INK_PRIMARY)
    axes[0, 0].set_ylim(-3, 103)
    fig.supxlabel("patch size / |activation|  (layer 41, action cue)", color=INK_SECONDARY, fontsize=9)
    fig.legend(loc="upper center", bbox_to_anchor=(0.5, 1.0 + 0.04 / nrow), ncol=3, frameon=False,
               fontsize=8, labelcolor=INK_PRIMARY)
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.07 / nrow))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(args.out.with_suffix(f".{ext}"), dpi=200, bbox_inches="tight")
    print(f"wrote {args.out}.png and .pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
