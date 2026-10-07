#!/usr/bin/env python3
"""Summarise edit_patch.py: does the choice follow the edited explanation?

Per direction (nla, meandiff, random) and strength alpha, over every decision
and edited target, split by whether the controller did nothing or acted:

    to target   the most likely legal option after the patch is the target
    changed     it differs from the unpatched choice
    dlogp       log p(target) after the patch minus before (natural log)

Read the control first: the unpatched replay should choose the recorded action
(it is the same model in transformers rather than vLLM, so a few near-ties may
differ) and see the captured vector (cosine ~1). Intervals resample runs.

    python analyse_patch.py PATCH_DIR [-o patch.json]
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "replay"))
from pool_battery import pooled  # noqa: E402


def top(d: dict[str, float]) -> str | None:
    return max(d, key=d.__getitem__) if d else None


def fmt(s: dict | None, pct: bool = True) -> str:
    if s is None:
        return f"{'-':>22}"
    if pct:
        return f"{100*s['rate']:5.1f}% [{100*s['lo']:4.1f}, {100*s['hi']:5.1f}]"
    return f"{s['rate']:+6.2f} [{s['lo']:+5.2f}, {s['hi']:+5.2f}]"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("patch_dir", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()
    rows = [json.loads(l) for l in (args.patch_dir / "patched.jsonl").read_text().splitlines() if l.strip()]

    base = {(r["run"], r["period"]): r for r in rows if r["cond"] == "unpatched"}
    agree = [top(r["dist"]) == r["chosen"] for r in base.values()]
    cos = [r["h_cos_captured"] for r in base.values()]
    print(f"control: {len(base)} decisions; the unpatched replay chooses the recorded action in "
          f"{100*st.mean(agree):.1f}%; cosine to the captured vector median {st.median(cos):.4f} "
          f"(min {min(cos):.4f})")

    # (cond, alpha, measure, split) -> run -> values
    acc: dict = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["cond"] == "unpatched":
            continue
        b = base[(r["run"], r["period"])]
        p0 = b["dist"].get(r["target"], 0.0)
        p1 = r["dist"].get(r["target"], 0.0)
        split = "no_op" if r["action"] == "no_op" else "action"
        vals = {"to target": top(r["dist"]) == r["target"],
                "changed": top(r["dist"]) != top(b["dist"]),
                "dlogp": math.log(max(p1, 1e-12)) - math.log(max(p0, 1e-12))}
        for m, v in vals.items():
            for s in (split, "all"):
                acc[(r["cond"], r["alpha"], m, s)][r["run"]].append(v)

    summary = {}
    for key, per_run in acc.items():
        summary["|".join(map(str, key))] = pooled(list(per_run.values()))
    conds = [c for c in ("nla", "meandiff", "random") if any(k[0] == c for k in acc)]
    alphas = sorted({k[1] for k in acc})
    for m in ("to target", "changed", "dlogp"):
        print(f"\n{m}")
        print(f"{'direction':<10} {'alpha':>5}  {'no-op':>22}  {'action':>22}  {'n':>6}")
        for c in conds:
            for a in alphas:
                s = [summary.get(f"{c}|{a}|{m}|{sp}") for sp in ("no_op", "action", "all")]
                n = s[2]["n"] if s[2] else 0
                print(f"{c:<10} {a:>5g}  {fmt(s[0], m != 'dlogp')}  {fmt(s[1], m != 'dlogp')}  {n:>6}")
    if args.out:
        args.out.write_text(json.dumps({"control_agreement": st.mean(agree),
                                        "cos_captured_median": st.median(cos),
                                        "measures": summary}, indent=1))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
