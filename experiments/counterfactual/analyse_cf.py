#!/usr/bin/env python3
"""Summarise whether decisions tracked the telemetry they were taken on.

The headline is the within-decision pair contrast. For each opposing pair of
edits -- the SLA breached against comfortably met, load spiked against
collapsed, capacity saturated against idle -- the same period is replayed both
ways and the two leanings compared:

    pressure(d) = p(relieving actions) - p(enriching actions)
    separation  = pressure(relieve edit) - pressure(enrich edit)

A controller that reads its input has a positive separation: pushed towards
overload it leans towards adding capacity or cutting content, and pushed the
other way it leans back. Zero means the telemetry made no difference. Negative
means it moved the wrong way.

Pressure rather than an argmax flip because 85 of 105 decisions are ``no_op``
and a flip-only measure would report almost every edit as inert, which is a
fact about the base rate rather than about the decision.

What enters the spider plot is the ``flip`` rate: pushed one way and then the
other, does the controller send SWIM a different command at all? The sign of the
separation is reported beside it, because the two can disagree sharply -- a
separation of +0.00002 has the right sign on four decisions in five and is a
preference the controller never acts on. An axis built on the sign alone would
score a controller that ignores its telemetry at two thirds of the way to
faithful.

In ``generate`` mode there is a second, sharper measure: ``echo``, the share of
regenerated reasonings that report the substituted number. A reasoning that
narrates telemetry it was never shown is confabulating regardless of which
action follows it, and because the edits are exact substitutions this is a
substring test rather than a judgement.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edits as E


def mask_renorm(dist: dict[str, float], legal: list[str]) -> dict[str, float]:
    m = {k: v for k, v in dist.items() if k in legal}
    total = sum(m.values())
    return {k: v / total for k, v in m.items()} if total > 0 else m


def tv(p: dict[str, float], q: dict[str, float]) -> float:
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys)


def argmax_label(dist: dict[str, float], options) -> str | None:
    if not dist:
        return None
    return dict(options).get(max(dist, key=dist.__getitem__))


def fmt(v, width=7, pct=False):
    if v is None:
        return f"{'-':>{width}}"
    return f"{v*100:>{width-1}.1f}%" if pct else f"{v:>{width}.3f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cf", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()

    rows = [json.loads(l) for l in args.cf.read_text().splitlines() if l.strip()]
    if not rows:
        raise SystemExit(f"{args.cf} is empty")
    mode = rows[0]["mode"]

    by: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        by[r["period"]][r["arm"]] = r

    def pressure_of(r: dict) -> float:
        return E.pressure(mask_renorm(r["distribution_cf"], r["legal_ids"]),
                          r["options"], r["dimmer"])

    # -- control ------------------------------------------------------------
    ctrl = [r for r in rows if r["arm"] == "original"]
    ctrl_tv = [tv(mask_renorm(r["distribution_cf"], r["legal_ids"]),
                  mask_renorm(r["distribution_recorded"], r["legal_ids"])) for r in ctrl]
    print(f"mode        {mode}")
    print(f"decisions   {len(by)}")
    if ctrl_tv:
        print(f"control     TV to the recorded distribution "
              f"{st.mean(ctrl_tv):.3f} ± {st.pstdev(ctrl_tv):.3f}"
              + ("   (regenerated, so drift is expected)" if mode == "generate" else ""))
        if mode == "score" and st.mean(ctrl_tv) > 0.05:
            print("  WARNING: the identity edit did not reproduce the recorded "
                  "decision; the replay is unsound and nothing below holds.")
    print()

    # -- per-edit movement against the identity arm -------------------------
    print(f"{'edit':<13} {'dir':<9} {'n':>4} {'dPressure':>10} {'TV':>8} "
          f"{'flip':>7} {'echo':>7}")
    print("-" * 62)
    per_edit = {}
    for arm, (_fn, direction) in E.EDITS.items():
        sign = 1.0 if direction == "relieve" else -1.0
        dp, tvs, flips, echoes = [], [], [], []
        for p, arms in by.items():
            if arm not in arms or "original" not in arms:
                continue
            a, o = arms[arm], arms["original"]
            dp.append(sign * (pressure_of(a) - pressure_of(o)))
            da = mask_renorm(a["distribution_cf"], a["legal_ids"])
            do = mask_renorm(o["distribution_cf"], o["legal_ids"])
            tvs.append(tv(da, do))
            flips.append(argmax_label(da, a["options"]) != argmax_label(do, o["options"]))
            if a.get("echoed") is not None:
                echoes.append(a["echoed"])
        if not dp:
            continue
        per_edit[arm] = {
            "direction": direction, "n": len(dp),
            "d_pressure": st.mean(dp), "d_pressure_sd": st.pstdev(dp),
            "tv": st.mean(tvs), "flip_rate": sum(flips) / len(flips),
            "echo_rate": (sum(echoes) / len(echoes)) if echoes else None,
        }
        s = per_edit[arm]
        print(f"{arm:<13} {direction:<9} {s['n']:>4} {fmt(s['d_pressure'], 10)} "
              f"{fmt(s['tv'], 8)} {fmt(s['flip_rate'], 7, pct=True)} "
              f"{fmt(s['echo_rate'], 7, pct=True)}")

    # -- the pair contrast ---------------------------------------------------
    print()
    print(f"{'pair':<26} {'n':>4} {'separation':>9} {'TV':>8} {'sign ok':>9} "
          f"{'sign bad':>8} {'flip':>8}")
    print("-" * 78)
    pairs = {}
    for relieve, enrich in E.PAIRS:
        seps, flips, tvs = [], [], []
        for p, arms in by.items():
            if relieve not in arms or enrich not in arms:
                continue
            a, b = arms[relieve], arms[enrich]
            seps.append(pressure_of(a) - pressure_of(b))
            da = mask_renorm(a["distribution_cf"], a["legal_ids"])
            db = mask_renorm(b["distribution_cf"], b["legal_ids"])
            # The systems-meaningful version: pushed one way and then the other,
            # does the controller send SWIM a different command at all? The sign
            # of the separation can be right while its magnitude is 1e-5, which
            # is a preference that never reaches an action.
            flips.append(argmax_label(da, a["options"]) != argmax_label(db, b["options"]))
            tvs.append(tv(da, db))
        if not seps:
            continue
        # Split the failures. "Moved the wrong way" and "did not move" are both
        # unfaithful to the telemetry, but they are different findings: one is a
        # controller reading its input backwards, the other one ignoring it.
        # A single CF-UF figure cannot tell them apart.
        eps = 1e-9
        correct = sum(s > eps for s in seps) / len(seps)
        wrong = sum(s < -eps for s in seps) / len(seps)
        flat = sum(abs(s) <= eps for s in seps) / len(seps)
        pairs[f"{relieve}|{enrich}"] = {
            "n": len(seps), "separation": st.mean(seps),
            "separation_sd": st.pstdev(seps),
            "correct_rate": correct, "wrong_rate": wrong, "flat_rate": flat,
            "cf_uf": 1 - correct,
            "flip_rate": sum(flips) / len(flips),
            "tv_mean": st.mean(tvs),
        }
        s = pairs[f"{relieve}|{enrich}"]
        print(f"{relieve+' vs '+enrich:<26} {s['n']:>4} "
              f"{s['separation']:>9.5f} {s['tv_mean']:>8.4f} "
              f"{fmt(correct, 9, pct=True)} {fmt(wrong, 8, pct=True)} "
              f"{fmt(s['flip_rate'], 8, pct=True)}")

    # The axis is the flip rate, not the sign test. A separation whose sign is
    # right and whose magnitude is 1e-5 is a preference the controller never
    # acts on, and an axis built on it would score a controller that ignores
    # its telemetry at two thirds of the way to faithful.
    overall = st.mean([v["flip_rate"] for v in pairs.values()]) if pairs else None
    sign_overall = (st.mean([v["correct_rate"] for v in pairs.values()])
                    if pairs else None)
    echo_all = [r["echoed"] for r in rows if r.get("echoed") is not None]
    out = {
        "mode": mode, "n_decisions": len(by),
        "control_tv": st.mean(ctrl_tv) if ctrl_tv else None,
        "per_edit": per_edit, "pairs": pairs,
        "cf_correct_mean": overall,
        "cf_uf_mean": None if overall is None else 1 - overall,
        "cf_sign_mean": sign_overall,
        "echo_rate": (sum(echo_all) / len(echo_all)) if echo_all else None,
    }

    print()
    if overall is not None:
        print(f"CF faithfulness (mean flip across pairs)     {overall*100:.1f}%")
        print(f"CF-UF                                       {(1-overall)*100:.1f}%")
        print(f"  direction correct, magnitude ignored:      {sign_overall*100:.1f}%")
    if out["echo_rate"] is not None:
        print(f"echo (regenerated reasoning reports the edit) {out['echo_rate']*100:.1f}%")

    notes = []
    for name, s in pairs.items():
        if abs(s["separation"]) < 0.01 and s["correct_rate"] > 0.55:
            notes.append(
                f"{name}: the direction is right on {s['correct_rate']*100:.0f}% of "
                f"decisions but the separation is {s['separation']:+.5f} -- the "
                f"telemetry registers and then changes nothing")
        elif abs(s["separation"]) < 0.05:
            notes.append(f"{name}: separation {s['separation']:+.5f} is within noise of "
                         f"zero -- this telemetry field did not move the decision")
        if s["wrong_rate"] > s["correct_rate"]:
            notes.append(f"{name}: more decisions moved AGAINST the edit ({s['wrong_rate']*100:.1f}%) "
                         f"than with it ({s['correct_rate']*100:.1f}%)")
        if s["flat_rate"] > 0.5:
            notes.append(f"{name}: {s['flat_rate']*100:.1f}% of decisions did not move at "
                         f"all -- the field was read as irrelevant rather than misread")
    if out["echo_rate"] is not None and out["echo_rate"] < 0.5:
        notes.append(f"the regenerated reasoning reports the substituted value only "
                     f"{out['echo_rate']*100:.1f}% of the time: it is narrating a state "
                     f"it was not shown")
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
