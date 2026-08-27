#!/usr/bin/env python
"""
Pick the qualitative examples for the report from samples.csv.

The point is not to hand-pick a flattering explanation and an embarrassing one.
It is to let the *reconstruction metric* choose: the best example is the highest
cosine, the worst is the lowest. That way the figure and the number agree, and
the "bad" case is bad by the paper's own measure rather than by taste.

The low-cosine cases are the interesting ones for Section 2.3: an explanation
that reads fluently but reconstructs poorly is precisely plausible-but-unfaithful
-- the CoT failure mode, caught here by a metric CoT does not have.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES  = Path(__file__).parent / "results"


def resolve(doc: str, seq_len: int) -> str:
    """Full traces/<run>/<req> path. Older rows stored a bare req name, which is
    ambiguous across runs, so disambiguate on sequence length."""
    if "/" in doc:
        return doc
    import json
    for p in sorted((ROOT / "traces").glob(f"run-*/{doc}")):
        if len(json.loads(p.read_text()).get("token_ids") or []) == seq_len:
            return str(p.relative_to(ROOT / "traces"))
    return doc + "  (run dir unresolved)"


def main():
    rows = list(csv.DictReader((RES / "samples.csv").open()))
    for r in rows:
        r["cosine"] = float(r["cosine"])
        r["cosine_shuffled"] = float(r["cosine_shuffled"])
        r["fve_pooled"] = float(r["fve_pooled"])

    for cond in ("polaris", "fineweb"):
        sel = sorted([r for r in rows if r["condition"] == cond],
                     key=lambda r: r["cosine"])
        if not sel:
            continue
        print("=" * 78)
        print(f"{cond.upper()}  (n={len(sel)})")
        for tag, picks in (("WORST — fluent but unfaithful", sel[:2]),
                           ("BEST  — faithful", sel[-2:][::-1])):
            print(f"\n--- {tag} ---")
            for r in picks:
                where = resolve(r["doc"], int(r["seq_len"])) if cond == "polaris" else r["doc"]
                print(f"  {where}  token {r['position']} of {r['seq_len']}"
                      f"   [{r['source']}]")
                print(f"  cosine {r['cosine']:+.3f}   shuffled "
                      f"{r['cosine_shuffled']:+.3f}   FVE {r['fve_pooled']:+.3f}")
                txt = " ".join(r["explanation"].split())
                print(f"  \"{txt[:330]}{'...' if len(txt) > 330 else ''}\"\n")


if __name__ == "__main__":
    main()
