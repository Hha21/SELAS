#!/usr/bin/env python3
"""Checks on the aggregate and the frontier that need no run and no matplotlib."""
import sys, types
for name in ("matplotlib", "matplotlib.pyplot", "numpy"):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
sys.modules["matplotlib"].use = lambda *a, **k: None
sys.path.insert(0, ".")
import pareto as P

FAILURES = []
def check(name, got, want):
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'}  {name}: {got}" + ("" if good else f"   want {want}"))
    if not good:
        FAILURES.append(name)

print("aggregate: groups are averaged, then the groups are averaged")
# Faithfulness holds 3 of the 5 axes. A flat mean would let it outvote the
# other two axes for no reason beyond its having more sub-measures.
vals = {"Robustness": 1.0, "Sensitivity": 0.0, "Mistakes": 0.0,
        "Counterfactual": 0.0, "Simulatability": 1.0}
agg, groups, _ = P.aggregate(vals)
check("faithfulness group", round(groups["Faithfulness"], 3), 0.0)
check("aggregate", round(agg, 3), 0.667)
check("a flat mean would give", round(sum(vals.values()) / 5, 3), 0.4)

print("\naggregate: an unmeasured group makes the point unplottable")
v = dict(vals, Simulatability=None)
agg2, _g, missing = P.aggregate(v)
check("aggregate", agg2, None)
check("names what is missing", missing, ["Simulatability"])

print("\naggregate: a partly-measured group averages what it has")
v = dict(vals, Counterfactual=None, Mistakes=1.0)
_a, g, _m = P.aggregate(v)
check("faithfulness from 2 of 3", round(g["Faithfulness"], 3), 0.5)

print("\nfrontier: a genuine trade-off keeps every point")
pts = [(0.9, 100, "interpretable"), (0.5, 300, "middle"), (0.2, 400, "effective")]
check("all non-dominated", [n for _x, _y, n in P.frontier(pts)],
      ["effective", "middle", "interpretable"])

print("\nfrontier: a point beaten on both axes is dropped")
# high is better on both than mid, so mid is dominated however it is read.
pts = [(0.9, 350, "high"), (0.5, 300, "mid"), (0.2, 400, "effective")]
check("mid dropped", [n for _x, _y, n in P.frontier(pts)], ["effective", "high"])

print("\nfrontier: ties and singletons")
check("single point", [n for _x, _y, n in P.frontier([(0.5, 10, "solo")])], ["solo"])
check("equal utility, one more interpretable",
      [n for _x, _y, n in P.frontier([(0.8, 10, "a"), (0.4, 10, "b")])], ["a"])

print()
if FAILURES:
    print(f"{len(FAILURES)} failed: {', '.join(FAILURES)}")
    raise SystemExit(1)
print("all checks passed")
