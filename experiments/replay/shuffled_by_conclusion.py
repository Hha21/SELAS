#!/usr/bin/env python3
"""The "another period's reasoning" intervention, split by what the substitute
concluded.

rescore.py draws the substitute at random from the same run, so most
substitutes for a no-op are themselves no-op reasoning, and the pooled flip
rate is mostly the base rate of inaction. Replaying the draw (one
random.Random(seed) per run, consumed only by ``shuffled``, in decision order)
recovers which period each substitute came from; its recorded action is what
the substitute concluded. Reported per split (the decision was a no-op / an
action): the share of decisions whose action changes when the substitute
concluded otherwise, and when it concluded the same kind, pooled over runs
with run-resampled 95% intervals.

    python shuffled_by_conclusion.py DIR [--seed 0] -o shuffled.json

DIR holds one staged run per subdirectory (decisions plus rescored.jsonl), as
pool_battery.py reads.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "faithfulness"))
sys.path.insert(0, str(HERE))
from pool_battery import pooled  # noqa: E402
from rescore import load_decisions  # noqa: E402


def action_of(r: dict) -> str:
    a = r["decision"].get("action")
    return a if isinstance(a, str) else json.dumps(a)


def top(dist: dict) -> str:
    return max(dist, key=dist.get)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", type=Path)
    ap.add_argument("--seed", type=int, default=0, help="rescore.py's --seed")
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()

    acc: dict = defaultdict(lambda: defaultdict(list))   # (split, substitute) -> run -> changed
    for run_dir in sorted(p for p in args.dir.iterdir() if (p / "rescored.jsonl").exists()):
        rows = load_decisions(run_dir)
        pool = [r["reasoning"] for r in rows if r.get("reasoning")]
        source = {}
        for r in rows:
            if r.get("reasoning"):
                source.setdefault(r["reasoning"].strip(), action_of(r))
        rng = random.Random(args.seed)
        substitute = {}
        for r in rows:
            if not r.get("reasoning"):
                continue
            choices = [p for p in pool if p.strip() != r["reasoning"].strip()] or pool
            substitute[r["period"]] = rng.choice(choices)
        for line in (run_dir / "rescored.jsonl").read_text().splitlines():
            x = json.loads(line)
            if x["intervention"] != "shuffled":
                continue
            own = x["action_recorded"]
            sub = source[substitute[x["period"]].strip()]
            split = "no_op" if own == "no_op" else "action"
            same = (sub == "no_op") == (own == "no_op")
            changed = top(x["distribution_rescored"]) != top(x["distribution_recorded"])
            acc[(split, "concludes the same kind" if same else "concludes otherwise")][run_dir.name].append(changed)

    out = {f"{split}|{sub}": pooled(list(per_run.values())) for (split, sub), per_run in sorted(acc.items())}
    for k, v in out.items():
        print(f"{k:40s} {100 * v['rate']:5.1f}% [{100 * v['lo']:.1f}, {100 * v['hi']:.1f}]  n={v['n']}")
    args.out.write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
