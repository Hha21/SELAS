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

    def paraphraser(prompt: str) -> str:
        """Reword via the same endpoint. Low temperature: the task is to restate,
        not to elaborate, and a creative paraphrase changes the meaning it is
        supposed to preserve."""
        return backend.generate_chat(
            [{"role": "user", "content": prompt}], max_tokens=300, temperature=0.3,
            stop=["\nAction:"])

    print(f"{len(rows)} decisions x {len(names)} interventions "
          f"= {len(rows)*len(names)} scoring calls")
    started = time.time()
    written = skipped = 0
    # Per-arm count of decisions an intervention could not touch. Reported at
    # the end: an arm that matched nothing has an n far below the others, and
    # that has to be visible rather than inferred from a smaller denominator.
    skipped_noop: dict[str, int] = {}
    with args.out.open("w", encoding="utf-8") as fh:
        for i, r in enumerate(rows):
            reasoning = r.get("reasoning")
            if not reasoning:
                skipped += 1
                continue
            chat = bool(r.get("messages"))
            head = None
            if not chat:
                try:
                    head = iv.split_prompt(r["prompt"], reasoning)
                except ValueError as exc:
                    print(f"  period {r['period']}: {exc}; skipped")
                    skipped += 1
                    continue

            option_ids = [oid for oid, _ in r["decision"]["options"]]
            legal_ids = list(r["decision"]["distribution"])

            for name in names:
                modified = iv.INTERVENTIONS[name](
                    reasoning, pool=pool, rng=rng, paraphraser=paraphraser)
                # An intervention that came back unchanged is not an
                # intervention, and recording it as one dilutes the effect with
                # untouched decisions. This was previously checked only for
                # corrupt and paraphrase, which was enough while every arm used
                # the scaffold; free-form reasoning has no fields to cut, so the
                # truncation arms silently returned the original too.
                if name != "original" and modified is not None \
                        and modified.strip() == reasoning.strip():
                    skipped_noop[name] = skipped_noop.get(name, 0) + 1
                    continue
                try:
                    if chat:
                        dist = backend.score_chat(
                            iv.rebuild_messages(r["messages"], modified), option_ids)
                    else:
                        dist = backend.score(iv.rebuild(head, modified), option_ids)
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
                    "format": "chat" if chat else "completion",
                }) + "\n")
                written += 1
            if (i + 1) % 20 == 0:
                rate = written / max(1e-9, time.time() - started)
                print(f"  {i+1}/{len(rows)} decisions, {written} calls, {rate:.1f}/s")

    print(f"wrote {written} rows to {args.out} ({skipped} decisions skipped) "
          f"in {(time.time()-started)/60:.1f} min")
    if skipped_noop:
        print("interventions that left the reasoning unchanged (not recorded):")
        for name, n in sorted(skipped_noop.items(), key=lambda kv: -kv[1]):
            print(f"  {name:<14} {n:>4} of {len(rows)} decisions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
