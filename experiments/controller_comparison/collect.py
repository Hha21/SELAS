#!/usr/bin/env python3
"""Turn one run's raw outputs into a tidy series plus a summary.

Two sources, because neither alone is enough:

* **SWIM's own output** (`.sca`/`.vec`, SQLite -- `swim.ini` sets
  `SqliteOutputScalarManager`/`SqliteOutputVectorManager`). This is the only
  place utility exists: `SimpleMonitor.ned` declares
  `@statistic[utility](source="sum(utility)"; record=last)` for the total and
  `@statistic[utilityPeriod](source="utility"; record=vector)` per period.
  Nothing outside the simulator can compute it.

* **The controller's `decisions.jsonl`**, when the run was externally
  controlled. It carries what the controller *saw and chose* -- response time,
  the action, both action distributions -- which SWIM does not record.

The OMNeT++ SQLite schema differs a little between versions, so tables and
columns are introspected rather than assumed, and anything missing is reported
by name instead of raising.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swim_utility  # noqa: E402

# Vector statistics declared in SimpleMonitor.ned that we care about.
WANTED_VECTORS = {
    "activeServers": "active_servers",
    "brownoutFactor": "brownout_factor",
    "utilityPeriod": "utility_period",
    "serverCost": "server_cost",
}
WANTED_SCALARS = {"utility": "utility_total"}


def _tables(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]


def _simtime_scale(con: sqlite3.Connection) -> float:
    """OMNeT++ stores simtime as an integer with a power-of-ten exponent."""
    try:
        row = con.execute(
            "SELECT attrValue FROM runAttr WHERE attrName='simtimeExp' LIMIT 1"
        ).fetchone()
        if row:
            return 10.0 ** int(row[0])
    except sqlite3.Error:
        pass
    return 1e-12          # OMNeT++ default resolution: picoseconds


def read_scalars(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    out: dict[str, float] = {}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as con:
        if "scalar" not in _tables(con):
            return {}
        for module, name, value in con.execute(
            "SELECT moduleName, scalarName, scalarValue FROM scalar"
        ):
            out[f"{module}.{name}"] = value
            base = name.split(":")[0]
            if base in WANTED_SCALARS:
                out[WANTED_SCALARS[base]] = value
    return out


def read_vectors(path: Path) -> dict[str, list[tuple[float, float]]]:
    """{friendly_name: [(simtime_seconds, value), ...]}"""
    if not path.exists():
        return {}
    series: dict[str, list[tuple[float, float]]] = {}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as con:
        tables = _tables(con)
        if not {"vector", "vectorData"} <= tables:
            return {}
        scale = _simtime_scale(con)
        time_col = "simtimeRaw" if "simtimeRaw" in _columns(con, "vectorData") else "simtime"

        for vid, module, vname in con.execute(
            "SELECT vectorId, moduleName, vectorName FROM vector"
        ):
            base = vname.split(":")[0]
            if base not in WANTED_VECTORS:
                continue
            rows = con.execute(
                f"SELECT {time_col}, value FROM vectorData WHERE vectorId=? ORDER BY {time_col}",
                (vid,),
            ).fetchall()
            series[WANTED_VECTORS[base]] = [(t * scale, v) for t, v in rows]
    return series


def read_decisions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def build(run_dir: Path, sla: float = 0.75, warmup: float = 900.0) -> dict:
    # Searched recursively rather than at the top level: SWIM writes under a
    # network-named subdirectory (result-dir ../../../results/SWIM), and the
    # controller writes under its own run id. Neither lands beside the other.
    sca = next(iter(sorted(run_dir.rglob("*.sca"))), run_dir / "missing.sca")
    vec = next(iter(sorted(run_dir.rglob("*.vec"))), run_dir / "missing.vec")
    dec = next(iter(sorted(run_dir.rglob("decisions.jsonl"))), run_dir / "decisions.jsonl")

    scalars = read_scalars(sca)
    vectors = read_vectors(vec)
    decisions = read_decisions(dec)

    # The utility SWIM reports: periodUtilitySEAMS2017A from plotResults.R,
    # computed from the vectors (swim_utility.py, verified equal to SWIM's R on
    # published and on our own runs). utility_total below is the simulator's
    # ICAC 2016 scalar, which has no server-cost term; it is kept for continuity
    # with earlier results but is not the number to report.
    seams = icac = None
    if sca.exists() and vec.exists():
        try:
            seams = swim_utility.utility(vec, sca, "seams2017a")
            icac = swim_utility.utility(vec, sca, "icac2016")
        except (KeyError, ValueError, StopIteration) as exc:
            print(f"  (could not compute SWIM utility for {run_dir.name}: {exc})")

    # Cumulative utility over the evaluation window. SWIM scores from the end of
    # the warmup period, so anything before it must not contribute.
    cum, running = [], 0.0
    for t, v in vectors.get("utility_period", []):
        if t < warmup:
            continue
        running += v
        cum.append((t, running))

    # The plotted curve is SWIM's reported utility, accumulated per period. The
    # one above is the simulator's ICAC 2016 series, kept under its own name.
    cum_icac = cum
    if seams:
        cum, running = [], 0.0
        for t, v in seams["periods"]:
            running += v
            cum.append((t, running))

    rt = [(d["sim_elapsed_s"], d["observation"]["avg_rt"]) for d in decisions]
    violations = sum(1 for _, v in rt if v > sla)

    # SLA violations as SWIM itself scores them. UtilityScorer returns a
    # positive utility when the period's response time is within the threshold
    # and min(0, throughput*1.5 - latePenalty) when it is not, with latePenalty
    # = maxServers * maxServiceRate * 1.5 -- negative for any real throughput.
    # So a scored period is a violation exactly when its utility is negative.
    # Unlike the count above, this needs no controller log, so it is the same
    # measurement for socket-driven runs and for SWIM's built-in managers.
    scored = [v for t, v in vectors.get("utility_period", []) if t >= warmup]
    swim_violations = sum(1 for v in scored if v < 0)

    return {
        "run_dir": str(run_dir),
        "sources": {
            "sca": sca.name if sca.exists() else None,
            "vec": vec.name if vec.exists() else None,
            "decisions": len(decisions),
            "decisions_path": str(dec) if decisions else None,
        },
        "vectors_found": sorted(vectors),
        "utility_total": scalars.get("utility_total"),
        "utility_seams2017a": seams["total"] if seams else None,
        "utility_icac2016": icac["total"] if icac else None,
        "mean_servers": seams["mean_servers"] if seams else None,
        "mean_dimmer": seams["mean_dimmer"] if seams else None,
        "late_periods_seams": seams["late_periods"] if seams else None,
        "utility_cumulative": cum,
        "utility_cumulative_icac2016": cum_icac,
        "response_time_swim": seams["response_times"] if seams else [],
        "series": vectors,
        "response_time": rt,
        "sla_violations": violations,
        "sla_violation_rate": (violations / len(rt)) if rt else None,
        "scored_periods": len(scored),
        "sla_violations_swim": swim_violations,
        "sla_violation_rate_swim": (swim_violations / len(scored)) if scored else None,
        "decisions": decisions,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path, nargs="+")
    ap.add_argument("--sla", type=float, default=0.75)
    ap.add_argument("--warmup", type=float, default=900.0)
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="write the combined result as JSON here")
    args = ap.parse_args()

    results = []
    for d in args.run_dir:
        r = build(d, sla=args.sla, warmup=args.warmup)
        results.append(r)
        print(f"{d}")
        print(f"  sca/vec:        {r['sources']['sca']} / {r['sources']['vec']}")
        print(f"  vectors found:  {r['vectors_found'] or 'NONE'}")
        print(f"  utility (SWIM reported, SEAMS2017A): {r['utility_seams2017a']}   simulator scalar: {r['utility_total']}")
        print(f"  decisions:      {r['sources']['decisions']}")
        if r["sla_violation_rate"] is not None:
            print(f"  SLA violations: {r['sla_violations']} "
                  f"({r['sla_violation_rate']*100:.1f}% of periods)")
    if args.out:
        slim = [{k: v for k, v in r.items() if k != "decisions"} for r in results]
        args.out.write_text(json.dumps(slim, indent=2))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
