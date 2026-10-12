#!/usr/bin/env python3
"""The five interpretability aspects of Yeo et al. on the final design, for all
decisions, decisions to act and decisions to do nothing (1 = interpretable end).

    Robustness      1 - share changed when the reasoning is reworded
    Sensitivity     share changed when the reasoning is removed
    Mistakes        share changed by negating the SLA premise, read against the
                    same reasoning with the conclusion already removed (paired:
                    corrupt_open vs truncate_3, as experiments/spider/spider.py)
    Counterfactual  share whose action differs between opposing telemetry edits,
                    reasoning regenerated (mean of the three pairs)
    Simulatability  (acc(premises) - acc(state) + 1) / 2 for a second model,
                    mean of the two students (as the per-run simulatability files)

Rates are pooled over runs with run-resampled 95% intervals, from
pool_battery.py's JSON and, for Mistakes, the per-decision rescored.jsonl.

    python aspects.py DIR --battery DIR/battery.json -o DIR/aspects.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pool_battery import pooled  # noqa: E402

SPLITS = ("all", "action", "no_op")
STUDENTS = ("gemma-3-12b-it", "qwen2.5-14b-instruct")
PAIRS = ("rt_breached|rt_met", "load_high|load_low", "spare_none|spare_ample")


def top(dist: dict) -> str:
    return max(dist, key=dist.get)


def mistakes(run_dirs: list[Path]) -> dict:
    """Paired flip, corrupt_open against truncate_3, per split."""
    acc = {s: defaultdict(list) for s in SPLITS}
    for d in run_dirs:
        by = defaultdict(dict)
        for line in (d / "rescored.jsonl").read_text().splitlines():
            x = json.loads(line)
            if x["intervention"] in ("corrupt_open", "truncate_3"):
                by[x["period"]][x["intervention"]] = x
        for pair in by.values():
            if len(pair) < 2:
                continue
            a, b = pair["corrupt_open"], pair["truncate_3"]
            flip = top(a["distribution_rescored"]) != top(b["distribution_rescored"])
            split = "no_op" if a["action_recorded"] == "no_op" else "action"
            for s in (split, "all"):
                acc[s][d.name].append(flip)
    return {s: pooled(list(acc[s].values())) for s in SPLITS}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", type=Path)
    ap.add_argument("--battery", type=Path, required=True)
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    M = json.loads(args.battery.read_text())["measures"]
    runs = sorted(p for p in args.dir.iterdir() if (p / "rescored.jsonl").exists())
    mis = mistakes(runs)

    out = {}
    for s in SPLITS:
        par, abl = M["faith/paraphrase"][s], M["faith/ablate"][s]
        cf = [M[f"cf_generate/pair:{p}"][s] for p in PAIRS]
        sim = [(M[f"sim_{t}/e_premises"][s]["rate"] - M[f"sim_{t}/x"][s]["rate"] + 1) / 2 for t in STUDENTS]
        out[s] = {
            "Robustness": {"value": 1 - par["rate"], "lo": 1 - par["hi"], "hi": 1 - par["lo"]},
            "Sensitivity": {"value": abl["rate"], "lo": abl["lo"], "hi": abl["hi"]},
            "Mistakes": {"value": mis[s]["rate"], "lo": mis[s]["lo"], "hi": mis[s]["hi"]},
            "Counterfactual": {"value": sum(c["rate"] for c in cf) / len(cf),
                               "lo": sum(c["lo"] for c in cf) / len(cf),
                               "hi": sum(c["hi"] for c in cf) / len(cf)},
            "Simulatability": {"value": sum(sim) / len(sim), "lo": None, "hi": None},
            "n": abl["n"],
        }
    for s, v in out.items():
        print(f"{s:7s} n={v['n']:4d}  " + "  ".join(
            f"{k} {v[k]['value']:.2f}" for k in ("Robustness", "Sensitivity", "Mistakes",
                                                 "Counterfactual", "Simulatability")))
    args.out.write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
