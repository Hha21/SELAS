#!/usr/bin/env python3
"""SWIM's reported utility, ported from SWIM/tools/plotResults.R.

SWIM has two utility functions and they are not the same:

``icac2016``   what the simulator computes in UtilityScorer.cc and records as the
               ``utility:last`` scalar. Revenue per period, or a late penalty if
               the period's response time exceeds the threshold. No cost term, so
               extra servers are free.

``seams2017a`` the function in Moreno et al., "Comparing model-based predictive
               approaches to self-adaptation: CobRA and PLA" (SEAMS 2017), and
               the default that SWIM's own plotResults.R reports
               (utilityFc=periodUtilitySEAMS2017A, USE_COMPUTED_UTILITY <- TRUE).
               It adds a server-cost term, 10 * (maxServers - avgServers), which
               is credited only when revenue is at its optimum -- dimmer at 1 --
               so a controller must serve full content *and* run lean to earn it.

This module computes both from the recorded vectors, the way plotResults.R does,
so that a number from our runs means what a number in a SWIM paper means.

The port is deliberately literal, including behaviour that looks unintended:

* ``periodicAverage`` pairs interval end-times with per-group means by position
  (R's ``cbind``), not by label. It lines up when every period has at least one
  observation, which is the normal case.
* ``timeWeightedAverage`` fills an interval start that has no observation with
  the last value observed before it -- and, when there is none, with the last
  value in the whole series, because ``rev(order(df$x < t))[1]`` falls through
  to the final row when no element is TRUE.
* Vectors of unequal length are combined by R's recycling rule.

Matching these is what makes the result comparable to published SWIM numbers;
correcting them would make it merely plausible.
"""

from __future__ import annotations

import math
import sqlite3
import sys
from bisect import bisect_right
from pathlib import Path


# -- reading ------------------------------------------------------------------
def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def read_scalars(sca: Path) -> dict[str, float]:
    with _connect(sca) as c:
        return {n: v for n, v in c.execute("SELECT scalarName, scalarValue FROM scalar")}


def read_vector(vec: Path, name: str, module: str | None = None) -> list[tuple[float, float]]:
    """``readVector``: rows in the order SQLite returns them, as R receives them."""
    with _connect(vec) as c:
        exp = c.execute("SELECT simtimeExp FROM run LIMIT 1").fetchone()[0]
        scale = 10.0 ** exp
        q = ("SELECT simtimeRaw, CAST(value AS REAL) FROM vector NATURAL JOIN vectorData "
             "WHERE vectorName = ?")
        args: list = [name]
        if module is not None:
            q += " AND moduleName = ?"
            args.append(module)
        return [(raw * scale, v) for raw, v in c.execute(q, args)]


# -- R semantics ----------------------------------------------------------------
def _find_interval(x: float, breaks: list[float]) -> int:
    """R ``findInterval``: count of breaks <= x (0 when x < breaks[0])."""
    return bisect_right(breaks, x)


def _seq(start: float, end: float, step: float) -> list[float]:
    n = int(math.floor((end - start) / step + 1e-9)) + 1
    return [start + i * step for i in range(max(0, n))]


def _recycle(xs: list[float], n: int) -> list[float]:
    return [xs[i % len(xs)] for i in range(n)] if xs else [math.nan] * n


def periodic_average(df: list[tuple[float, float]], period: float) -> list[tuple[float, float]]:
    """Mean per period, labelled by the period's end time."""
    xs = [x for x, _ in df]
    start = math.floor(min(xs) / period) * period
    end = math.ceil(max(xs) / period) * period
    intervals = _seq(start + period, end, period)
    groups: dict[int, list[float]] = {}
    for x, y in df:
        groups.setdefault(_find_interval(x, intervals), []).append(y)
    means = [sum(v) / len(v) for _, v in sorted(groups.items())]
    n = max(len(intervals), len(means))                 # cbind recycling
    return list(zip(_recycle(intervals, n), _recycle(means, n)))


def time_weighted_average(df: list[tuple[float, float]], period: float) -> list[tuple[float, float]]:
    """Time-weighted mean per period, labelled by the period's start time."""
    xs = [x for x, _ in df]
    start = math.floor(min(xs) / period) * period
    end = math.ceil(max(xs) / period) * period
    if max(xs) == end:
        end = end + period
    intervals = _seq(start, end, period)

    present = set(xs)
    added = []
    for t in intervals:
        if t in present:
            continue
        before = [i for i, x in enumerate(xs) if x < t]
        idx = before[-1] if before else len(xs) - 1     # R falls through to the last row
        added.append((t, df[idx][1]))
    rows = df + added
    order = sorted(range(len(rows)), key=lambda i: rows[i][0])   # stable, like order()
    rows = [rows[i] for i in order]

    end_of = []
    for x, _ in rows:
        k = _find_interval(x, intervals)
        end_of.append(intervals[k - 1] + period if k >= 1 else math.nan)

    groups: dict[int, list[tuple[float, float]]] = {}
    for i in range(len(rows) - 1):
        x, y = rows[i]
        w = min(rows[i + 1][0], end_of[i]) - x
        groups.setdefault(_find_interval(x, intervals), []).append((y, w))
    wm = []
    for _, g in sorted(groups.items()):
        tw = sum(w for _, w in g)
        wm.append(sum(y * w for y, w in g) / tw if tw else math.nan)
    labels = intervals[:-1]                             # intervals[1:length(intervals)-1]
    n = max(len(labels), len(wm))
    return list(zip(_recycle(labels, n), _recycle(wm, n)))


# -- the utility functions ---------------------------------------------------------
def _period_icac2016(max_servers, max_rate, arrival, dimmer, rt_threshold, avg_rt, avg_servers):
    late_penalty = max_servers * max_rate * 1.5
    if avg_rt > rt_threshold or avg_rt < 0:
        return min(0.0, arrival * 1.5 - late_penalty)
    return float(round_half_even(arrival * ((1 - dimmer) * 1.0 + dimmer * 1.5)))


def _period_seams2017a(max_servers, max_rate, arrival, dimmer, rt_threshold, avg_rt, avg_servers):
    precision = 1e-5
    ur = arrival * ((1 - dimmer) * 1.0 + dimmer * 1.5)
    uc = 10 * (max_servers - avg_servers)
    ur_opt = arrival * 1.5
    if avg_rt <= rt_threshold and ur >= ur_opt - precision:
        return ur + uc
    if avg_rt <= rt_threshold:
        return ur
    return min(0.0, arrival - max_servers * max_rate) * 1.5


def round_half_even(v: float) -> float:
    """R's round() is IEC 60559 round-half-to-even, as is Python's."""
    return round(v)


FUNCTIONS = {"seams2017a": _period_seams2017a, "icac2016": _period_icac2016}


def utility(vec: Path, sca: Path, function: str = "seams2017a") -> dict:
    """Total and per-period utility, as plotResults.R computes it."""
    s = read_scalars(sca)
    period = s["evaluationPeriod"]
    rt_threshold = s["responseTimeThreshold"]
    max_servers = s["maxServers"]
    max_rate = s["maxServiceRate"]

    servers = read_vector(vec, "serverCost:vector")
    dimmer = [(x, 1 - y) for x, y in read_vector(vec, "brownoutFactor:vector")]
    responses = read_vector(vec, "lifeTime:vector")
    inter = periodic_average(read_vector(vec, "interArrival:vector"), period)
    arrival = [(x, 1 / y) for x, y in inter]

    end = math.ceil(max(x for x, _ in servers) / period) * period
    avg_rt = periodic_average(responses, period)
    dimmer_mean = [(x + period, y) for x, y in time_weighted_average(dimmer, period)]
    servers_mean = [(x + period, y) for x, y in time_weighted_average(servers, period)]

    trim = lambda d: [(x, y) for x, y in d if x <= end]
    arrival, dimmer_mean, servers_mean, avg_rt = map(trim, (arrival, dimmer_mean, servers_mean, avg_rt))

    n = max(len(arrival), len(dimmer_mean), len(servers_mean), len(avg_rt))
    a = _recycle([y for _, y in arrival], n)
    d = _recycle([y for _, y in dimmer_mean], n)
    r = _recycle([y for _, y in avg_rt], n)
    sv = _recycle([y for _, y in servers_mean], n)
    xs = _recycle([x for x, _ in avg_rt], n)

    f = FUNCTIONS[function]
    per = [f(max_servers, max_rate, a[i], d[i], rt_threshold, r[i], sv[i]) for i in range(n)]

    # Where the SEAMS 2017A total comes from: revenue in periods within the SLA,
    # the server-cost bonus (paid only when the dimmer is at 1), and penalties in
    # periods over it. The three sum to the total; kept so a large score can be
    # explained rather than just reported.
    comp = {"revenue": 0.0, "cost_bonus": 0.0, "penalty": 0.0,
            "bonus_periods": 0, "late_periods": 0, "periods": n}
    for i in range(n):
        if r[i] > rt_threshold:
            comp["penalty"] += min(0.0, a[i] - max_servers * max_rate) * 1.5
            comp["late_periods"] += 1
            continue
        ur = a[i] * ((1 - d[i]) * 1.0 + d[i] * 1.5)
        comp["revenue"] += ur
        if ur >= a[i] * 1.5 - 1e-5:
            comp["cost_bonus"] += 10 * (max_servers - sv[i])
            comp["bonus_periods"] += 1
    return {
        "function": function,
        "components": comp,
        "total": sum(per),
        "periods": list(zip(xs, per)),
        "lengths": {"arrival": len(arrival), "dimmer": len(dimmer_mean),
                    "servers": len(servers_mean), "response": len(avg_rt)},
        "late_periods": sum(1 for v in r if v > rt_threshold),
        # Per-period mean response time from SWIM's per-request records, the
        # same measure for every controller whether or not it logs decisions.
        "response_times": list(zip(xs, r)),
        "mean_servers": sum(sv) / len(sv) if sv else math.nan,
        "mean_dimmer": sum(d) / len(d) if d else math.nan,
    }


def main() -> int:
    for arg in sys.argv[1:]:
        p = Path(arg)
        vec = p if p.suffix == ".vec" else next(p.rglob("*.vec"))
        sca = vec.with_suffix(".sca")
        out = [utility(vec, sca, f) for f in ("seams2017a", "icac2016")]
        recorded = read_scalars(sca).get("utility:last")
        print(f"{p.name:<30} SEAMS2017A {out[0]['total']:>11.2f}   ICAC2016 {out[1]['total']:>11.2f}"
              f"   recorded {recorded if recorded is not None else float('nan'):>11.2f}"
              f"   late {out[0]['late_periods']:>3}  servers {out[0]['mean_servers']:.2f}"
              f"  dimmer {out[0]['mean_dimmer']:.2f}  lengths {out[0]['lengths']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
