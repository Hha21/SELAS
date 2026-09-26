#!/usr/bin/env python3
"""Utility per prompt configuration, one dot per seed, baselines as lines.

The companion to plot.py's time series: that figure shows *how* each prompt
behaves on one seed; this one shows the outcome on every seed, so the spread
is visible next to the differences between configurations. Rows run in the
order the prompt is built up, top to bottom. Utility is SWIM's reported
SEAMS 2017A figure (``utility_seams2017a`` from collect.py).

    python ladder_plot.py RUNS.json [RUNS.json ...] -o OUT \\
        --arm "k0=no examples, no objective" --arm "k2=2 examples" ... \\
        --reference "do nothing=5101" --reference "PLA=4089"

Runs are grouped by arm, the part of the run directory name before "-s<seed>".
"""

from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plot import GRID, INK_PRIMARY, INK_SECONDARY, SERIES, _style

DOT = SERIES[0]["color"]


def load(paths: list[Path]) -> dict[str, list[tuple[int, float]]]:
    per: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for path in paths:
        runs = json.loads(path.read_text())
        runs = runs if isinstance(runs, list) else runs.get("runs", runs)
        for r in runs:
            name = r["run_dir"].rstrip("/").split("/")[-1]
            arm, seed = name.rsplit("-s", 1)
            per[arm].append((int(seed), r["utility_seams2017a"]))
    return per


def plot(per: dict, arms: list[tuple[str, str]], refs: list[tuple[str, float]],
         out: Path, title: str | None = None) -> None:
    _style()
    fig, ax = plt.subplots(figsize=(7.0, 0.45 * len(arms) + 0.3 * len(refs) + 1.1))
    for y, (arm, _) in enumerate(arms):
        vals = [u for _, u in sorted(per[arm])]
        ax.scatter(vals, [y] * len(vals), s=22, color=DOT, alpha=0.75, zorder=3, linewidths=0)
        m = st.mean(vals)
        ax.plot([m, m], [y - 0.28, y + 0.28], color=INK_PRIMARY, linewidth=1.6, zorder=4)
        sd = f" ± {st.stdev(vals):,.0f}" if len(vals) > 1 else ""
        ax.annotate(f"{m:,.0f}{sd}  (n={len(vals)})", xy=(1.0, y), xycoords=("axes fraction", "data"),
                    xytext=(6, 0), textcoords="offset points", va="center", fontsize=8,
                    color=INK_PRIMARY)
    # Reference labels sit in a band above the first row, one step lower per
    # line in order of value, so baselines a few hundred apart (PLA, Thallium,
    # doing nothing) do not print on top of one another.
    step = 0.32
    for k, (name, v) in enumerate(sorted(refs, key=lambda r: r[1])):
        ax.axvline(v, color=INK_SECONDARY, linestyle=":", linewidth=0.9, zorder=1)
        ax.annotate(name, xy=(v, -0.62 - step * (len(refs) - 1 - k)), xytext=(3, 0),
                    textcoords="offset points", ha="left", va="center",
                    fontsize=7.5, color=INK_SECONDARY)
    ax.axvline(0, color=GRID, linewidth=1.0, zorder=0)
    ax.set_yticks(range(len(arms)), [label for _, label in arms])
    ax.set_ylim(len(arms) - 0.5, -0.5 - (step * len(refs) + 0.1 if refs else 0))
    ax.set_xlabel("utility (SWIM, SEAMS 2017A) — dots are seeds, bar is the mean")
    ax.grid(axis="x")
    ax.tick_params(axis="y", length=0)
    if title:
        ax.set_title(title, fontsize=10, color=INK_PRIMARY, pad=8)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", facecolor="white")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    print(f"wrote {out.with_suffix('.png')} and {out.with_suffix('.pdf')}")


def _pair(text: str, kind=str) -> tuple[str, object]:
    key, _, value = text.partition("=")
    if not value:
        raise argparse.ArgumentTypeError(f"expected NAME=VALUE, got {text!r}")
    return key.strip(), kind(value)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", type=Path, nargs="+", help="runs.json files from collect.py")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--arm", action="append", required=True, type=_pair,
                    help="ARM=LABEL, in the order to plot (top first)")
    ap.add_argument("--reference", action="append", default=[],
                    type=lambda t: _pair(t, float), help="NAME=UTILITY, drawn as a line")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()
    per = load(args.runs)
    missing = [a for a, _ in args.arm if a not in per]
    if missing:
        ap.error(f"no runs for {missing}; found {sorted(per)}")
    plot(per, args.arm, args.reference, args.out, args.title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
