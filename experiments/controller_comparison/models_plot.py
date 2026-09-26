#!/usr/bin/env python3
"""Utility per prompt configuration across models: does the pattern hold?

One row per prompt configuration, one sub-row per model, one dot per seed and
a bar at each model's mean. Colour is the model, from the reference palette in
fixed order; baselines are vertical lines. The question the figure answers is
whether the ordering of the rows is the same for every colour -- not which
model scores highest.

    python models_plot.py -o OUT \\
        --runs "gemma-3-27b=a.json" --runs "gemma-3-27b=b.json" --runs "Llama-3.3-70B=c.json" \\
        --arm "k2=no objective" --arm "k2-words=objective in words" \\
        --reference "do nothing=5101"

``--runs`` may repeat a model name to pool several runs.json files (e.g. one per
seed-set). Runs are grouped by arm, the run directory name before "-s<seed>".
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

from ladder_plot import _pair
from plot import GRID, INK_PRIMARY, INK_SECONDARY, SERIES, _style


def load(pairs: list[tuple[str, Path]]) -> dict[str, dict[str, list[tuple[int, float]]]]:
    per: dict[str, dict[str, list[tuple[int, float]]]] = defaultdict(lambda: defaultdict(list))
    for model, path in pairs:
        runs = json.loads(Path(path).read_text())
        runs = runs if isinstance(runs, list) else runs.get("runs", runs)
        for r in runs:
            if r.get("utility_seams2017a") is None:
                continue
            name = r["run_dir"].rstrip("/").split("/")[-1]
            arm, seed = name.rsplit("-s", 1)
            per[model][arm].append((int(seed), r["utility_seams2017a"]))
    return per


def plot(per, models: list[str], arms: list[tuple[str, str]], refs: list[tuple[str, float]],
         out: Path, title: str | None = None) -> None:
    _style()
    n = len(models)
    band = 0.8                                    # height of one prompt's block
    fig, ax = plt.subplots(figsize=(7.2, 0.28 * n * len(arms) + 0.3 * len(refs) + 1.6))
    for row, (arm, _) in enumerate(arms):
        for k, model in enumerate(models):
            vals = [u for _, u in sorted(per[model].get(arm, []))]
            if not vals:
                continue
            y = row + (k - (n - 1) / 2) * band / n
            color = SERIES[k % len(SERIES)]["color"]
            ax.scatter(vals, [y] * len(vals), s=16, color=color, alpha=0.8, zorder=3, linewidths=0,
                       label=model if row == 0 or not any(per[model].get(a) for a, _ in arms[:row]) else None)
            m = st.mean(vals)
            ax.plot([m, m], [y - 0.35 * band / n, y + 0.35 * band / n], color=color,
                    linewidth=1.8, zorder=4)
        if row:
            ax.axhline(row - 0.5, color=GRID, linewidth=0.8, zorder=0)
    step = 0.2
    for k, (name, v) in enumerate(sorted(refs, key=lambda r: r[1])):
        ax.axvline(v, color=INK_SECONDARY, linestyle=":", linewidth=0.9, zorder=1)
        ax.annotate(name, xy=(v, -0.62 - step * (len(refs) - 1 - k)), xytext=(3, 0),
                    textcoords="offset points", ha="left", va="center",
                    fontsize=7.5, color=INK_SECONDARY)
    ax.axvline(0, color=GRID, linewidth=1.0, zorder=0)
    ax.set_yticks(range(len(arms)), [label for _, label in arms])
    ax.set_ylim(len(arms) - 0.5, -0.5 - (step * len(refs) + 0.1 if refs else 0))
    ax.set_xlabel("utility (SWIM, SEAMS 2017A) — dots are seeds, bars are means")
    ax.grid(axis="x")
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=min(n, 3),
              fontsize=8, markerscale=1.4, handletextpad=0.3)
    if title:
        ax.set_title(title, fontsize=10, color=INK_PRIMARY, pad=8)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", facecolor="white")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    print(f"wrote {out.with_suffix('.png')} and {out.with_suffix('.pdf')}")


def table(per, models: list[str], arms: list[tuple[str, str]]) -> None:
    print(f"{'model':24s} " + " ".join(f"{label[:22]:>24s}" for _, label in arms))
    for model in models:
        cells = []
        for arm, _ in arms:
            vals = [u for _, u in sorted(per[model].get(arm, []))]
            if not vals:
                cells.append(f"{'—':>24s}")
            elif len(vals) == 1:
                cells.append(f"{vals[0]:>16,.0f} (n=1)  ")
            else:
                cells.append(f"{st.mean(vals):>10,.0f} ± {st.stdev(vals):>5,.0f} (n={len(vals)})")
        print(f"{model:24s} " + " ".join(cells))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--runs", action="append", required=True, type=_pair,
                    help="MODEL=runs.json; repeat a model to pool files")
    ap.add_argument("--arm", action="append", required=True, type=_pair,
                    help="ARM=LABEL, in the order to plot (top first)")
    ap.add_argument("--reference", action="append", default=[],
                    type=lambda t: _pair(t, float), help="NAME=UTILITY, drawn as a line")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()
    per = load(args.runs)
    models = list(dict.fromkeys(m for m, _ in args.runs))
    table(per, models, args.arm)
    plot(per, models, args.arm, args.reference, args.out, args.title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
