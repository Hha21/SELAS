#!/usr/bin/env python3
"""Ask a simulator to predict the controller's action under each condition.

Four scoring calls per recorded decision and no simulator run: the prompt the
controller sent is rebuilt from the stored messages, edited down to the
condition (see conditions.py), and scored for the distribution over the same
action options. 105 decisions x 4 conditions is ~420 calls.

The simulator is deliberately not the controller. Scoring a model on its own
reasoning measures self-consistency, which is near-total by construction and
says nothing about whether the explanation would help anyone else. A smaller
instruct model from the same family keeps the chat template and the tokenizer
family fixed while genuinely not knowing what the controller was thinking.

Run the controller's own model too, with --label, if a self-simulation ceiling
is wanted: it bounds how much of any shortfall is the explanation and how much
is the simulator being weaker at the task.

    ./simulate.py <run-dir>/llm --llm-base-url http://127.0.0.1:8000/v1 \\
        --llm-model student --label gemma-3-12b-it -o simulated.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "CONTROLLER"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import conditions as C
import legality
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
    ap.add_argument("--label", default=None,
                    help="name of the simulator, recorded on every row "
                         "(defaults to --llm-model)")
    ap.add_argument("-o", "--out", type=Path, default=Path("simulated.jsonl"))
    ap.add_argument("--only", nargs="*", default=None, help="restrict to these conditions")
    ap.add_argument("--limit", type=int, default=None, help="first N decisions only")
    args = ap.parse_args()

    rows = load_decisions(args.run_dir)
    if args.limit:
        rows = rows[: args.limit]
    names = args.only or list(C.CONDITIONS)
    label = args.label or args.llm_model
    backend = OpenAICompatBackend(base_url=args.llm_base_url, model=args.llm_model,
                                  api_key=args.llm_api_key)

    usable = [r for r in rows if r.get("messages") and r.get("reasoning")]
    print(f"simulator {label}")
    print(f"{len(usable)} decisions x {len(names)} conditions "
          f"= {len(usable)*len(names)} scoring calls "
          f"({len(rows)-len(usable)} decisions without reasoning skipped)")

    started = time.time()
    written = 0
    with args.out.open("w", encoding="utf-8") as fh:
        for i, r in enumerate(usable):
            options = dict(r["decision"]["options"])
            option_ids = list(options)
            legal_ids = legality.legal_ids(r)
            for name in names:
                try:
                    msgs = C.CONDITIONS[name](r["messages"])
                except ValueError as exc:
                    print(f"  period {r['period']} / {name}: {exc}; skipped")
                    continue
                try:
                    dist = backend.score_chat(msgs, option_ids)
                except Exception as exc:
                    print(f"  period {r['period']} / {name}: scoring failed ({exc})")
                    continue
                fh.write(json.dumps({
                    "period": r["period"],
                    "simulator": label,
                    "condition": name,
                    # The target: what the controller actually did. There is no
                    # gold action, so the controller's decision is the label.
                    "action_recorded": r["decision"]["action"],
                    "distribution_recorded": r["decision"]["distribution"],
                    "distribution_simulated": dist,
                    "legal_ids": legal_ids,
                    "options": r["decision"]["options"],
                    "missing_ids": list(backend.last_missing_ids),
                }) + "\n")
                written += 1
            if (i + 1) % 20 == 0:
                rate = written / max(1e-9, time.time() - started)
                print(f"  {i+1}/{len(usable)} decisions, {written} calls, {rate:.1f}/s")

    print(f"wrote {written} rows to {args.out} "
          f"in {(time.time()-started)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
