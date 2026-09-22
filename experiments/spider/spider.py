#!/usr/bin/env python3
"""Assemble the interpretability axes into one figure.

Each axis is a measurement made elsewhere, rescaled so that 1 is the
interpretable end and 0 is not, and all of them are read on the ACTIVE
decisions. That restriction is not cosmetic: 85 of 105 periods are ``no_op``,
a decision to do nothing survives almost any perturbation, and pooling the two
reports the base rate of inaction on every axis at once.

    Robustness        1 - flip(paraphrase)
                      The same reasoning reworded should reach the same action.
                      A decision that moves was reading surface form.

    Sensitivity       flip(ablate)
                      Removing the reasoning should change the action. If it
                      does not, the reasoning was not load-bearing and nothing
                      else on this chart is about the decision.

    Mistakes          flip(corrupt_open)
                      Negating the SLA premise and removing the stated
                      conclusion should change the action. The adding-mistakes
                      test; ``corrupt`` alone leaves the conclusion to copy.

    Counterfactual    1 - CF-UF
                      Editing the telemetry in opposing directions should move
                      the decision the corresponding way.

    Simulatability    (acc(premises) - acc(state)) rescaled to [0, 1]
                      How much a second model's ability to predict the action
                      improves when given the reasoning without its conclusion.

Two controls bracket the scale rather than sitting on it. ``original`` must be
0 -- rescoring an unmodified decision reproduces it -- and ``shuffled`` is the
ceiling, since a decision that moves just as much under someone else's
reasoning is not being driven by its own. Both are printed, and a run where
they are not at their expected ends is reported before the chart is drawn.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Reference categorical palette, slots 1-3, light mode, taken in fixed order.
# Line style repeats identity so the figure survives greyscale printing and
# colour-vision deficiency, since a paper figure has no hover layer.
SERIES = [
    {"color": "#2a78d6", "linestyle": "-"},
    {"color": "#eb6834", "linestyle": "--"},
    {"color": "#1baf7a", "linestyle": "-."},
    {"color": "#8f6bd1", "linestyle": ":"},
]
INK_PRIMARY = "#1a1a19"
INK_SECONDARY = "#5c5b55"
GRID = "#e6e5e0"

AXES = ["Robustness", "Sensitivity", "Mistakes", "Counterfactual", "Simulatability"]


def _flip(faith: dict, arm: str, pool: str) -> float | None:
    key = "flip_active" if pool == "ACTIVE" else "flip_rate"
    v = faith.get(arm, {}).get(key)
    return None if v is None else float(v)


def axes_for(run: Path, pool: str = "ACTIVE",
             simulator: str | None = None) -> tuple[dict, list[str]]:
    """Read one run directory into axis values and whatever could not be read."""
    vals: dict[str, float | None] = dict.fromkeys(AXES)
    missing: list[str] = []

    f = run / "faithfulness.json"
    faith = json.loads(f.read_text()) if f.exists() else {}
    if faith:
        par, abl, cor = (_flip(faith, a, pool)
                         for a in ("paraphrase", "ablate", "corrupt_open"))
        vals["Robustness"] = None if par is None else 1.0 - par
        vals["Sensitivity"] = abl
        vals["Mistakes"] = cor
    else:
        missing.append("faithfulness.json")

    # Average over the students, not the ceiling: the question is whether a
    # reader can follow the reasoning, and the controller reading its own is a
    # bound on the measurement rather than an instance of it.
    sims = sorted(p for p in run.glob("simulatability_*.json")
                  if "ceiling" not in p.name
                  and (simulator is None or simulator in p.name))
    if sims:
        got = []
        for p in sims:
            d = json.loads(p.read_text()).get("las", {}).get(pool, {})
            if d.get("simulatability") is not None:
                got.append(float(d["simulatability"]))
        if got:
            vals["Simulatability"] = sum(got) / len(got)
    else:
        missing.append("simulatability_*.json")

    # The generate mode is the counterfactual proper; score mode holds the
    # written reasoning and is a different question, so it is not a fallback.
    cf = run / "counterfactual_generate.json"
    if cf.exists():
        d = json.loads(cf.read_text())
        pairs = d.get("pairs", {})
        if pairs:
            vals["Counterfactual"] = sum(
                v["correct_rate"] for v in pairs.values()) / len(pairs)
    else:
        missing.append("counterfactual_generate.json")

    return vals, missing


def controls(run: Path, pool: str) -> dict[str, float | None]:
    f = run / "faithfulness.json"
    if not f.exists():
        return {}
    faith = json.loads(f.read_text())
    return {"original": _flip(faith, "original", pool),
            "shuffled": _flip(faith, "shuffled", pool)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--labels", nargs="*", default=None)
    ap.add_argument("--pool", choices=["ACTIVE", "all"], default="ACTIVE")
    ap.add_argument("--simulator", default=None,
                    help="substring selecting one simulator; default averages all students")
    ap.add_argument("-o", "--out", type=Path, default=Path("spider.png"))
    args = ap.parse_args()

    labels = args.labels or [r.name for r in args.runs]
    if len(labels) != len(args.runs):
        raise SystemExit(f"{len(labels)} labels for {len(args.runs)} runs")

    series = []
    for run, label in zip(args.runs, labels):
        vals, missing = axes_for(run, args.pool, args.simulator)
        ctl = controls(run, args.pool)
        series.append((label, vals, missing, ctl))

    width = max(len(a) for a in AXES) + 2
    print(f"pool: {args.pool} decisions\n")
    print(f"{'axis':<{width}}" + "".join(f"{l:>16}" for l in labels))
    print("-" * (width + 16 * len(labels)))
    for ax in AXES:
        row = "".join(
            f"{'-':>16}" if v[1][ax] is None else f"{v[1][ax]:>16.3f}"
            for v in series)
        print(f"{ax:<{width}}" + row)
    print()
    for label, _v, missing, ctl in series:
        if ctl:
            print(f"{label}: control original {ctl['original']:.3f} (expect 0.000), "
                  f"shuffled {ctl['shuffled']:.3f} (ceiling)")
            if ctl["original"] and ctl["original"] > 0.05:
                print(f"  WARNING: {label} control arm moved; the axes below it "
                      f"are not interpretable")
        if missing:
            print(f"{label}: not yet measured -> {', '.join(missing)}")

    # Draw only the axes at least one series has, so a pending measurement
    # leaves a smaller chart rather than a polygon collapsed towards the centre
    # on an axis that was never run.
    drawn = [a for a in AXES if any(s[1][a] is not None for s in series)]
    if not drawn:
        raise SystemExit("nothing to plot")
    if len(drawn) < len(AXES):
        print(f"\nplotting {len(drawn)} of {len(AXES)} axes; "
              f"omitted: {', '.join(a for a in AXES if a not in drawn)}")

    ang = np.linspace(0, 2 * np.pi, len(drawn), endpoint=False).tolist()
    ang += ang[:1]
    fig, ax = plt.subplots(figsize=(6.2, 6.2), subplot_kw={"polar": True})
    for i, (label, vals, _m, _c) in enumerate(series):
        style = SERIES[i % len(SERIES)]
        # A missing axis is carried at 0 with the label already flagged above;
        # a gap in a closed polygon would read as a value.
        v = [vals[a] if vals[a] is not None else 0.0 for a in drawn]
        v += v[:1]
        ax.plot(ang, v, linewidth=1.8, label=label, **style)
        ax.fill(ang, v, color=style["color"], alpha=0.12)

    ax.set_xticks(ang[:-1])
    ax.set_xticklabels(drawn, color=INK_PRIMARY, fontsize=10)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"],
                       color=INK_SECONDARY, fontsize=8)
    ax.tick_params(pad=8)
    ax.grid(color=GRID, linewidth=0.8)
    ax.spines["polar"].set_color(GRID)
    ax.set_title(f"Interpretability of the controller's reasoning\n"
                 f"({args.pool} decisions, higher is more interpretable)",
                 color=INK_PRIMARY, fontsize=11, pad=24)
    if len(series) > 1:
        ax.legend(loc="upper right", bbox_to_anchor=(1.28, 1.12), frameon=False,
                  fontsize=9, labelcolor=INK_PRIMARY)
    fig.tight_layout()
    for suffix in (".png", ".pdf"):
        fig.savefig(args.out.with_suffix(suffix), dpi=200, bbox_inches="tight")
    print(f"\nwrote {args.out.with_suffix('.png')} and {args.out.with_suffix('.pdf')}")

    payload = {"pool": args.pool, "axes": drawn,
               "series": {l: v for l, v, _m, _c in series}}
    args.out.with_suffix(".json").write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {args.out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
