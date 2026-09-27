#!/usr/bin/env python3
"""NLA pilot: what the controller's layer-41 activations say at its decision
positions, and whether the words can be trusted.

Three phases on one GPU, each model freed before the next is loaded:

  1. capture    gemma-3-27b-it replays every recorded decision (prompt, the
                reasoning it wrote, "Action:") and the layer-41 residual stream
                is kept at the probe positions only -- the end of the live
                state (P0_state_end), the opened model turn before any
                reasoning (P0_turn), the end of each reasoning field, and the
                position the action letter was read after (P_action).
  2. verbalise  the released AV explains each vector (greedy).
  3. score      the released AR reconstructs each vector from its explanation;
                fve_nrm says how much of the vector the words carry.

Before any of that is interpreted, the same code reproduces the pair's
published worked example (kitft/nla-inference, gemma27b_layer41_step6000):
the raw norms of the 22 prompt tokens of "What is the capital of France and
what is it known for?" (a wrong layer or a doubled <bos> changes them), and the
fve_nrm of their decodes. ``reference.json`` records the comparison and the run
fails if the norms do not match.

    python pilot.py RUN_DIR [RUN_DIR ...] -o OUT [--limit N]

Output in OUT: vectors.npy (float32, one row per probe), index.jsonl (what each
row is), explanations.jsonl (AV text and AR scores per row), reference.json.
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "activations"))
sys.path.insert(0, str(HERE.parent / "faithfulness"))

import legality  # noqa: E402
from nla_pair import AR_REPO, AV_REPO, LAYER, Reconstructor, Verbaliser, extract_explanation  # noqa: E402
from render import locate_probes, probe_token_indices, render_chat  # noqa: E402

TARGET = "google/gemma-3-27b-it"

# The published example: prompt-token raw norms at layer 41 and the fve_nrm of
# their greedy decodes (SGLang, bf16). Positions 0-3 are template tokens the
# pair rarely saw in training; the example's own summary starts at 4.
REFERENCE_PROMPT = "What is the capital of France and what is it known for?"
REFERENCE = [  # (token, ||v||, fve_nrm)
    ("<bos>", 860335.9, 0.919), ("<start_of_turn>", 33343.8, -8.371), ("user", 61947.8, 0.352),
    ("\n", 72205.9, 0.481), ("What", 52619.5, 0.778), (" is", 53726.3, 0.810),
    (" the", 27920.3, 0.758), (" capital", 53569.4, 0.855), (" of", 45332.6, 0.837),
    (" France", 53510.3, 0.932), (" and", 39577.5, 0.812), (" what", 54626.8, 0.844),
    (" is", 51029.3, 0.792), (" it", 52223.1, 0.757), (" known", 57561.9, 0.899),
    (" for", 47954.2, 0.766), ("?", 47212.3, 0.603), ("<end_of_turn>", 54324.4, 0.164),
    ("\n", 45986.6, 0.761), ("<start_of_turn>", 47263.0, 0.807), ("model", 57081.1, 0.670),
    ("\n", 53109.1, 0.773),
]
REFERENCE_FRANCE = ("Educational/informational article format: a structured answer or quiz "
                    "format about a country, likely France, or a capital city.")


def _free() -> None:
    """Return freed GPU memory; the caller must have dropped its references."""
    gc.collect()
    torch.cuda.empty_cache()


def load_decisions(run_dir: Path) -> list[dict]:
    f = next(iter(sorted(run_dir.rglob("decisions.jsonl"))), None)
    if f is None:
        raise SystemExit(f"no decisions.jsonl under {run_dir}")
    rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return [r for r in rows if r.get("messages")]


def capture(runs: list[Path], limit: int | None, out: Path) -> tuple[np.ndarray, list[dict]]:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(TARGET)
    model = AutoModelForCausalLM.from_pretrained(TARGET, dtype=torch.bfloat16, device_map="cuda")
    model.eval().requires_grad_(False)
    dev = model.get_input_embeddings().weight.device

    def layer_states(ids: list[int]) -> np.ndarray:
        with torch.no_grad():
            hs = model(input_ids=torch.tensor([ids], device=dev), output_hidden_states=True,
                       use_cache=False).hidden_states
        n_layers = len(hs) - 1
        assert n_layers == 62, f"expected 62 decoder layers, got {n_layers}"
        return hs[LAYER + 1][0].float().cpu().numpy()   # hs[0] is the embeddings

    vecs, index = [], []
    # The worked example, all 22 prompt positions.
    ref_ids = tok.apply_chat_template([{"role": "user", "content": REFERENCE_PROMPT}],
                                      tokenize=True, add_generation_prompt=True)
    ref_ids = list(ref_ids["input_ids"] if hasattr(ref_ids, "keys") else ref_ids)
    h = layer_states(ref_ids)
    toks = tok.convert_ids_to_tokens(ref_ids)
    for p in range(len(ref_ids)):
        vecs.append(h[p]); index.append({"source": "reference", "pos": p, "token": toks[p],
                                         "norm": float(np.linalg.norm(h[p]))})

    started = time.time()
    for run in runs:
        rows = load_decisions(run)[:limit]
        for n, r in enumerate(rows):
            text = render_chat(tok, r["messages"])
            enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
            probes = probe_token_indices(enc["offset_mapping"], locate_probes(text, r["messages"]))
            h = layer_states(enc["input_ids"])
            toks = tok.convert_ids_to_tokens(enc["input_ids"])
            dist = r["decision"]["distribution"]
            for name, p in sorted(probes.items(), key=lambda kv: kv[1]):
                vecs.append(h[p])
                index.append({
                    "source": "run", "run": f"{run.parent.name}/{run.name}", "period": r["period"],
                    "probe": name, "pos": p, "token": toks[p], "n_tokens": len(toks),
                    "norm": float(np.linalg.norm(h[p])),
                    "action": r["decision"]["action"], "distribution": dist,
                    "options": r["decision"]["options"], "legal_ids": legality.legal_ids(r),
                    "observation": {k: r["observation"].get(k) for k in
                                    ("servers", "active_servers", "dimmer", "avg_rt", "arrival_rate")},
                    "reasoning": r.get("reasoning"),
                })
            if (n + 1) % 25 == 0:
                print(f"  {run.name}: {n + 1}/{len(rows)} decisions, {time.time() - started:.0f}s", flush=True)
    del model, layer_states
    _free()
    V = np.stack(vecs).astype(np.float32)
    np.save(out / "vectors.npy", V)
    (out / "index.jsonl").write_text("".join(json.dumps(i) + "\n" for i in index))
    return V, index


def reference_report(index: list[dict], expl: list[dict], out: Path) -> bool:
    rows = []
    for i, x in zip(index, expl):
        if i["source"] != "reference":
            continue
        tok_ref, norm_ref, fve_ref = REFERENCE[i["pos"]] if i["pos"] < len(REFERENCE) else (None, None, None)
        rows.append({"pos": i["pos"], "token": i["token"], "token_ref": tok_ref,
                     "norm": i["norm"], "norm_ref": norm_ref,
                     "norm_rel_err": (abs(i["norm"] - norm_ref) / norm_ref) if norm_ref else None,
                     "fve_nrm": x["fve_nrm"], "fve_nrm_ref": fve_ref,
                     "explanation": x["explanation"]})
    body = [r for r in rows if r["pos"] >= 4]
    worst = max(r["norm_rel_err"] for r in rows)
    ok = len(rows) == len(REFERENCE) and worst < 0.03
    rep = {
        "ok": ok,
        "tokens_match": [r["token"] for r in rows] == [t for t, _, _ in REFERENCE],
        "norm_max_rel_err": worst,
        "fve_nrm_mean_pos4plus": float(np.mean([r["fve_nrm"] for r in body])),
        "fve_nrm_mean_pos4plus_ref": float(np.mean([r["fve_nrm_ref"] for r in body])),
        "france_explanation_ref": REFERENCE_FRANCE,
        "positions": rows,
    }
    (out / "reference.json").write_text(json.dumps(rep, indent=1))
    print(f"reference: tokens match {rep['tokens_match']}, max norm error {worst:.2%}, "
          f"fve_nrm (pos 4+) {rep['fve_nrm_mean_pos4plus']:.3f} vs published "
          f"{rep['fve_nrm_mean_pos4plus_ref']:.3f}")
    fr = next(r for r in rows if r["pos"] == 9)
    print(f"  ' France' decode: {fr['explanation'][:160]!r}")
    print(f"  published      : {REFERENCE_FRANCE[:160]!r}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", type=Path, nargs="+", help="controller run directories (chat format)")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=None, help="decisions per run")
    ap.add_argument("--max-new-tokens", type=int, default=200)
    ap.add_argument("--batch-size", type=int, default=32)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    if (args.out / "vectors.npy").exists():
        V = np.load(args.out / "vectors.npy")
        index = [json.loads(l) for l in (args.out / "index.jsonl").read_text().splitlines()]
        print(f"capture: reusing {len(index)} vectors")
    else:
        V, index = capture(args.runs, args.limit, args.out)
        print(f"capture: {len(index)} vectors in {time.time() - t0:.0f}s", flush=True)

    t1 = time.time()
    av = Verbaliser(AV_REPO)
    raw = av.explain(V, max_new_tokens=args.max_new_tokens, batch_size=args.batch_size)
    del av
    _free()
    print(f"verbalise: {len(raw)} decodes in {time.time() - t1:.0f}s", flush=True)

    t2 = time.time()
    ar = Reconstructor(AR_REPO)
    texts = [extract_explanation(t) for t in raw]
    s = ar.score(texts, V)
    del ar
    _free()
    print(f"score: {time.time() - t2:.0f}s", flush=True)

    expl = [{"i": k, "raw": raw[k], "explanation": texts[k], "closed": "</explanation>" in raw[k],
             **{m: float(s[m][k]) for m in ("mse_nrm", "cos", "fve_nrm")}} for k in range(len(raw))]
    (args.out / "explanations.jsonl").write_text("".join(json.dumps(e) + "\n" for e in expl))

    ok = reference_report(index, expl, args.out)
    runs = [(i, e) for i, e in zip(index, expl) if i["source"] == "run"]
    for probe in sorted({i["probe"] for i, _ in runs}):
        f = [e["fve_nrm"] for i, e in runs if i["probe"] == probe]
        print(f"  {probe:14s} n={len(f):4d}  fve_nrm median {np.median(f):.3f}  "
              f"IQR {np.percentile(f, 25):.3f}-{np.percentile(f, 75):.3f}")
    print(f"done in {time.time() - t0:.0f}s -> {args.out}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
