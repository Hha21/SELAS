#!/usr/bin/env python3
"""Aggregate run_sa.sh outputs (each run's summary.json) by cell.

Labels are ``<cell>_s<seed>``. Per cell: n, SEAMS 2017A utility mean ± sample
SD (n-1), min, max, late periods, mean servers, mean dimmer, decisions acted
on in the scored window. Cells named ``<trace>_fixed_srvNN_dimK`` form the
fixed-configuration grid; for each trace the best of them (by mean utility) is
reported, with the grid's spread.

    table_sa.py OUTDIR [OUTDIR ...] [--json FILE]
"""

from __future__ import annotations

import argparse
import json
import re
import statistics as st
from collections import defaultdict
from pathlib import Path

LABEL = re.compile(r"^(?P<cell>.+)_s(?P<seed>\d+)$")
GRID = re.compile(r"^(?P<trace>[a-z]+)_fixed_srv(?P<srv>\d+)_dim(?P<dim>\d+)$")


def ms(xs, d=1):
    if not xs:
        return "n/a"
    return f"{st.mean(xs):.{d}f} ± {st.stdev(xs):.{d}f}" if len(xs) > 1 else f"{xs[0]:.{d}f}"


def load(dirs):
    cells = defaultdict(list)
    for d in dirs:
        for f in sorted(Path(d).glob("*/summary.json")):
            try:
                r = json.loads(f.read_text())
            except json.JSONDecodeError:
                continue
            m = LABEL.match(r["label"])
            if m:
                r["seed"] = int(m.group("seed"))
                cells[m.group("cell")].append(r)
    return cells


def stats(rs):
    u = [r["utility_seams2017a"] for r in rs]
    return {"n": len(rs), "mean": st.mean(u), "sd": st.stdev(u) if len(u) > 1 else float("nan"),
            "min": min(u), "max": max(u),
            "late": st.mean(r["late_periods"] for r in rs),
            "servers": st.mean(r["mean_servers"] for r in rs),
            "dimmer": st.mean(r["mean_dimmer"] for r in rs),
            "acts": st.mean(r["actions_scored"] for r in rs),
            "seeds": sorted(r["seed"] for r in rs)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    cells = load(a.dirs)
    summary = {c: stats(rs) for c, rs in cells.items()}

    head = (f"{'cell':<34}{'n':>3}{'utility (mean ± sd)':>22}{'min':>10}{'max':>10}"
            f"{'late':>7}{'servers':>9}{'dimmer':>8}{'acts':>7}")
    print("SEAMS 2017A (swim_utility.py, as collect.py); late = scored periods over 0.75 s;"
          " acts = decisions with a tactic at t >= 900 s")
    print(head)
    print("-" * len(head))
    for c in sorted(k for k in summary if not GRID.match(k)):
        s = summary[c]
        u = [r["utility_seams2017a"] for r in cells[c]]
        print(f"{c:<34}{s['n']:>3}{ms(u):>22}{s['min']:>10.1f}{s['max']:>10.1f}"
              f"{s['late']:>7.1f}{s['servers']:>9.2f}{s['dimmer']:>8.3f}{s['acts']:>7.1f}")

    grid = defaultdict(dict)
    for c, s in summary.items():
        m = GRID.match(c)
        if m:
            grid[m.group("trace")][(int(m.group("srv")), int(m.group("dim")))] = s
    for trace, g in sorted(grid.items()):
        best = max(g, key=lambda k: g[k]["mean"])
        b = g[best]
        means = sorted((s["mean"] for s in g.values()), reverse=True)
        print(f"\n{trace}: fixed grid, {len(g)} configurations x {min(s['n'] for s in g.values())}-"
              f"{max(s['n'] for s in g.values())} seed-sets")
        print(f"  best in hindsight: {best[0]} servers, dimmer {best[1]}/9 = {best[1] / 9:.3f}: "
              f"{b['mean']:.1f} ± {b['sd']:.1f} (min {b['min']:.1f}, max {b['max']:.1f}), "
              f"late {b['late']:.1f}")
        print(f"  next best: " + ", ".join(
            f"{k[0]}s/d{k[1]} {g[k]['mean']:.1f}" for k in sorted(g, key=lambda k: -g[k]["mean"])[1:6]))
        print(f"  grid means: max {means[0]:.1f}, median {st.median(means):.1f}, min {means[-1]:.1f}")
        # Per-period upper bound: in every scored period take the best fixed
        # configuration's utility in that period (same seed-set). It ignores
        # boot delays and the transients of switching, so no policy can be
        # expected to reach it; the gap to the best fixed configuration is the
        # most adaptation could add on this trace.
        bounds = []
        for seed in sorted({r["seed"] for c in cells if GRID.match(c) and GRID.match(c).group("trace") == trace
                            for r in cells[c]}):
            per = [r["period_utility"] for c in cells if GRID.match(c) and GRID.match(c).group("trace") == trace
                   for r in cells[c] if r["seed"] == seed and r.get("period_utility")]
            if not per or len({len(p) for p in per}) != 1 or len({tuple(x[0] for x in p) for p in per}) != 1:
                continue
            bounds.append(sum(max(p[i][1] for p in per) for i in range(len(per[0]))))
        if bounds:
            print(f"  per-period upper bound (best fixed configuration chosen afresh every period, "
                  f"{len(bounds)} seed-sets): {ms(bounds)}")
            summary[f"{trace}_perperiod_bound"] = {"n": len(bounds), "mean": st.mean(bounds),
                                                   "sd": st.stdev(bounds) if len(bounds) > 1 else float("nan")}
        print("  mean utility by servers (rows) x dimmer level 0..9 (columns):")
        for srv in sorted({k[0] for k in g}):
            row = " ".join(f"{g[(srv, d)]['mean']:>8.0f}" if (srv, d) in g else f"{'':>8}" for d in range(10))
            print(f"   {srv:>2} {row}")
    if a.json:
        a.json.write_text(json.dumps({"cells": summary, "grid_best": {
            t: {"servers": max(g, key=lambda k: g[k]["mean"])[0], "dimmer_level": max(g, key=lambda k: g[k]["mean"])[1],
                **g[max(g, key=lambda k: g[k]["mean"])]} for t, g in grid.items()}}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
