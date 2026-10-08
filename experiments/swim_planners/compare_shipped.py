#!/usr/bin/env python3
"""Compare a re-run of SWIM's PLA/Thallium manager with SWIM's shipped result.

    compare_shipped.py RUN_DIR SHIPPED.vec [--tolerance-s 1.0]

Reports, for both runs, SWIM's reported utility (SEAMS 2017A, the scorer
collect.py and summarise.py use), the simulator's own utility:last scalar, late
periods, mean servers and dimmer; then how far the decisions agree:

* transitionsEvaluated, decision by decision. It is a pure function of the
  reachability relation and the configuration at the decision, so equal
  sequences mean the same relation *and* the same configuration trajectory.
* the activeServers / serverCost / brownoutFactor step series: the sequence of
  values, and the largest difference in the time of each change. Changes are
  applied after the measured wall-clock decision time (simulateDecisionDelay),
  so their times differ by milliseconds between machines even when the
  decisions are identical.
"""

from __future__ import annotations

import argparse
import sqlite3
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "controller_comparison"))
import swim_utility  # noqa: E402

SERIES = ("activeServers:vector", "serverCost:vector", "brownoutFactor:vector")


def vector(vec: Path, name: str) -> list[tuple[float, float]]:
    with sqlite3.connect(f"file:{vec}?mode=ro", uri=True) as c:
        exp = c.execute("SELECT simtimeExp FROM run LIMIT 1").fetchone()[0]
        rows = c.execute(
            "SELECT simtimeRaw, value FROM vector NATURAL JOIN vectorData "
            "WHERE vectorName = ? ORDER BY eventNumber", (name,)).fetchall()
    return [(t * 10.0 ** exp, float(v)) for t, v in rows]


def changes(series: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The step function's change points (the monitor also re-records unchanged values)."""
    out, last = [], None
    for t, v in series:
        if last is None or abs(v - last) > 1e-9:
            out.append((t, v))
            last = v
    return out


def summary(vec: Path) -> dict:
    sca = vec.with_suffix(".sca")
    seams = swim_utility.utility(vec, sca, "seams2017a")
    scal = swim_utility.read_scalars(sca)
    dec = [v for _, v in vector(vec, "decisionTime:vector")]
    return {
        "seams2017a": seams["total"],
        "utility_last": scal.get("utility:last"),
        "late": seams["late_periods"],
        "servers": seams["mean_servers"],
        "dimmer": seams["mean_dimmer"],
        "periods": seams["components"]["periods"],
        "decision_ms": st.mean(dec) if dec else float("nan"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path, help="run directory (or .vec)")
    ap.add_argument("shipped", type=Path, help="shipped .vec (SWIM/tools/THALLIUM/...)")
    ap.add_argument("--tolerance-s", type=float, default=1.0,
                    help="max |dt| for a change to count as the same change")
    a = ap.parse_args()
    run = a.run if a.run.suffix == ".vec" else next(a.run.rglob("*.vec"))

    s_run, s_ship = summary(run), summary(a.shipped)
    print(f"{'':<22}{'re-run':>14}{'shipped':>14}{'diff':>12}")
    for k in ("seams2017a", "utility_last", "late", "servers", "dimmer", "periods", "decision_ms"):
        x, y = s_run[k], s_ship[k]
        print(f"{k:<22}{x:>14.4f}{y:>14.4f}{x - y:>12.4f}")

    ok = True
    te_r = [int(v) for _, v in vector(run, "transitionsEvaluated:vector")]
    te_s = [int(v) for _, v in vector(a.shipped, "transitionsEvaluated:vector")]
    diff = [i for i, (x, y) in enumerate(zip(te_r, te_s)) if x != y]
    same = len(te_r) == len(te_s) and not diff
    ok &= same
    print(f"\ntransitionsEvaluated: {len(te_r)} vs {len(te_s)} decisions, "
          f"{'identical' if same else f'{len(diff)} differ, first at decision {diff[0] if diff else None}'}"
          f"; mean {st.mean(te_r):.1f} vs {st.mean(te_s):.1f}")

    for name in SERIES:
        cr, cs = changes(vector(run, name)), changes(vector(a.shipped, name))
        vals_same = [round(v, 9) for _, v in cr] == [round(v, 9) for _, v in cs]
        dts = [abs(x[0] - y[0]) for x, y in zip(cr, cs)]
        within = vals_same and all(d <= a.tolerance_s for d in dts)
        ok &= within
        print(f"{name:<24} changes {len(cr):>3} vs {len(cs):>3}; values "
              f"{'identical' if vals_same else 'DIFFER'}; max |dt| = {max(dts) if dts else 0:.3f} s"
              f"{'' if within else '  <-- mismatch'}")
        if not vals_same:
            for i, (x, y) in enumerate(zip(cr, cs)):
                if abs(x[1] - y[1]) > 1e-9 or abs(x[0] - y[0]) > a.tolerance_s:
                    print(f"    first difference at change {i}: re-run {x}, shipped {y}")
                    break
    print("\nSAME DECISIONS" if ok else "\nDECISIONS DIFFER")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
