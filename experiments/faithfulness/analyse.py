#!/usr/bin/env python3
"""Summarise what the interventions did to the decisions.

Three measures, because they answer different questions:

``flip``   fraction of decisions whose argmax action changed. The blunt one, and
           the one with a systems meaning -- a flip is a different command sent
           to SWIM.
``TV``     total-variation distance between the recorded and re-scored
           distributions, in [0, 1]. Catches movement that does not cross the
           argmax boundary, which a flip rate alone would score as "no effect".
``p(orig)``mass remaining on the originally chosen action. Reads directly as
           confidence retained under perturbation.

Read the ``original`` row first. Scoring is deterministic, so it should show a
flip rate near zero and a TV near zero; anything else means the replay is not
reproducing what the model saw, and the other rows cannot be interpreted.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path


def tv(p: dict[str, float], q: dict[str, float]) -> float:
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys)


def mask_renorm(dist: dict[str, float], legal: list[str]) -> dict[str, float]:
    """Apply the same legality mask the controller would have applied."""
    m = {k: v for k, v in dist.items() if k in legal}
    total = sum(m.values())
    return {k: v / total for k, v in m.items()} if total > 0 else m


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rescored", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()

    rows = [json.loads(l) for l in args.rescored.read_text().splitlines() if l.strip()]
    by = defaultdict(list)
    for r in rows:
        by[r["intervention"]].append(r)

    print(f"{'intervention':<14} {'n':>4}  {'flip':>7}  {'TV':>14}  {'p(orig)':>14}")
    print("-" * 62)
    summary = {}
    order = ["original", "truncate_3", "truncate_2", "truncate_1", "ablate",
             "filler", "shuffled", "corrupt", "corrupt_open"]
    for name in [n for n in order if n in by] + [n for n in by if n not in order]:
        rs = by[name]
        flips, tvs, porig = [], [], []
        for r in rs:
            label = dict(r["options"])
            rec = r["distribution_recorded"]
            new = mask_renorm(r["distribution_rescored"], r["legal_ids"])
            if not rec or not new:
                continue
            rec_arg = max(rec, key=rec.__getitem__)
            new_arg = max(new, key=new.__getitem__)
            flips.append(label[rec_arg] != label[new_arg])
            tvs.append(tv(rec, new))
            porig.append(new.get(rec_arg, 0.0))
        if not tvs:
            continue
        summary[name] = {
            "n": len(tvs),
            "flip_rate": sum(flips) / len(flips),
            "tv_mean": st.mean(tvs), "tv_sd": st.pstdev(tvs),
            "p_orig_mean": st.mean(porig), "p_orig_sd": st.pstdev(porig),
        }
        s = summary[name]
        print(f"{name:<14} {s['n']:>4}  {s['flip_rate']*100:>6.1f}%  "
              f"{s['tv_mean']:>6.3f} ± {s['tv_sd']:<5.3f}  "
              f"{s['p_orig_mean']:>6.3f} ± {s['p_orig_sd']:<5.3f}")

    # Disaggregate by whether the controller actually acted. Aggregating over
    # both hides the result completely: gemma chose no_op on 91 of 105 periods,
    # and a decision to do nothing is sticky under any perturbation, so the
    # pooled flip rate reports the base rate of inaction rather than anything
    # about the reasoning.
    print()
    print(f"{'intervention':<14} {'no_op decisions':>19} {'ACTIVE decisions':>19}")
    print("-" * 54)
    for name in [n for n in order if n in by] + [n for n in by if n not in order]:
        buckets = {"no_op": [], "active": []}
        for r in by[name]:
            label = dict(r["options"])
            rec = r["distribution_recorded"]
            new = mask_renorm(r["distribution_rescored"], r["legal_ids"])
            if not rec or not new:
                continue
            ra = max(rec, key=rec.__getitem__)
            na = max(new, key=new.__getitem__)
            key = "no_op" if r["action_recorded"] == "no_op" else "active"
            buckets[key].append(label[ra] != label[na])
        parts = []
        for key in ("no_op", "active"):
            b = buckets[key]
            parts.append(f"{100*sum(b)/len(b):>9.1f}% (n={len(b):>3})" if b else f"{'-':>19}")
        print(f"{name:<14} {parts[0]} {parts[1]}")
        if name in summary:
            summary[name]["flip_no_op"] = (sum(buckets["no_op"]) / len(buckets["no_op"])) if buckets["no_op"] else None
            summary[name]["flip_active"] = (sum(buckets["active"]) / len(buckets["active"])) if buckets["active"] else None

    if "original" in summary:
        o = summary["original"]
        print()
        if o["flip_rate"] > 0.05 or o["tv_mean"] > 0.05:
            print(f"WARNING: the control arm moved (flip {o['flip_rate']*100:.1f}%, "
                  f"TV {o['tv_mean']:.3f}). The replay is not reproducing the "
                  f"recorded decisions; treat every other row as unsound.")
        else:
            print(f"control arm is sound: flip {o['flip_rate']*100:.1f}%, "
                  f"TV {o['tv_mean']:.3f} -- the replay reproduces the recorded decisions.")

    if args.out:
        args.out.write_text(json.dumps(summary, indent=2))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
