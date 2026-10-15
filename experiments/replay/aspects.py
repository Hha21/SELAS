#!/usr/bin/env python3
"""The interpretability aspects of Yeo et al. on the final design, for all
decisions, decisions to act and decisions to do nothing (1 = interpretable end).

    Robustness      1 - share changed when the reasoning is reworded
    Sensitivity     share changed when the reasoning is removed
    Mistakes        share changed by negating the SLA premise, read against the
                    same reasoning with the conclusion already removed (paired:
                    corrupt_open vs truncate_3, as experiments/spider/spider.py)
    Substitution    share that take the kind of action (act / do nothing) that
                    another period's reasoning concludes, substituted for their
                    own, where it concludes the other kind (Paul et al.'s
                    indirect effect; shuffled_by_conclusion.py's "concludes
                    otherwise, adopts its kind")
    Counterfactual  share whose action differs between opposing telemetry edits,
                    reasoning regenerated (mean of the three pairs)
    Simulatability  Hase et al.'s leakage-adjusted simulatability (LAS): the gain
                    in a second model's accuracy when the reasoning is added to
                    the state, acc(xe) - acc(x), averaged over the decisions the
                    reasoning alone predicts (leaking) and those it does not;
                    pooled over runs, mapped to [0, 1] as (LAS + 1) / 2 so 0.5 is
                    no gain, and averaged over the two students, with intervals
                    from resampling runs (the same resample for both students).
                    Until 2026-10-14 this axis was (acc(premises) - acc(state)
                    + 1) / 2, the premises *replacing* the state; that variant is
                    kept as "Simulatability (premises only)".

Rates are pooled over runs with run-resampled 95% intervals, from
pool_battery.py's JSON, for Mistakes the per-decision rescored.jsonl, and for
Substitution shuffled_by_conclusion.py's JSON.

    python aspects.py DIR --battery DIR/battery.json [--substitution DIR/shuffled_by_conclusion.json] -o DIR/aspects.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulatability"))
from pool_battery import pooled  # noqa: E402
from las import predicted_label  # noqa: E402

SPLITS = ("all", "action", "no_op")
STUDENTS = ("gemma-3-12b-it", "qwen2.5-14b-instruct")
PAIRS = ("rt_breached|rt_met", "load_high|load_low", "spare_none|spare_ample")


def top(dist: dict, legal: list[str]) -> str:
    """The option the controller would take: the argmax over legal options."""
    return max((k for k in legal if k in dist), key=dist.get)


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
            flip = top(a["distribution_rescored"], a["legal_ids"]) != top(b["distribution_rescored"], b["legal_ids"])
            split = "no_op" if a["action_recorded"] == "no_op" else "action"
            for s in (split, "all"):
                acc[s][d.name].append(flip)
    return {s: pooled(list(acc[s].values())) for s in SPLITS}


def las_of(rows: list[dict]) -> float | None:
    """Hase et al.'s LAS on rows of {condition: correct}: the mean of the xe - x
    gain over leaking rows (e alone correct) and over non-leaking rows."""
    halves = [[r["xe"] - r["x"] for r in rows if r["e"] == leak] for leak in (True, False)]
    halves = [sum(h) / len(h) for h in halves if h]
    return sum(halves) / len(halves) if halves else None


def simulatability(run_dirs: list[Path], n_boot: int = 2000, seed: int = 0) -> dict:
    """LAS mapped to [0, 1], mean over STUDENTS, per split, with run-resampled
    95% intervals."""
    import random
    per = {s: {t: {} for t in STUDENTS} for s in SPLITS}   # split -> student -> run -> rows
    for d in run_dirs:
        for t in STUDENTS:
            by = defaultdict(dict)
            for line in (d / f"simulated_{t}.jsonl").read_text().splitlines():
                x = json.loads(line)
                by[x["period"]][x["condition"]] = predicted_label(x) == x["action_recorded"]
                by[x["period"]]["_action"] = x["action_recorded"]
            for c in by.values():
                if not all(k in c for k in ("xe", "x", "e")):
                    continue
                for s in ("no_op" if c["_action"] == "no_op" else "action", "all"):
                    per[s][t].setdefault(d.name, []).append(c)

    def score(s: str, runs: list[str]) -> float:
        return sum((las_of([r for n in runs for r in per[s][t].get(n, [])]) + 1) / 2
                   for t in STUDENTS) / len(STUDENTS)

    names = [d.name for d in run_dirs]
    rng, out = random.Random(seed), {}
    for s in SPLITS:
        boot = sorted(score(s, [rng.choice(names) for _ in names]) for _ in range(n_boot))
        out[s] = {"value": score(s, names), "lo": boot[int(0.025 * n_boot)],
                  "hi": boot[int(0.975 * n_boot) - 1]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", type=Path)
    ap.add_argument("--battery", type=Path, required=True)
    ap.add_argument("--substitution", type=Path,
                    help="shuffled_by_conclusion.py's output (default DIR/shuffled_by_conclusion.json)")
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    M = json.loads(args.battery.read_text())["measures"]
    runs = sorted(p for p in args.dir.iterdir() if (p / "rescored.jsonl").exists())
    mis = mistakes(runs)
    las = simulatability(runs)
    sub = json.loads((args.substitution or args.dir / "shuffled_by_conclusion.json").read_text())

    out = {}
    for s in SPLITS:
        par, abl = M["faith/paraphrase"][s], M["faith/ablate"][s]
        cf = [M[f"cf_generate/pair:{p}"][s] for p in PAIRS]
        sim = [(M[f"sim_{t}/e_premises"][s]["rate"] - M[f"sim_{t}/x"][s]["rate"] + 1) / 2 for t in STUDENTS]
        out[s] = {
            "Robustness": {"value": 1 - par["rate"], "lo": 1 - par["hi"], "hi": 1 - par["lo"]},
            "Sensitivity": {"value": abl["rate"], "lo": abl["lo"], "hi": abl["hi"]},
            "Mistakes": {"value": mis[s]["rate"], "lo": mis[s]["lo"], "hi": mis[s]["hi"]},
            "Substitution": {"value": (t := sub[f"{s}|concludes otherwise, adopts its kind"])["rate"],
                             "lo": t["lo"], "hi": t["hi"], "n": t["n"]},
            "Counterfactual": {"value": sum(c["rate"] for c in cf) / len(cf),
                               "lo": sum(c["lo"] for c in cf) / len(cf),
                               "hi": sum(c["hi"] for c in cf) / len(cf)},
            "Simulatability": las[s],
            "Simulatability (premises only)": {"value": sum(sim) / len(sim), "lo": None, "hi": None},
            "n": abl["n"],
        }
    for s, v in out.items():
        print(f"{s:7s} n={v['n']:4d}  " + "  ".join(
            f"{k} {v[k]['value']:.2f}" for k in ("Robustness", "Sensitivity", "Mistakes", "Substitution",
                                                 "Counterfactual", "Simulatability")))
    args.out.write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
