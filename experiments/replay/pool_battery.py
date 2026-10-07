#!/usr/bin/env python3
"""Pool the intervention battery over runs, split by what the controller did.

replay_all.sbatch writes one battery per run (one arm directory per seed-set),
and the per-arm analyses (faithfulness/analyse.py, counterfactual/analyse_cf.py,
simulatability/las.py) each read one run. This pools the runs of one design
cell and reports every measure separately for decisions to do nothing and
decisions to act. The 95% intervals resample runs, not decisions: decisions
within a run share one closed loop and are not independent.

Measures, each a rate over decisions:

``faith/<intervention>``  the action changes when the explanation is perturbed
                          (argmax of the masked re-scored distribution against
                          the recorded action; ``original`` is the control).
``cf_<mode>/<edit>``      the action changes when the telemetry is edited, against
                          the identity edit of the same mode (``generate``: the
                          explanation is regenerated from the edited telemetry;
                          ``score``: the recorded explanation is kept).
``cf_<mode>/pair:<a>|<b>`` the actions differ between the two opposing edits.
``echo/<edit>``           the regenerated explanation reports the substituted
                          value (where the value is distinctive enough to test).
``sim_<tag>/<condition>`` the simulator predicts the recorded action.

    python pool_battery.py ~/selas-results/interp-gemma27b-final -o battery.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "counterfactual"))
import edits as E  # noqa: E402

SPLITS = ("no_op", "action", "all")


def mask_renorm(dist: dict[str, float], legal: list[str]) -> dict[str, float]:
    m = {k: v for k, v in dist.items() if k in legal}
    total = sum(m.values())
    return {k: v / total for k, v in m.items()} if total > 0 else m


def top(dist: dict[str, float], legal: list[str], options) -> str | None:
    d = mask_renorm(dist, legal)
    return dict(options).get(max(d, key=d.__getitem__)) if d else None


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def split_of(action: str) -> str:
    return "no_op" if action == "no_op" else "action"


def run_measures(arm: Path) -> dict[str, dict[str, list[bool]]]:
    """measure -> split -> outcomes for one run."""
    out: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))

    def add(measure: str, action: str, value: bool) -> None:
        out[measure][split_of(action)].append(value)
        out[measure]["all"].append(value)

    for r in read(arm / "rescored.jsonl"):
        rec = r["distribution_recorded"]
        new = top(r["distribution_rescored"], r["legal_ids"], r["options"])
        if not rec or new is None:
            continue
        was = dict(r["options"])[max(rec, key=rec.__getitem__)]
        add(f"faith/{r['intervention']}", r["action_recorded"], was != new)

    for mode in ("score", "generate"):
        by: dict[int, dict[str, dict]] = defaultdict(dict)
        for r in read(arm / f"cf_{mode}.jsonl"):
            by[r["period"]][r["arm"]] = r
        for arms in by.values():
            o = arms.get("original")
            if o is None:
                continue
            base = top(o["distribution_cf"], o["legal_ids"], o["options"])
            acts = {name: top(a["distribution_cf"], a["legal_ids"], a["options"])
                    for name, a in arms.items()}
            for name, a in arms.items():
                if name == "original":
                    continue
                add(f"cf_{mode}/{name}", o["action_recorded"], acts[name] != base)
                if mode == "generate" and a.get("reasoning_new") is not None:
                    ec = E.is_echoed(a["reasoning_new"], E.candidate_values(a.get("edit")))
                    if ec is not None:
                        add(f"echo/{name}", o["action_recorded"], ec)
            for a, b in E.PAIRS:
                if a in acts and b in acts:
                    add(f"cf_{mode}/pair:{a}|{b}", o["action_recorded"], acts[a] != acts[b])

    for f in sorted(arm.glob("simulated_*.jsonl")):
        tag = f.stem.removeprefix("simulated_")
        for r in read(f):
            pred = top(r["distribution_simulated"], r["legal_ids"], r["options"])
            if pred is None:
                continue
            add(f"sim_{tag}/{r['condition']}", r["action_recorded"], pred == r["action_recorded"])
    return out


def pooled(per_run: list[list[bool]], reps: int = 2000, seed: int = 0) -> dict | None:
    """Pooled rate with a percentile interval from resampling runs."""
    runs = [r for r in per_run if r]
    if not runs:
        return None
    vals = [v for r in runs for v in r]
    rng = random.Random(seed)
    stats = []
    for _ in range(reps):
        s = [v for r in (rng.choice(runs) for _ in runs) for v in r]
        stats.append(sum(s) / len(s))
    stats.sort()
    return {"rate": sum(vals) / len(vals), "lo": stats[int(0.025 * reps)],
            "hi": stats[int(0.975 * reps) - 1], "n": len(vals), "runs": len(runs)}


def fmt(s: dict | None) -> str:
    if s is None:
        return f"{'-':>24}"
    return f"{100*s['rate']:5.1f}% [{100*s['lo']:4.1f}, {100*s['hi']:5.1f}] {s['n']:>5}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path, help="directory holding one arm directory per run")
    ap.add_argument("--arms", nargs="*", default=None, help="arm directories (default: all)")
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()

    arms = ([args.run / a for a in args.arms] if args.arms
            else sorted(p for p in args.run.iterdir() if p.is_dir()))
    per = [run_measures(a) for a in arms]
    measures = sorted({m for p in per for m in p})
    summary = {m: {s: pooled([p[m][s] for p in per if m in p]) for s in SPLITS}
               for m in measures}

    print(f"{len(arms)} runs: {' '.join(a.name for a in arms)}")
    print(f"{'measure':<34} {'no-op':>24} {'action':>24} {'all':>24}")
    section = None
    for m in measures:
        if m.split("/")[0] != section:
            section = m.split("/")[0]
            print("-" * 108)
        print(f"{m:<34} " + " ".join(fmt(summary[m][s]) for s in SPLITS))
    if args.out:
        args.out.write_text(json.dumps({"runs": [a.name for a in arms], "measures": summary},
                                       indent=1))
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
