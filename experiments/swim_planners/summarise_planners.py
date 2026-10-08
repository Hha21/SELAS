#!/usr/bin/env python3
"""Per-planner summary over seed-sets, from collect.py's results.json.

Labels are ``<cell>_s<seed>``; everything before the seed is the cell. Reports
SWIM's reported utility (SEAMS 2017A, as collect.py / summarise.py) as mean and
sample SD (n-1), with min and max; late periods (scored periods whose mean
response time exceeds 0.75 s, ``late_periods_seams``); and the time-weighted
mean servers and dimmer that the scorer uses. A run with seed 0 is listed on
its own line as well, since that is the one comparable with SWIM's shipped file.
"""

from __future__ import annotations

import json
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

LABEL = re.compile(r"^(?P<cell>.+)_s(?P<seed>\d+)$")


def fmt(xs: list[float], digits: int = 1) -> str:
    if not xs:
        return "n/a"
    sd = st.stdev(xs) if len(xs) > 1 else float("nan")
    return f"{st.mean(xs):.{digits}f} ± {sd:.{digits}f}"


def main() -> int:
    rows = json.loads(Path(sys.argv[1]).read_text())
    cells: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for r in rows:
        m = LABEL.match(Path(r["run_dir"]).name)
        if m:
            cells[m.group("cell")].append((int(m.group("seed")), r))
    print("utility = SWIM's reported SEAMS 2017A function (plotResults.R / swim_utility.py); "
          "mean ± sample SD over seed-sets")
    head = (f"{'cell':<22}{'seeds':>8}{'n':>4}{'utility':>20}{'min':>10}{'max':>10}"
            f"{'late periods':>16}{'servers':>14}{'dimmer':>14}")
    print(head)
    print("-" * len(head))
    for cell in sorted(cells):
        for name, rs in ((cell, [r for s, r in cells[cell] if s > 0]),
                         (f"{cell} (seed 0)", [r for s, r in cells[cell] if s == 0])):
            if not rs:
                continue
            seeds = sorted(int(LABEL.match(Path(r["run_dir"]).name).group("seed")) for r in rs)
            u = [r["utility_seams2017a"] for r in rs]
            late = [r["late_periods_seams"] for r in rs]
            sv = [r["mean_servers"] for r in rs]
            dm = [r["mean_dimmer"] for r in rs]
            span = f"{seeds[0]}-{seeds[-1]}" if len(seeds) > 1 else str(seeds[0])
            print(f"{name:<22}{span:>8}{len(rs):>4}{fmt(u):>20}{min(u):>10.1f}{max(u):>10.1f}"
                  f"{fmt(late):>16}{fmt(sv, 2):>14}{fmt(dm, 3):>14}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
