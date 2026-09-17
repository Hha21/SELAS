#!/usr/bin/env python3
"""Four-panel comparison of two controllers driving SWIM.

Four stacked panels sharing one time axis, rather than fewer panels with more
axes: servers, dimmer, response time and cumulative utility have unrelated
scales, and putting any two of them on a shared y (or on twin y-axes) would
invent a comparison the data does not support.

Colour carries controller identity only, taken in fixed order from the reference
categorical palette (slot 1 blue, slot 2 orange -- a documented adjacent pair
that passes the CVD and normal-vision gates). Line style repeats that identity so
the figure survives greyscale printing and colour-vision deficiency, since a
paper figure has no hover layer to fall back on.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

# Reference categorical palette, slots 1-2, light mode.
SERIES = [
    {"color": "#2a78d6", "linestyle": "-",  "label": "Reactive"},
    {"color": "#eb6834", "linestyle": "--", "label": "LLM"},
]
INK_PRIMARY = "#1a1a19"
INK_SECONDARY = "#5c5b55"
GRID = "#e6e5e0"


def _style() -> None:
    plt.rcParams.update({
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 9,
        "axes.edgecolor": GRID,          # recessive axes
        "axes.labelcolor": INK_SECONDARY,
        "axes.linewidth": 0.8,
        "xtick.color": INK_SECONDARY,
        "ytick.color": INK_SECONDARY,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.frameon": False,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
    })


def _series_from(result: dict, key: str) -> tuple[list[float], list[float]]:
    pts = result.get("series", {}).get(key, [])
    return [t for t, _ in pts], [v for _, v in pts]


def plot(results: list[dict], out: Path, sla: float = 0.75,
         warmup: float = 900.0, title: str | None = None) -> None:
    _style()
    fig, axes = plt.subplots(4, 1, figsize=(7.0, 8.0), sharex=True,
                             gridspec_kw={"hspace": 0.18})
    ax_srv, ax_dim, ax_rt, ax_util = axes

    for result, style in zip(results, SERIES):
        label = result.get("label", style["label"])
        common = {"color": style["color"], "linestyle": style["linestyle"],
                  "linewidth": 2.0, "label": label}

        # Servers and dimmer are held between decisions, so they are steps, not
        # interpolated lines -- a slope between two periods would imply the
        # system passed through values it never took.
        t, v = _series_from(result, "active_servers")
        if t:
            ax_srv.plot(t, v, drawstyle="steps-post", **common)

        t, v = _series_from(result, "brownout_factor")
        if t:
            # SWIM records brownout; the controller's knob is the dimmer.
            ax_dim.plot(t, [1.0 - b for b in v], drawstyle="steps-post", **common)

        rt = result.get("response_time") or []
        if rt:
            ax_rt.plot([p[0] for p in rt], [p[1] for p in rt], **common)

        cum = result.get("utility_cumulative") or []
        if cum:
            ax_util.plot([p[0] for p in cum], [p[1] for p in cum], **common)
            # One direct label per series at its endpoint -- not a number on
            # every point.
            ax_util.annotate(f"{cum[-1][1]:,.0f}", xy=cum[-1],
                             xytext=(4, 0), textcoords="offset points",
                             va="center", fontsize=8, color=style["color"])

    ax_srv.set_ylabel("servers")
    ax_srv.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax_dim.set_ylabel("dimmer")
    ax_dim.set_ylim(-0.05, 1.05)
    ax_rt.set_ylabel("resp. time (s)")
    ax_util.set_ylabel("cum. utility")
    ax_util.set_xlabel("simulation time (s)")

    ax_rt.axhline(sla, color=INK_SECONDARY, linestyle=":", linewidth=1.0, zorder=0)
    ax_rt.annotate(f"SLA {sla:g}s", xy=(0.995, sla), xycoords=("axes fraction", "data"),
                   xytext=(0, 3), textcoords="offset points",
                   ha="right", va="bottom", fontsize=7.5, color=INK_SECONDARY)

    for ax in axes:
        ax.grid(True, axis="y", zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        if warmup:
            # Utility is scored only after the warmup period; marking it stops
            # the first minutes being read as part of the comparison.
            ax.axvline(warmup, color=GRID, linewidth=1.0, zorder=0)

    # On the bottom panel, just above the axis: on the top panel it landed
    # directly on the servers trace, which is a step line pinned to the top.
    ax_util.annotate("warm-up ends", xy=(warmup, 0.02), xycoords=("data", "axes fraction"),
                     xytext=(4, 0), textcoords="offset points",
                     ha="left", va="bottom", fontsize=7.5, color=INK_SECONDARY)

    handles, labels = ax_srv.get_legend_handles_labels()
    if not handles:
        handles, labels = ax_util.get_legend_handles_labels()
    if len(handles) >= 2:
        fig.legend(handles, labels, loc="upper center", ncol=len(handles),
                   bbox_to_anchor=(0.5, 0.965), fontsize=9)

    if title:
        fig.suptitle(title, y=0.99, fontsize=10, color=INK_PRIMARY)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", facecolor="white")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    print(f"wrote {out.with_suffix('.png')} and {out.with_suffix('.pdf')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results_json", type=Path,
                    help="output of collect.py -o (a list of run results)")
    ap.add_argument("-o", "--out", type=Path, default=Path("results/comparison"))
    ap.add_argument("--labels", nargs="*", default=None)
    ap.add_argument("--sla", type=float, default=0.75)
    ap.add_argument("--warmup", type=float, default=900.0)
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    results = json.loads(args.results_json.read_text())
    if args.labels:
        for r, lab in zip(results, args.labels):
            r["label"] = lab
    plot(results, args.out, sla=args.sla, warmup=args.warmup, title=args.title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
