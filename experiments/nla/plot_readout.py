#!/usr/bin/env python3
"""When is the action readable? Per action kind, the share of decisions a
cross-validated linear read-out recovers from the telemetry and prompt alone,
from the activation before any reasoning (P0_turn), and at the action cue.

    python plot_readout.py OUT/summary.json -o figures/interp/nla_readout

Reads the ``decodability`` block analyse_pilot.py writes.
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
from plot import GRID, INK_PRIMARY, INK_SECONDARY, SERIES, _style  # noqa: E402

SOURCES = [("telemetry + prompt", "telemetry and prompt only"),
           ("P0_turn", "activation, before any reasoning"),
           ("P_action", "activation, at the action cue")]
KINDS = [("no_op", "no_op"), ("dimmer", "set dimmer"), ("add_server", "add server"),
         ("remove_server", "remove server")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("summary", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    dec = json.loads(args.summary.read_text())["decodability"]

    _style()
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    offsets = [0.2, 0.0, -0.2]         # first legend entry on top
    for (key, label), off, style in zip(SOURCES, offsets, SERIES):
        ys = [len(KINDS) - 1 - r + off for r in range(len(KINDS))]
        xs = [dec[key]["recall"].get(k, 0.0) for k, _ in KINDS]
        ax.scatter(xs, ys, s=46, color=style["color"], edgecolor="white", linewidth=1.0,
                   zorder=3, label=label)
    ax.set_yticks(range(len(KINDS)))
    ax.set_yticklabels([f"{name}  (n={dec['classes'].get(k, 0)})" for k, name in reversed(KINDS)])
    ax.set_xlim(-0.03, 1.03)
    ax.set_xlabel("share of decisions of that kind recovered (cross-validated)", color=INK_SECONDARY)
    ax.grid(axis="x", color=GRID)
    ax.grid(axis="y", visible=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.22), ncol=3, frameon=False,
              fontsize=8, labelcolor=INK_PRIMARY, handletextpad=0.3, columnspacing=1.2)
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(args.out.with_suffix(f".{ext}"), dpi=200, bbox_inches="tight")
    print(f"wrote {args.out}.png and .pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
