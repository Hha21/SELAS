#!/usr/bin/env python3
"""What moves the decision? Share of decisions whose action changes under each
intervention, split into decisions to do nothing and decisions to act.

Three panels on one 0-100% axis, from pool_battery.py's JSON:
  (a) the reasoning perturbed, everything else kept (faithfulness);
  (b) one telemetry value pushed each way, with the recorded reasoning kept or
      regenerated from the edited telemetry (counterfactual, opposing pairs);
  (c) the objective removed, with the reasoning kept, regenerated, or
      regenerated but scored under the original objective (mediation).
Dots are pooled rates over the runs; whiskers are 95% intervals that
resample runs.

    python plot_battery.py battery.json -o figures/interp/battery
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller_comparison"))
from plot import GRID, INK_PRIMARY, INK_SECONDARY, _style  # noqa: E402

SPLITS = [("action", "decisions to act", "#2a78d6", "D"),
          ("no_op", "decisions to do nothing", "#1baf7a", "o")]
PANELS = [
    ("(a) reasoning perturbed", [
        ("faith/original", "none (control)"),
        ("faith/paraphrase", "reworded"),
        ("faith/corrupt", "SLA verdict negated"),
        ("faith/truncate_3", "conclusion removed"),
        ("faith/ablate", "reasoning removed"),
        ("faith/filler", "replaced by dots"),
        ("faith/shuffled", "another period's reasoning"),
    ]),
    ("(b) telemetry pushed each way", [
        ("cf_score/pair:rt_breached|rt_met", "response time, reasoning kept"),
        ("cf_generate/pair:rt_breached|rt_met", "response time, reasoning regenerated"),
        ("cf_score/pair:load_high|load_low", "load, reasoning kept"),
        ("cf_generate/pair:load_high|load_low", "load, reasoning regenerated"),
        ("cf_score/pair:spare_none|spare_ample", "spare capacity, reasoning kept"),
        ("cf_generate/pair:spare_none|spare_ample", "spare capacity, reasoning regenerated"),
    ]),
    ("(c) objective removed", [
        ("med_combined>none/direct", "reasoning kept"),
        ("med_combined>none/total", "reasoning regenerated"),
        ("med_combined>none/reason", "regenerated, scored with the objective"),
    ]),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("battery", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    M = json.loads(args.battery.read_text())["measures"]

    _style()
    heights = [len(rows) for _, rows in PANELS]
    fig, axes = plt.subplots(len(PANELS), 1, sharex=True, figsize=(6.6, 0.3 * sum(heights) + 1.6),
                             gridspec_kw={"height_ratios": heights, "hspace": 0.45})
    for ax, (title, rows) in zip(axes, PANELS):
        n = len(rows)
        for i, (key, label) in enumerate(rows):
            y = n - 1 - i
            for (split, slabel, color, marker), off in zip(SPLITS, (0.13, -0.13)):
                s = (M.get(key) or {}).get(split)
                if not s:
                    continue
                r, lo, hi = 100 * s["rate"], 100 * s["lo"], 100 * s["hi"]
                ax.plot([lo, hi], [y + off, y + off], color=color, lw=1.4, solid_capstyle="round", zorder=2)
                ax.scatter([r], [y + off], s=30, marker=marker, color=color, edgecolor="white",
                           linewidth=0.8, zorder=3, label=slabel if (ax is axes[0] and i == 0) else None)
        ax.set_yticks(range(n))
        ax.set_yticklabels([lab for _, lab in reversed(rows)], fontsize=8)
        ax.set_ylim(-0.6, n - 0.4)
        ax.set_title(title, loc="left", color=INK_PRIMARY, fontsize=9)
        ax.set_xlim(-2, 102)
        ax.grid(axis="x", color=GRID)
        ax.grid(axis="y", visible=False)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axes[-1].set_xlabel("decisions whose action changes (%)", color=INK_SECONDARY)
    fig.legend(loc="upper center", bbox_to_anchor=(0.6, 1.0), ncol=2, frameon=False, fontsize=8,
               labelcolor=INK_PRIMARY)
    fig.subplots_adjust(top=0.92)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(args.out.with_suffix(f".{ext}"), dpi=200, bbox_inches="tight")
    print(f"wrote {args.out}.png and .pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
