#!/usr/bin/env python3
"""Summarise run_mediation.py output: how much of the objective's effect goes
through the written reasoning.

Every distribution is masked to the legal options and renormalised, as the
controller does, before anything is compared. Per run it reports:

    control      orig reproduces the recorded decision (argmax agreement)
    flips        decisions whose most likely action changes under total /
                 direct / reason, relative to orig
    carried      of the decisions total flips, the share direct flips to the
                 same action (moved with the reasoning fixed) and the share
                 reason flips to it (moved by the reasoning alone)
    TV           mean total-variation distance from orig, per condition
    removal      mean P(remove_server) under each condition, over all
                 decisions and over those orig or total decides to remove

    python analyse_mediation.py mediation.jsonl [...] -o mediation.json
"""

from __future__ import annotations

import argparse
import json
import statistics as st
from pathlib import Path

CONDS = ("orig", "direct", "total", "reason")


def masked(dist: dict[str, float], legal: list[str]) -> dict[str, float]:
    m = {k: v for k, v in dist.items() if k in legal}
    z = sum(m.values())
    return {k: v / z for k, v in m.items()} if z > 0 else {}


def tv(a: dict[str, float], b: dict[str, float]) -> float:
    return 0.5 * sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in set(a) | set(b))


def argmax(d: dict[str, float]) -> str | None:
    return max(d, key=d.__getitem__) if d else None


def summarise(rows: list[dict]) -> dict:
    out: dict = {"decisions": len(rows)}
    if not rows:
        return out
    remove = next(oid for oid, label in rows[0]["options"] if label == "remove_server")
    D = [{c: masked(r[f"dist_{c}"], r["legal_ids"]) for c in CONDS} for r in rows]
    A = [{c: argmax(d[c]) for c in CONDS} for d in D]

    by_label = {label: oid for oid, label in rows[0]["options"]}
    out["control_agreement"] = st.mean(a["orig"] == by_label.get(r["action_recorded"])
                                       for a, r in zip(A, rows))
    for c in ("total", "direct", "reason"):
        out[f"flips_{c}"] = sum(a[c] != a["orig"] for a in A)
    flipped = [a for a in A if a["total"] != a["orig"]]
    out["carried_direct"] = (sum(a["direct"] == a["total"] for a in flipped) / len(flipped)) if flipped else None
    out["carried_reason"] = (sum(a["reason"] == a["total"] for a in flipped) / len(flipped)) if flipped else None
    for c in ("direct", "total", "reason"):
        out[f"tv_{c}"] = st.mean(tv(d["orig"], d[c]) for d in D)
    for c in CONDS:
        out[f"p_remove_{c}"] = st.mean(d[c].get(remove, 0.0) for d in D)
    sel = [d for d, a in zip(D, A) if remove in (a["orig"], a["total"])]
    out["remove_decisions"] = len(sel)
    for c in CONDS:
        out[f"p_remove_{c}_where_removing"] = st.mean(d[c].get(remove, 0.0) for d in sel) if sel else None
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", type=Path, nargs="+")
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()
    report = {}
    for path in args.inputs:
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        s = summarise(rows)
        name = f"{path.parent.name} ({rows[0]['objective_from']} -> {rows[0]['objective_to']})" if rows else path.parent.name
        report[name] = s
        if not rows:
            print(f"{name}: empty"); continue
        cd = "—" if s["carried_direct"] is None else f"{s['carried_direct']:.0%}"
        cr = "—" if s["carried_reason"] is None else f"{s['carried_reason']:.0%}"
        print(f"{name}: n={s['decisions']}, control reproduces {s['control_agreement']:.0%}")
        print(f"    flips vs orig: total {s['flips_total']}, direct {s['flips_direct']}, "
              f"reason {s['flips_reason']}; of total's flips, direct makes the same {cd}, reason {cr}")
        print(f"    TV from orig: direct {s['tv_direct']:.3f}  total {s['tv_total']:.3f}  "
              f"reason {s['tv_reason']:.3f}")
        print(f"    P(remove): orig {s['p_remove_orig']:.3f}  direct {s['p_remove_direct']:.3f}  "
              f"total {s['p_remove_total']:.3f}  reason {s['p_remove_reason']:.3f}"
              f"  (over {s['remove_decisions']} removal decisions: "
              + "  ".join(f"{c} {s[f'p_remove_{c}_where_removing']:.3f}" for c in CONDS
                          if s[f'p_remove_{c}_where_removing'] is not None) + ")")
    if args.out:
        args.out.write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
