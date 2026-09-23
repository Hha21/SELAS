#!/usr/bin/env python3
"""Group built-in baseline runs by cell and report mean and spread over seeds.

Labels are ``<config>_<trace>_i<initialServers>_s<seed>``; everything but the
seed defines a cell. The standard deviation is the sample one (n-1), since the
seeds are a sample of the simulator's randomness rather than the whole of it.
"""

from __future__ import annotations

import json
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

LABEL = re.compile(r"^(?P<cell>.+)_s(?P<seed>\d+)$")


def main() -> int:
    rows = json.loads(Path(sys.argv[1]).read_text())
    cells: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        name = Path(r["run_dir"]).name
        m = LABEL.match(name)
        cells[m.group("cell") if m else name].append(r)

    print("utility = SWIM's reported SEAMS 2017A function (plotResults.R)")
    print(f"\n{'cell':<32} {'n':>3} {'utility mean':>13} {'sd':>9} "
          f"{'min':>10} {'max':>10} {'SLA viol':>9}")
    print("-" * 92)
    for cell in sorted(cells):
        rs = cells[cell]
        # SWIM's reported utility (SEAMS 2017A), not the simulator's scalar.
        u = [r["utility_seams2017a"] for r in rs if r.get("utility_seams2017a") is not None]
        v = [r["sla_violation_rate_swim"] for r in rs
             if r.get("sla_violation_rate_swim") is not None]
        if not u:
            print(f"{cell:<32} {len(rs):>3}   no utility recorded")
            continue
        sd = st.stdev(u) if len(u) > 1 else float("nan")
        print(f"{cell:<32} {len(u):>3} {st.mean(u):>13.1f} {sd:>9.1f} "
              f"{min(u):>10.1f} {max(u):>10.1f} "
              f"{(100 * st.mean(v)) if v else float('nan'):>8.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
