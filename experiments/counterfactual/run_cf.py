#!/usr/bin/env python3
"""Replay each decision against edited telemetry.

Two modes, answering different questions.

``score``    edit the observation, keep the reasoning the controller actually
             wrote, re-score. The reasoning now describes a state that is not
             in the prompt, so this asks which of the two the action follows.
             One call per decision per edit.

``generate`` edit the observation, regenerate the reasoning from it, then
             score. This is the counterfactual proper -- a decision taken on
             the edited world -- and it is the only mode that can ask whether
             the new reasoning reports the value that was actually substituted.

Both include an identity edit. In ``score`` it is the control arm: scoring is
deterministic, so re-scoring an unedited decision must reproduce the recorded
distribution, and where it does not nothing else in the file is interpretable.
In ``generate`` it is the baseline the edits are contrasted against, because
otherwise the difference between arms would confound the edit with the
regeneration.

Generation runs at temperature 0 by default, unlike the live controller. The
measurement is a within-decision contrast between two opposing edits, and
sampling noise at 0.7 would sit on top of exactly the difference being
measured.

    ./run_cf.py <run-dir>/llm --mode generate \\
        --llm-base-url http://127.0.0.1:8000/v1 --llm-model csf-llm -o cf.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "CONTROLLER"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "faithfulness"))

import edits as E
import interventions as iv
import legality
from controller.backends import OpenAICompatBackend

STOP = ["\nAction:", "\n---"]


def load_decisions(run_dir: Path) -> list[dict]:
    f = next(iter(sorted(run_dir.rglob("decisions.jsonl"))), None)
    if f is None:
        raise SystemExit(f"no decisions.jsonl under {run_dir}")
    return [json.loads(l) for l in f.read_text().splitlines() if l.strip()]


def with_block(messages: list[dict], block: str) -> list[dict]:
    out = [dict(m) for m in messages]
    out[-2]["content"] = block
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--llm-base-url", required=True)
    ap.add_argument("--llm-model", required=True)
    ap.add_argument("--llm-api-key", default="local")
    ap.add_argument("--mode", choices=["score", "generate"], default="score")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=200)
    ap.add_argument("-o", "--out", type=Path, default=Path("cf.jsonl"))
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    rows = load_decisions(args.run_dir)
    if args.limit:
        rows = rows[: args.limit]
    usable = [r for r in rows if r.get("messages") and r.get("reasoning")]
    backend = OpenAICompatBackend(base_url=args.llm_base_url, model=args.llm_model,
                                  api_key=args.llm_api_key)

    arms = ["original"] + list(E.EDITS)
    per = 2 if args.mode == "generate" else 1
    print(f"mode {args.mode}, temperature {args.temperature}")
    print(f"{len(usable)} decisions x {len(arms)} arms x {per} call(s) "
          f"= {len(usable)*len(arms)*per}")

    started = time.time()
    written = 0
    with args.out.open("w", encoding="utf-8") as fh:
        for i, r in enumerate(usable):
            block = r["messages"][-2]["content"]
            dimmer = E.current_dimmer(block)
            options = r["decision"]["options"]
            option_ids = [oid for oid, _ in options]
            legal_ids = legality.legal_ids(r)

            for arm in arms:
                if arm == "original":
                    new_block, meta = block, {"field": None, "target": None,
                                              "edit": None, "echo": None}
                    direction = "none"
                else:
                    fn, direction = E.EDITS[arm]
                    res = fn(block)
                    if res is None:          # field absent from this block
                        continue
                    new_block, meta = res

                msgs = with_block(r["messages"], new_block)
                reasoning_new = None
                if args.mode == "generate":
                    try:
                        reasoning_new = backend.generate_chat(
                            msgs[:-1], max_tokens=args.max_tokens,
                            temperature=args.temperature, stop=STOP)
                    except Exception as exc:
                        print(f"  period {r['period']} / {arm}: generation failed ({exc})")
                        continue
                    msgs = iv.rebuild_messages(msgs, reasoning_new)

                try:
                    dist = backend.score_chat(msgs, option_ids)
                except Exception as exc:
                    print(f"  period {r['period']} / {arm}: scoring failed ({exc})")
                    continue

                # Whether the regenerated reasoning reports the substituted
                # value. Only meaningful when the reasoning was regenerated from
                # the edited block; held reasoning cannot echo an edit it never
                # saw.
                echoed = None
                if args.mode == "generate" and meta.get("echo"):
                    echoed = meta["echo"] in (reasoning_new or "")

                fh.write(json.dumps({
                    "period": r["period"],
                    "mode": args.mode,
                    "arm": arm,
                    "direction": direction,
                    "field": meta["field"],
                    "target": meta["target"],
                    "edit": meta["edit"],
                    "echo_token": meta.get("echo"),
                    "echoed": echoed,
                    "dimmer": dimmer,
                    "action_recorded": r["decision"]["action"],
                    "distribution_recorded": r["decision"]["distribution"],
                    "distribution_cf": dist,
                    "legal_ids": legal_ids,
                    "options": options,
                    "reasoning_new": reasoning_new,
                }) + "\n")
                written += 1
            if (i + 1) % 10 == 0:
                rate = written / max(1e-9, time.time() - started)
                print(f"  {i+1}/{len(usable)} decisions, {written} rows, {rate:.1f}/s")

    print(f"wrote {written} rows to {args.out} in {(time.time()-started)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
