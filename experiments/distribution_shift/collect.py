#!/usr/bin/env python
"""
Distribution-shift measurement: does the NLA reconstruct worse on the runtime
traces of a self-adaptive system than on the corpus it was trained on?

Two conditions, identical protocol:

  fineweb   FineWeb sample-10BT -- the corpus NLA/src/data.py trains on, so this
            is the in-distribution reference, not merely a proxy for it.
  polaris   Activations from POLARIS's own LLM calls, replayed from traces/.
            Sidecars store token_ids, so no live run is needed and the
            activations are bit-identical to those produced at runtime.

Run in three phases, each loading ONE model:

    python collect.py acts      # T  (15.2 GB) -> activations
    python collect.py explain   # AV (15.2 GB) -> explanations
    python collect.py score     # AR (10.9 GB) -> cosines, FVE, CSV

Together the three are 41.3 GB and need both cards; separately each fits one.
That is the same separability the trace format was designed for, and it means
the experiment survives other users occupying the second GPU. Phases persist
their output, so a crash costs one phase rather than the whole run.

Two confounds are controlled deliberately:

  position depth   POLARIS prompts run to ~3.6k tokens while FineWeb documents
                   are mostly shorter, and activations drift with depth. The
                   FineWeb positions are therefore drawn to *match* the POLARIS
                   position histogram rather than sampled independently.
  minimum context  MIN_POSITION=150, matching src/data.py.

One confound is NOT controlled and must be reported: POLARIS text carries a chat
template (<|im_start|>system ...) while FineWeb is raw prose. Format is part of
the domain difference here, not separable from it.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "NLA"))

# .env is read by the shell start scripts, not by Python, so a script that
# imports src.config directly silently gets the *default* backbone. Load it here
# before src.config is imported, or this measures the wrong model entirely.
import os  # noqa: E402


def _load_env(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


_load_env(ROOT / ".env")
# One card on purpose (see DEVICE below): overrides whatever .env asked for.
os.environ["NLA_DEVICE"] = "cuda:0"

# src.config sets HF_HOME and must precede any HuggingFace import.
from src.config import (  # noqa: E402
    AR_PREFIX, AR_SUFFIX, AV_USER_PROMPT, MODEL_ID, PROBE_LAYER,
)

import torch  # noqa: E402
import torch.nn.functional as F  # noqa: E402

HERE         = Path(__file__).parent
RES          = HERE / "results"
MIN_POSITION = 150                       # matches src/data.py
# Three conditions, chosen to separate two things that are confounded if you
# only compare FineWeb with POLARIS: the *domain* (adaptation reasoning vs web
# prose) and the *format* (chat template vs raw text). UltraChat is general-
# domain but chat-formatted, so it sits between them and tells you which of the
# two the shift is really about.
CORPORA = {
    "fineweb":   dict(path="HuggingFaceFW/fineweb", name="sample-10BT",
                      split="train", kind="raw"),
    "ultrachat": dict(path="HuggingFaceH4/ultrachat_200k", name=None,
                      split="train_sft", kind="chat"),
}
AV_MAX_NEW   = 120                       # matches server/inference.py
AR_MAX_LEN   = 256                       # matches server/inference.py

# Pinned to one card on purpose: 15.2 GB fits a 24 GB 4090 with room for
# activations, and staying off GPU 1 leaves other users' jobs alone.
DEVICE = "cuda:0"


def _norm(a: torch.Tensor, d: int) -> torch.Tensor:
    """sqrt(d) normalisation, matching server/inference.py before cosine/FVE."""
    return a * (float(np.sqrt(d)) / a.norm().clamp(min=1e-8))


# ------------------------------------------------------------------ phase: acts
def phase_acts(args):
    from src.model import load_target, load_tokenizer, decoder_layers, decoder_stack
    from datasets import load_dataset

    print(f"backbone {MODEL_ID}  layer {PROBE_LAYER}", flush=True)

    rng = random.Random(args.seed)
    tok = load_tokenizer()
    print(f"loading T ({MODEL_ID}) on {DEVICE} ...", flush=True)
    target = load_target(DEVICE)
    d_model = target.config.hidden_size

    cache: dict = {}

    def _hook(_m, _i, out):
        cache["resid"] = (out[0] if isinstance(out, tuple) else out).detach()

    decoder_layers(target)[PROBE_LAYER].register_forward_hook(_hook)
    body = decoder_stack(target)

    def acts_for(ids):
        t = torch.tensor(ids, dtype=torch.long, device=DEVICE)
        with torch.no_grad():
            body(input_ids=t.unsqueeze(0))
        return cache["resid"][0].float().cpu().numpy()

    # ---- polaris: sample positions across every captured trace
    traces = sorted(Path(args.traces).glob("run-*/req-*.json"))
    if not traces:
        raise SystemExit(f"no traces under {args.traces}")
    pool = []
    for t in traces:
        meta = json.loads(t.read_text())
        ids = meta.get("token_ids") or []
        if len(ids) <= MIN_POSITION + 1:
            continue
        head = (meta.get("messages") or [{}])[0].get("content", "")[:200]
        src = "meta-learner" if "prompt engineer" in head else "reasoner"
        pool += [(t, p, src) for p in range(MIN_POSITION, len(ids))]
    rng.shuffle(pool)
    picks = pool[: args.n]
    print(f"polaris: {len(picks)} positions from {len(traces)} traces", flush=True)

    rows, acts = [], []
    by_trace: dict = {}
    for t, p, s in picks:
        by_trace.setdefault(t, []).append((p, s))

    t0 = time.time()
    for t, items in by_trace.items():
        meta = json.loads(t.read_text())
        A = acts_for(meta["token_ids"])                  # (seq, d), one pass
        for p, s in items:
            rows.append({"condition": "polaris", "source": s,
                         "doc": str(t.relative_to(Path(args.traces))),
                         "position": p, "seq_len": len(meta["token_ids"])})
            acts.append(A[p])
        print(f"  {t.name}: +{len(items)}  ({len(rows)}/{len(picks)})", flush=True)

    # ---- text corpora: match the polaris position histogram exactly
    targets = sorted([r["position"] for r in rows], reverse=True)
    print(f"matching {len(targets)} positions "
          f"(median {int(np.median(targets))}, max {max(targets)})", flush=True)

    for cond, spec in CORPORA.items():
        ds = load_dataset(spec["path"], spec["name"], split=spec["split"],
                          streaming=True)
        remaining, n_docs = list(targets), 0
        for doc in ds:
            if not remaining:
                break
            if spec["kind"] == "chat":
                # Apply the same chat template the server applies to POLARIS's
                # calls, so this condition differs from POLARIS in domain only.
                msgs = doc.get("messages") or []
                if not msgs:
                    continue
                text = tok.apply_chat_template(msgs, tokenize=False)
            else:
                text = (doc.get("text") or "").strip()
            if not text:
                continue
            ids = tok(text, return_tensors="pt",
                      add_special_tokens=True)["input_ids"][0]
            fits = [p for p in remaining if p < len(ids)]
            if not fits:
                continue
            take = fits[:10]                      # <=10 per doc, as in training
            A = acts_for(ids.tolist())
            n_docs += 1
            for p in take:
                rows.append({"condition": cond, "source": cond,
                             "doc": f"{cond}-{n_docs:05d}", "position": p,
                             "seq_len": int(len(ids))})
                acts.append(A[p])
                remaining.remove(p)
            done = len(targets) - len(remaining)
            print(f"  {cond} doc{n_docs:05d}: +{len(take)}  "
                  f"({done}/{len(targets)})", flush=True)
        if remaining:
            print(f"  WARNING: {cond} left {len(remaining)} positions unmatched "
                  f"(longest doc too short)", flush=True)

    RES.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(RES / "acts.npz", acts=np.stack(acts).astype(np.float32))
    (RES / "meta.json").write_text(json.dumps(
        {"d_model": d_model, "rows": rows}, indent=2))
    print(f"\nphase acts: {len(rows)} activations in {time.time()-t0:.0f}s "
          f"-> {RES/'acts.npz'}")


# --------------------------------------------------------------- phase: explain
def phase_explain(args):
    from src.av import load_av

    print(f"backbone {MODEL_ID}  layer {PROBE_LAYER}", flush=True)

    meta = json.loads((RES / "meta.json").read_text())
    acts = np.load(RES / "acts.npz")["acts"]
    print(f"loading AV on {DEVICE} ...", flush=True)
    av, tok = load_av(DEVICE)
    av.eval()
    for p in av.parameters():
        p.requires_grad_(False)

    prompt_str = tok.apply_chat_template(
        [{"role": "user", "content": AV_USER_PROMPT}],
        tokenize=False, add_generation_prompt=True)
    pid = tok(prompt_str, add_special_tokens=False,
              return_tensors="pt")["input_ids"][0].to(DEVICE).unsqueeze(0)
    attn = torch.ones_like(pid, dtype=torch.long)

    out, t0 = [], time.time()
    for i, a in enumerate(acts):
        act = torch.from_numpy(a).to(DEVICE).float().unsqueeze(0)
        with torch.no_grad():
            gen = av.generate(pid, attn, act, max_new_tokens=AV_MAX_NEW,
                              do_sample=False, pad_token_id=tok.eos_token_id)
        text = tok.decode(gen[0], skip_special_tokens=True)
        m = re.search(r"<explanation>(.*?)(?:</explanation>|$)", text, re.DOTALL)
        out.append(m.group(1).strip() if m else text.strip())
        if (i + 1) % 10 == 0 or i == 0:
            el = time.time() - t0
            print(f"  [{i+1}/{len(acts)}] {el/(i+1):.1f}s each, "
                  f"eta {(len(acts)-i-1)*el/(i+1)/60:.0f} min", flush=True)

    (RES / "explanations.json").write_text(json.dumps(out, indent=2))
    print(f"\nphase explain: {len(out)} explanations in {time.time()-t0:.0f}s")


# ----------------------------------------------------------------- phase: score
def phase_score(args):
    from src.ar import load_ar
    from src.model import load_tokenizer

    print(f"backbone {MODEL_ID}  layer {PROBE_LAYER}", flush=True)

    meta  = json.loads((RES / "meta.json").read_text())
    rows  = meta["rows"]
    d     = meta["d_model"]
    acts  = np.load(RES / "acts.npz")["acts"]
    descs = json.loads((RES / "explanations.json").read_text())

    tok = load_tokenizer()
    print(f"loading AR on {DEVICE} ...", flush=True)
    ar = load_ar(DEVICE, freeze_base=False)
    ar.eval()
    for p in ar.parameters():
        p.requires_grad_(False)

    def recon(text: str) -> torch.Tensor:
        enc = tok(f"{AR_PREFIX}{text}{AR_SUFFIX}", return_tensors="pt",
                  truncation=True, max_length=AR_MAX_LEN).to(DEVICE)
        with torch.no_grad():
            return ar(enc["input_ids"], enc["attention_mask"]).float()[0]

    # Real reconstruction
    a_norm, a_hat, t0 = [], [], time.time()
    for i, (a, e) in enumerate(zip(acts, descs)):
        an = _norm(torch.from_numpy(a).to(DEVICE).float(), d)
        ah = recon(e).to(DEVICE)
        # Put the reconstruction on the same scale before any squared distance.
        # The AR's output scale depends on how it was trained: src/train.py
        # regresses onto sqrt(d)-normalised targets, but the published kitft pair
        # emits ~2.8x that. Cosine is scale-invariant and unaffected; FVE is a
        # squared distance and is destroyed by the mismatch unless both are
        # renormalised here. FVE is therefore about direction, and the magnitude
        # is kept as its own column rather than silently folded in.
        rows[i]["recon_scale_ratio"] = float(ah.norm() / np.sqrt(d))
        ahn = _norm(ah, d)
        a_norm.append(an.cpu().numpy())
        a_hat.append(ahn.cpu().numpy())
        rows[i]["cosine"] = float(F.cosine_similarity(an, ah, dim=-1))
        rows[i]["explanation"] = e
        if (i + 1) % 25 == 0:
            print(f"  real [{i+1}/{len(acts)}]", flush=True)

    # Shuffled control, within condition: score each activation against a
    # *different* sample's explanation. Separates "the AV read this activation"
    # from "the AV emits plausible text regardless".
    shuffled_err: list = []
    for cond in sorted({r["condition"] for r in rows}):
        idx = [i for i, r in enumerate(rows) if r["condition"] == cond]
        for k, i in enumerate(idx):
            other = descs[idx[(k + 1) % len(idx)]]
            ah = recon(other).to(DEVICE)
            an = torch.from_numpy(a_norm[i]).to(DEVICE)
            rows[i]["cosine_shuffled"] = float(F.cosine_similarity(an, ah, dim=-1))
            ahn = _norm(ah, d)
            num = float(((a_norm[i] - ahn.cpu().numpy()) ** 2).sum())
            shuffled_err.append((i, num))
        print(f"  shuffled {cond}: {len(idx)} done", flush=True)

    # FVE against two baselines. The own-corpus mean is the honest, demanding
    # one -- POLARIS activations are self-similar, so that baseline is tight and
    # depresses FVE for reasons unrelated to explanation quality. The pooled
    # mean is comparable across conditions. Report both; cosine stays primary.
    A = np.stack(a_norm)
    means = {c: A[[i for i, r in enumerate(rows) if r["condition"] == c]].mean(0)
             for c in sorted({r["condition"] for r in rows})}
    pooled = A.mean(0)
    for i, r in enumerate(rows):
        num = float(((a_norm[i] - a_hat[i]) ** 2).sum())
        r["fve_own"] = 1.0 - num / float(((a_norm[i] - means[r["condition"]]) ** 2).sum())
        r["fve_pooled"] = 1.0 - num / float(((a_norm[i] - pooled) ** 2).sum())
    for i, num_s in shuffled_err:
        rows[i]["fve_shuffled"] = 1.0 - num_s / float(((a_norm[i] - pooled) ** 2).sum())

    out = RES / "samples.csv"
    cols = ["condition", "source", "doc", "position", "seq_len",
            "cosine", "cosine_shuffled", "fve_own", "fve_pooled", "fve_shuffled",
            "recon_scale_ratio", "explanation"]
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    np.savez_compressed(RES / "corpus_means.npz", pooled=pooled, **means)

    print(f"\nphase score: {len(rows)} rows in {time.time()-t0:.0f}s -> {out}\n")
    for c in sorted({r["condition"] for r in rows}):
        sel = [r for r in rows if r["condition"] == c]
        if not sel:
            continue
        cos = np.array([r["cosine"] for r in sel])
        sh  = np.array([r["cosine_shuffled"] for r in sel])
        print(f"  {c:8s} n={len(sel):4d}  cos={cos.mean():+.3f}+-{cos.std():.3f}"
              f"  shuffled={sh.mean():+.3f}  delta={cos.mean()-sh.mean():+.3f}"
              f"  fve_own={np.mean([r['fve_own'] for r in sel]):+.3f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("phase", choices=["acts", "explain", "score"])
    ap.add_argument("-n", type=int, default=200, help="datapoints per condition")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--traces", default=str(ROOT / "traces"))
    a = ap.parse_args()
    {"acts": phase_acts, "explain": phase_explain, "score": phase_score}[a.phase](a)
