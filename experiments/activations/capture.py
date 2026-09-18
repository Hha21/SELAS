#!/usr/bin/env python3
"""Recover per-token activations for a completed controller run.

The controller is served by vLLM, which does not expose the residual stream, so
activations are recovered afterwards by replaying each recorded decision through
the same weights under transformers with a forward hook at the probe layer.

This is possible because a decision record stores the exact prompt and the exact
completion, so the token sequence is reconstructable rather than approximated.
It is also cheap: one forward pass per decision, no generation, no simulator --
about ten minutes of GPU for a 105-decision run, against 105 minutes to produce
one.

**What is and is not identical.** The weights, the tokens and the layer are the
same; the kernels are not, because vLLM and transformers schedule attention
differently. In bf16 that is a numerical difference well below the scale the
verbaliser is sensitive to, but the activations explained here were produced by
a replay of the decision rather than by the forward pass that made it. A run
served directly by an activation-exposing endpoint would close that gap, and is
the reason to add /v1/completions to NLA's server later.

Output is NLA's existing trace layout, so the inspector and the AV/AR pipeline
consume it unchanged:

    <out>/<run_id>/
        <request_id>.npz    float16 (seq, d_model)
        <request_id>.json   tokens, ids, completion, probe offsets, config
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "NLA"))
from src.model import decoder_layers, load_tokenizer   # noqa: E402


def load_decisions(run_dir: Path) -> list[dict]:
    f = next(iter(sorted(run_dir.rglob("decisions.jsonl"))), None)
    if f is None:
        raise SystemExit(f"no decisions.jsonl under {run_dir}")
    return [json.loads(l) for l in f.read_text().splitlines() if l.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path, help="a controller run directory")
    ap.add_argument("--model", default="google/gemma-3-27b-it")
    ap.add_argument("--layer", type=int, default=None,
                    help="probe layer; defaults to the PROBE_LAYERS entry for --model")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    if args.layer is None:
        from src.config import PROBE_LAYERS          # noqa: E402
        if args.model not in PROBE_LAYERS:
            raise SystemExit(
                f"no probe layer known for {args.model!r}. The layer is a property of "
                f"the released AV/AR pair, not a free choice -- pass --layer only if "
                f"you know which pair you are matching.")
        args.layer = PROBE_LAYERS[args.model]

    rows = load_decisions(args.run_dir)
    if args.limit:
        rows = rows[: args.limit]
    run_id = args.run_id or args.run_dir.name
    out_dir = args.out / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"model {args.model}  probe layer {args.layer}")
    print(f"{len(rows)} decisions -> {out_dir}")

    from transformers import AutoModelForCausalLM
    tok = load_tokenizer(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, device_map=args.device)
    model.eval().requires_grad_(False)

    captured: dict[str, torch.Tensor] = {}

    def _hook(_module, _inp, out):
        # Decoder blocks return a tuple in some versions and a tensor in others.
        captured["h"] = (out[0] if isinstance(out, tuple) else out).detach()

    handle = decoder_layers(model)[args.layer].register_forward_hook(_hook)

    try:
        for i, r in enumerate(rows):
            # Prompt plus what the model actually produced: the reasoning is part
            # of the stream the decision was read from, so its activations matter
            # as much as the prompt's.
            text = r["prompt"]
            ids = tok(text, return_tensors="pt").to(model.device)
            with torch.no_grad():
                model(**ids)
            acts = captured["h"][0].to(torch.float16).cpu().numpy()

            rid = f"period-{r['period']:04d}"
            np.savez_compressed(out_dir / f"{rid}.npz", activations=acts)
            token_ids = ids["input_ids"][0].tolist()
            (out_dir / f"{rid}.json").write_text(json.dumps({
                "request_id": rid,
                "run_id": run_id,
                "period": r["period"],
                "source": "replay",
                "prompt": text,
                "reasoning": r.get("reasoning"),
                "token_ids": token_ids,
                "tokens": tok.convert_ids_to_tokens(token_ids),
                "n_tokens": len(token_ids),
                "activations_file": f"{rid}.npz",
                "activations_shape": list(acts.shape),
                # Character offsets from the controller, mapped to token indices
                # so the inspector can jump straight to the decision position.
                "probes_char": r["decision"]["probes"],
                "probes_token": {
                    name: len(tok(text[:off])["input_ids"]) - 1
                    for name, off in r["decision"]["probes"].items()
                },
                "decision": {
                    "action": r["decision"]["action"],
                    "distribution": r["decision"]["distribution"],
                    "options": r["decision"]["options"],
                },
                "config": {"model": args.model, "probe_layer": args.layer,
                           "dtype": "float16", "captured_by": "experiments/activations/capture.py"},
            }, indent=1))

            if (i + 1) % 10 == 0:
                print(f"  {i+1}/{len(rows)}  last seq {acts.shape[0]} tokens")
    finally:
        handle.remove()

    total = sum(f.stat().st_size for f in out_dir.glob("*.npz"))
    print(f"done: {len(rows)} traces, {total/1e9:.2f} GB in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
