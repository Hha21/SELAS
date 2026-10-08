#!/usr/bin/env python3
"""One run of run_sa.sh -> one JSON object (printed).

Utility is SWIM's reported SEAMS 2017A from swim_utility.utility(), the same
call collect.py makes (utility_seams2017a, late_periods_seams, mean_servers,
mean_dimmer). Also: SWIM's own utility:last scalar, the SEAMS 2017A components,
and how often the manager acted, counted from SWIM's log ("AdaptationMgr
simtime=T tactic=..." is printed for every non-empty decision), in total and
in the scored window (decisions at T >= 900 s), and the per-period utilities.

    summarise_sa.py RUN_DIR
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "controller_comparison"))
import swim_utility  # noqa: E402

WARMUP = 900.0
ACT = re.compile(r"^AdaptationMgr simtime=([0-9.e+-]+) tactic=(.*)$")


def main() -> int:
    run = Path(sys.argv[1])
    vec = next(run.glob("*.vec"))
    sca = vec.with_suffix(".sca")
    u = swim_utility.utility(vec, sca, "seams2017a")
    scal = swim_utility.read_scalars(sca)
    acts = []
    log = run / "swim.log"
    if log.exists():
        for line in log.read_text(errors="replace").splitlines():
            m = ACT.match(line.strip())
            if m:
                acts.append((float(m.group(1)), m.group(2)))
    rts = [r for _, r in u["response_times"]]
    out = {
        "label": run.name,
        "utility_seams2017a": u["total"],
        "utility_last": scal.get("utility:last"),
        "late_periods": u["late_periods"],
        "periods": u["components"]["periods"],
        "mean_servers": u["mean_servers"],
        "mean_dimmer": u["mean_dimmer"],
        "components": u["components"],
        "max_period_rt": max(rts) if rts else None,
        "actions": len(acts),
        "actions_scored": sum(1 for t, _ in acts if t >= WARMUP),
        "tactics_scored": sorted({a for t, a in acts if t >= WARMUP}),
        # per scored period (end time, SEAMS 2017A utility), for the per-period
        # upper bound table_sa.py computes over the fixed grid
        "period_utility": [[t, v] for t, v in u["periods"]],
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
