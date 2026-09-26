#!/usr/bin/env python3
"""Does the objective change the decision through the reasoning, or around it?

For every recorded decision of a run made under objective FROM, four scored
distributions over the action letters, all at the same state:

    orig     the recorded prompt and reasoning (control: reproduces the run)
    direct   objective swapped to TO, the ORIGINAL reasoning kept
    total    objective swapped to TO, reasoning regenerated under it
    reason   objective kept as FROM, the reasoning regenerated under TO

``total`` is what the other objective would have done here; ``direct`` is how
much of that happens with the written reasoning held fixed -- the part of the
objective's effect that does not pass through the trace; ``reason`` is how
much the new reasoning alone carries under the old objective. If the trace
explains the decision, ``direct`` should be small and ``reason`` close to
``total``.

Regeneration is greedy (temperature 0), as in the runs, with the runs' 200-token
reasoning budget. Needs a server that continues the assistant turn (vLLM).

    python run_mediation.py RUN_DIR --from priority --to priority-no3 \\
        --llm-base-url http://127.0.0.1:8000/v1 --llm-model csf-llm -o mediation.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "CONTROLLER"))
sys.path.insert(0, str(HERE.parent / "faithfulness"))
sys.path.insert(0, str(HERE))

import interventions as iv  # noqa: E402
import legality  # noqa: E402
from controller.backends import OpenAICompatBackend  # noqa: E402
from objective_swap import swap_messages  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--from", dest="old", required=True, help="the objective the run used")
    ap.add_argument("--to", dest="new", required=True, help="the objective to swap in")
    ap.add_argument("--llm-base-url", required=True)
    ap.add_argument("--llm-model", required=True)
    ap.add_argument("--max-reasoning-tokens", type=int, default=200)
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    dec = next(args.run_dir.rglob("decisions.jsonl"))
    rows = [json.loads(l) for l in dec.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r.get("messages") and r.get("reasoning")]
    if args.limit:
        rows = rows[: args.limit]
    backend = OpenAICompatBackend(base_url=args.llm_base_url, model=args.llm_model)

    started, written = time.time(), 0
    with args.out.open("w", encoding="utf-8") as fh:
        for r in rows:
            m = r["messages"]
            ms = r["observation"]["max_servers"]
            ids = [oid for oid, _ in r["decision"]["options"]]
            swapped = swap_messages(m, args.old, args.new, ms)
            try:
                new_reasoning = backend.generate_chat(
                    swapped[:-1], max_tokens=args.max_reasoning_tokens, temperature=0.0,
                    stop=["\nAction:", "\n---"])
                dists = {
                    "orig": backend.score_chat(m, ids),
                    "direct": backend.score_chat(swapped, ids),
                    "total": backend.score_chat(iv.rebuild_messages(swapped, new_reasoning), ids),
                    "reason": backend.score_chat(iv.rebuild_messages(m, new_reasoning), ids),
                }
            except Exception as exc:
                print(f"  period {r['period']}: {exc}")
                continue
            fh.write(json.dumps({
                "period": r["period"],
                "sim_elapsed_s": r["sim_elapsed_s"],
                "objective_from": args.old, "objective_to": args.new,
                "action_recorded": r["decision"]["action"],
                "distribution_recorded": r["decision"]["distribution"],
                "options": r["decision"]["options"],
                "legal_ids": legality.legal_ids(r),
                "observation": {k: r["observation"][k] for k in
                                ("servers", "active_servers", "dimmer", "avg_rt", "arrival_rate")},
                "reasoning_orig": iv.reasoning_from_messages(m),
                "reasoning_new": new_reasoning,
                **{f"dist_{k}": v for k, v in dists.items()},
            }) + "\n")
            written += 1
            if written % 20 == 0:
                print(f"  {written}/{len(rows)} decisions, {time.time() - started:.0f}s")
    print(f"wrote {written} of {len(rows)} decisions -> {args.out}")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
