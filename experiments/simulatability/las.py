#!/usr/bin/env python3
"""Leakage-adjusted simulatability from the scored conditions.

    acc(c)  fraction of decisions where the simulator's top legal action equals
            the one the controller took, under condition c
    LAS_1   acc(xe) - acc(x), on decisions where the reasoning alone was enough
    LAS_0   the same, where it was not
    LAS     the mean of the two

The split is the adjustment: an explanation that states its own conclusion
raises acc(xe) without explaining anything, so Hase et al. separate those cases
out and weight the two halves equally rather than letting the leaking ones
dominate. Reported alongside are the raw per-condition accuracies -- a low LAS
from a simulator that is at chance everywhere means something quite different
from a low LAS from one that already knew the answer from the state.

Three things are read before the score itself.

The majority-class rate. Most periods are ``no_op``, so a simulator that always
says ``no_op`` scores well on accuracy and nothing on LAS. Any acc below this
line is worse than not reading the prompt.

The ACTIVE split. A decision to do nothing is sticky under any edit, so pooling
both reports the base rate of inaction; the same disaggregation the intervention
sweep needed applies here for the same reason.

``e_premises``. Ours, not theirs: the leak rate with the ``Therefore:`` line
removed. The gap between it and ``e`` is how much of the explanation's apparent
usefulness is the sentence that names the action.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

ORDER = ["xe", "x", "e", "e_premises"]


def mask_renorm(dist: dict[str, float], legal: list[str]) -> dict[str, float]:
    """Apply the legality mask the controller applied, so the simulator is
    scored on the choice that was actually available."""
    m = {k: v for k, v in dist.items() if k in legal}
    total = sum(m.values())
    return {k: v / total for k, v in m.items()} if total > 0 else m


def predicted_label(row: dict) -> str | None:
    labels = dict(row["options"])
    d = mask_renorm(row["distribution_simulated"], row["legal_ids"])
    if not d:
        return None
    return labels.get(max(d, key=d.__getitem__))


def mean(xs) -> float | None:
    """float, not int: these are means of booleans and of their differences,
    and an int 0 next to a float 0.5 in the written JSON invites a type check
    downstream that quietly treats one arm differently."""
    return float(st.mean(xs)) if xs else None


def fmt(v: float | None, pct: bool = True, width: int = 6) -> str:
    if v is None:
        return f"{'-':>{width}}"
    return f"{v*100:>{width-1}.1f}%" if pct else f"{v:>{width}.3f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("simulated", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()

    rows = [json.loads(l) for l in args.simulated.read_text().splitlines() if l.strip()]
    if not rows:
        raise SystemExit(f"{args.simulated} is empty")

    # period -> condition -> was the controller's action reproduced
    correct: dict[int, dict[str, bool]] = defaultdict(dict)
    target: dict[int, str] = {}
    simulators = sorted({r["simulator"] for r in rows})
    for r in rows:
        pred = predicted_label(r)
        if pred is None:
            continue
        target[r["period"]] = r["action_recorded"]
        correct[r["period"]][r["condition"]] = (pred == r["action_recorded"])

    # Only periods scored under every condition can enter a difference; a
    # partial period would contribute to one arm's accuracy and not another's.
    conditions = [c for c in ORDER if any(c in v for v in correct.values())]
    complete = [p for p, v in correct.items() if all(c in v for c in conditions)]
    dropped = len(correct) - len(complete)
    if not complete:
        raise SystemExit("no period was scored under every condition")

    active = [p for p in complete if target[p] != "no_op"]
    counts = defaultdict(int)
    for p in complete:
        counts[target[p]] += 1
    majority = max(counts.values()) / len(complete)

    print(f"simulator   {', '.join(simulators)}")
    print(f"decisions   {len(complete)} scored under all {len(conditions)} conditions"
          + (f" ({dropped} incomplete, dropped)" if dropped else ""))
    print(f"            {len(active)} ACTIVE, {len(complete)-len(active)} no_op")
    print(f"majority    {majority*100:.1f}%  (always answering "
          f"'{max(counts, key=counts.__getitem__)}')")
    print()

    print(f"{'condition':<12} {'acc (all)':>10} {'acc (ACTIVE)':>14} {'acc (no_op)':>13}")
    print("-" * 52)
    acc: dict[str, float] = {}
    acc_active: dict[str, float | None] = {}
    for c in conditions:
        allv = [correct[p][c] for p in complete]
        act = [correct[p][c] for p in active]
        noop = [correct[p][c] for p in complete if p not in set(active)]
        acc[c] = st.mean(allv)
        acc_active[c] = mean(act)
        print(f"{c:<12} {fmt(acc[c]):>10} {fmt(acc_active[c]):>14} {fmt(mean(noop)):>13}")

    def las(pool: list[int]) -> dict:
        leaking = [p for p in pool if correct[p].get("e")]
        nonleaking = [p for p in pool if not correct[p].get("e")]
        d1 = mean([correct[p]["xe"] - correct[p]["x"] for p in leaking])
        d0 = mean([correct[p]["xe"] - correct[p]["x"] for p in nonleaking])
        halves = [h for h in (d0, d1) if h is not None]
        return {
            "n": len(pool),
            "n_leaking": len(leaking), "n_nonleaking": len(nonleaking),
            "leak_rate": len(leaking) / len(pool) if pool else None,
            "leak_rate_premises": (
                sum(bool(correct[p].get("e_premises")) for p in pool) / len(pool)
                if pool else None),
            "las_1_leaking": d1, "las_0_nonleaking": d0,
            "las": mean(halves) if halves else None,
        }

    pools = {"all": complete, "ACTIVE": active}
    out = {"simulators": simulators, "n": len(complete), "dropped": dropped,
           "majority_rate": majority, "accuracy": acc,
           "accuracy_active": acc_active, "las": {}}

    print()
    print(f"{'':<12} {'n':>4} {'leak(e)':>9} {'leak(prem)':>11} "
          f"{'LAS_0':>8} {'LAS_1':>8} {'LAS':>8} {'[0,1]':>7}")
    print("-" * 74)
    for pool_name, pool in pools.items():
        if not pool:
            continue
        s = las(pool)
        s["las_normalised"] = None if s["las"] is None else (s["las"] + 1) / 2
        out["las"][pool_name] = s
        print(f"{pool_name:<12} {s['n']:>4} {fmt(s['leak_rate']):>9} "
              f"{fmt(s['leak_rate_premises']):>11} "
              f"{fmt(s['las_0_nonleaking'], pct=False, width=8)} "
              f"{fmt(s['las_1_leaking'], pct=False, width=8)} "
              f"{fmt(s['las'], pct=False, width=8)} "
              f"{fmt(s['las_normalised'], pct=False, width=7)}")

    notes = []
    for pool_name, s in out["las"].items():
        if s["n_nonleaking"] < 5:
            notes.append(f"{pool_name}: only {s['n_nonleaking']} non-leaking decisions, "
                         f"so LAS_0 rests on almost nothing and the mean of the two "
                         f"halves is not stable")
        if s["leak_rate"] is not None and s["leak_rate_premises"] is not None:
            gap = s["leak_rate"] - s["leak_rate_premises"]
            if gap > 0:
                notes.append(
                    f"{pool_name}: the conclusion accounts for {gap*100:.1f} points of "
                    f"the {s['leak_rate']*100:.1f}% leak rate; the premises alone leak "
                    f"{s['leak_rate_premises']*100:.1f}%")
            elif gap < 0:
                # The premises predict better once the conclusion is removed, so
                # the stated conclusion is leading the simulator away from what
                # the controller did -- an explanation whose summary misreports
                # its own body.
                notes.append(
                    f"{pool_name}: the premises alone leak {s['leak_rate_premises']*100:.1f}%, "
                    f"{-gap*100:.1f} points MORE than with the conclusion attached: the "
                    f"'Therefore:' line points away from the action taken")
            else:
                notes.append(f"{pool_name}: removing the conclusion does not change the "
                             f"{s['leak_rate']*100:.1f}% leak rate")
    if acc.get("x", 0) >= acc.get("xe", 0):
        notes.append("the state alone predicts the controller at least as well as the "
                     "state plus reasoning: the explanation adds nothing this simulator "
                     "can use")
    if min(acc.values()) < majority:
        below = [c for c, v in acc.items() if v < majority]
        notes.append(f"below the majority-class rate under {', '.join(below)}")
    if notes:
        print("\nnotes")
        for n in notes:
            print(f"  - {n}")
    out["notes"] = notes

    if args.out:
        args.out.write_text(json.dumps(out, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
