#!/usr/bin/env python3
"""Replay every recorded decision under each intervention and re-score it.

Needs a served model and nothing else -- no simulator, no GPU-side state. A
decision is replayed by rebuilding the exact prompt the controller sent, with
the reasoning swapped for a perturbed version, and asking for the distribution
over the same action tokens.

The original arm doubles as the soundness check on the whole procedure: scoring
is deterministic, so re-scoring unmodified reasoning must reproduce the recorded
distribution. Where it does not, the replay is not faithful to what the model
saw and every other arm is uninterpretable, so that is reported first.

    ./rescore.py <run-dir>/llm --llm-base-url http://127.0.0.1:8000/v1 \\
        --llm-model csf-llm -o rescored.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "CONTROLLER"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import interventions as iv
from controller.backends import OpenAICompatBackend


def load_decisions(run_dir: Path) -> list[dict]:
    f = next(iter(sorted(run_dir.rglob("decisions.jsonl"))), None)
    if f is None:
        raise SystemExit(f"no decisions.jsonl under {run_dir}")
    return [json.loads(l) for l in f.read_text().splitlines() if l.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--llm-base-url", required=True)
    ap.add_argument("--llm-model", required=True)
    ap.add_argument("--llm-api-key", default="local")
    ap.add_argument("-o", "--out", type=Path, default=Path("rescored.jsonl"))
    ap.add_argument("--only", nargs="*", default=None,
                    help="restrict to these interventions")
    ap.add_argument("--limit", type=int, default=None,
                    help="first N decisions only (for a smoke test)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rows = load_decisions(args.run_dir)
    if args.limit:
        rows = rows[: args.limit]
    pool = [r["reasoning"] for r in rows if r.get("reasoning")]
    names = args.only or list(iv.INTERVENTIONS)
    backend = OpenAICompatBackend(base_url=args.llm_base_url, model=args.llm_model,
                                  api_key=args.llm_api_key)
    rng = random.Random(args.seed)

    print(f"{len(rows)} decisions x {len(names)} interventions "
          f"= {len(rows)*len(names)} scoring calls")
    started = time.time()
    written = skipped = 0
    with args.out.open("w", encoding="utf-8") as fh:
        for i, r in enumerate(rows):
            reasoning = r.get("reasoning")
            if not reasoning:
                skipped += 1
                continue
            try:
                head = iv.split_prompt(r["prompt"], reasoning)
            except ValueError as exc:
                print(f"  period {r['period']}: {exc}; skipped")
                skipped += 1
                continue

            option_ids = [oid for oid, _ in r["decision"]["options"]]
            legal_ids = list(r["decision"]["distribution"])

            for name in names:
                modified = iv.INTERVENTIONS[name](reasoning, pool=pool, rng=rng)
                # A corruption that matched nothing is not a corruption; recording
                # it as one would dilute the effect with untouched decisions.
                if name.startswith("corrupt") and modified is not None \
                        and iv.corrupt(reasoning) == reasoning:
                    continue
                prompt = iv.rebuild(head, modified)
                try:
                    dist = backend.score(prompt, option_ids)
                except Exception as exc:
                    print(f"  period {r['period']} / {name}: scoring failed ({exc})")
                    continue
                fh.write(json.dumps({
                    "period": r["period"],
                    "intervention": name,
                    "action_recorded": r["decision"]["action"],
                    "distribution_recorded": r["decision"]["distribution"],
                    "distribution_rescored": dist,
                    "legal_ids": legal_ids,
                    "options": r["decision"]["options"],
                    "reasoning_chars": 0 if modified is None else len(modified),
                }) + "\n")
                written += 1
            if (i + 1) % 20 == 0:
                rate = written / max(1e-9, time.time() - started)
                print(f"  {i+1}/{len(rows)} decisions, {written} calls, {rate:.1f}/s")

    print(f"wrote {written} rows to {args.out} ({skipped} decisions skipped) "
          f"in {(time.time()-started)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
