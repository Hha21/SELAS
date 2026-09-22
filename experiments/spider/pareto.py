#!/usr/bin/env python3
"""Utility against interpretability, one point per prompting configuration.

The y axis is what the controller achieved: SWIM's own utility, accumulated
over the run after the warm-up. Nothing about it is our construction -- it is
the managed system's score for the commands it was sent, which is the thing a
QA benchmark cannot offer and the reason this setting is worth the trouble.

The x axis is the interpretability aggregate, grouped before averaging:

    Robustness      = robustness
    Faithfulness    = mean(sensitivity, mistakes, counterfactual)
    Utility         = simulatability
    Aggregate       = mean of the three

Grouped rather than a flat mean over five axes, following the source protocol's
three-axis structure. A flat mean would weight faithfulness three times as
heavily as the other two for no reason beyond its having more sub-measures.

Two kinds of series, and they are not comparable:

  points  configurations that produce an explanation. Each has a full set of
          axes and a place on the plane.
  lines   configurations that do not. `none` writes no reasoning, so four of
          the five axes are undefined -- there is nothing to perturb and no
          explanation to give a reader. It is drawn as a horizontal reference:
          the utility available with nothing explained. The reactive rule is
          the same, for a controller that is not a model at all.

Reading the plane against those lines is the point. A configuration below the
`none` line is paying utility for its explanation; one above it is not. The
frontier is drawn through the non-dominated points, but with a handful of
configurations it is a reading aid rather than a result -- the lines are what
carry the argument.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spider import AXES, axes_for  # noqa: E402

INK_PRIMARY = "#1a1a19"
INK_SECONDARY = "#5c5b55"
GRID = "#e6e5e0"
POINT = "#2a78d6"
FRONTIER = "#eb6834"
REFERENCE = "#5c5b55"

GROUPS = {
    "Robustness": ["Robustness"],
    "Faithfulness": ["Sensitivity", "Mistakes", "Counterfactual"],
    "Utility": ["Simulatability"],
}


def aggregate(vals: dict[str, float | None]) -> tuple[float | None, dict, list[str]]:
    """Group, average within groups, then average the groups."""
    group_means, missing = {}, []
    for name, members in GROUPS.items():
        got = [vals[m] for m in members if vals.get(m) is not None]
        missing += [m for m in members if vals.get(m) is None]
        group_means[name] = sum(got) / len(got) if got else None
    have = [v for v in group_means.values() if v is not None]
    return (sum(have) / len(have) if len(have) == len(GROUPS) else None,
            group_means, missing)


def load_utility(run: Path) -> dict[str, float]:
    f = run / "runs.json"
    if not f.exists():
        raise SystemExit(f"no runs.json in {run}; collect.py has not run")
    out = {}
    for r in json.loads(f.read_text()):
        out[Path(r["run_dir"]).name] = float(r["utility_total"])
    return out


def frontier(points: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Non-dominated: nothing is both more interpretable and higher utility."""
    out = []
    for p in sorted(points, key=lambda p: (-p[0], -p[1])):
        if not out or p[1] > out[-1][1]:
            out.append(p)
    return sorted(out, key=lambda p: p[0])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path, help="a sweep run directory")
    ap.add_argument("--reference", nargs="*", default=["none", "reactive", "null"],
                    help="arms drawn as horizontal lines rather than points")
    ap.add_argument("--pool", choices=["ACTIVE", "all"], default="ACTIVE")
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()

    out = args.out or (args.run / "pareto")
    utility = load_utility(args.run)

    points, references, skipped = [], [], []
    for arm, u in sorted(utility.items()):
        if arm in args.reference:
            references.append((arm, u))
            continue
        vals, _missing = axes_for(args.run / arm, args.pool)
        agg, groups, missing = aggregate(vals)
        if agg is None:
            skipped.append((arm, missing))
            continue
        points.append((agg, u, arm, groups))

    width = max([len(a) for a in utility] + [8]) + 2
    print(f"pool: {args.pool} decisions\n")
    print(f"{'arm':<{width}} {'utility':>10} {'Robust':>8} {'Faith':>8} "
          f"{'Util':>8} {'Aggregate':>10}")
    print("-" * (width + 46))
    for agg, u, arm, groups in sorted(points, key=lambda p: -p[1]):
        g = [groups[k] for k in GROUPS]
        print(f"{arm:<{width}} {u:>10.1f} " + " ".join(f"{v:>8.3f}" for v in g)
              + f" {agg:>10.3f}")
    for arm, u in sorted(references, key=lambda r: -r[1]):
        print(f"{arm:<{width}} {u:>10.1f} {'(reference line -- no explanation)':>44}")
    for arm, missing in skipped:
        print(f"{arm:<{width}} {'-':>10}   not yet measured: {', '.join(sorted(set(missing)))}")

    if not points:
        raise SystemExit("\nno arm has a complete set of axes yet; "
                         "run replay_all.sbatch first")

    fig, ax = plt.subplots(figsize=(6.6, 5.0))
    front = frontier([(a, u, n) for a, u, n, _ in points])
    if len(front) > 1:
        ax.plot([p[0] for p in front], [p[1] for p in front],
                color=FRONTIER, linewidth=1.4, linestyle="--", zorder=2,
                label="frontier")

    ax.scatter([p[0] for p in points], [p[1] for p in points],
               s=70, color=POINT, zorder=3, edgecolor="white", linewidth=1.2)
    for agg, u, arm, _g in points:
        ax.annotate(arm, xy=(agg, u), xytext=(6, 4), textcoords="offset points",
                    fontsize=9, color=INK_PRIMARY)

    for arm, u in references:
        ax.axhline(u, color=REFERENCE, linewidth=1.0, linestyle=":", zorder=1)
        ax.annotate(f"{arm} (no explanation)", xy=(0.01, u),
                    xycoords=("axes fraction", "data"),
                    xytext=(0, 3), textcoords="offset points",
                    fontsize=8, color=REFERENCE, va="bottom")

    ax.set_xlabel("interpretability (aggregate of the three axes)", color=INK_SECONDARY)
    ax.set_ylabel("utility realised in SWIM", color=INK_SECONDARY)
    ax.set_xlim(0, 1)
    ax.grid(True, color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_SECONDARY, labelsize=8)
    ax.set_title("What does an explanation cost?", color=INK_PRIMARY, fontsize=11)
    if len(front) > 1:
        ax.legend(frameon=False, fontsize=8, loc="lower left")

    fig.tight_layout()
    for suffix in (".png", ".pdf"):
        fig.savefig(out.with_suffix(suffix), dpi=200, bbox_inches="tight",
                    pad_inches=0.25, facecolor="white")
    payload = {
        "pool": args.pool,
        "points": [{"arm": n, "utility": u, "aggregate": a, "groups": g}
                   for a, u, n, g in points],
        "references": [{"arm": n, "utility": u} for n, u in references],
        "frontier": [n for _a, _u, n in front],
    }
    out.with_suffix(".json").write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nwrote {out.with_suffix('.png')}, {out.with_suffix('.pdf')} "
          f"and {out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
