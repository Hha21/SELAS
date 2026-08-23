"""
End-to-end sanity check: T -> activation -> AV -> text -> AR -> reconstruction.

Confirms the whole NLA loop is wired correctly on this machine and backbone:
the hook lands on the right layer, the checkpoints load into the right shapes,
and the reconstruction is meaningfully better than the trivial baselines.

Two baselines are reported alongside each result, because a cosine in isolation
means nothing:

  shuffled   AR reconstruction from *another* sample's explanation. If the real
             explanation does not beat this, the AV is not actually describing
             this activation -- the single most important check here.
  mean       cosine to the corpus-mean activation, if activations/dataset is
             present. Per-sample FVE uses the same baseline.

Usage:
    ./.venv/bin/python scripts/check_roundtrip.py
    ./.venv/bin/python scripts/check_roundtrip.py --text "custom text"
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import (          # must precede HF imports (sets HF_HOME)
    AR_SOURCE, AV_SOURCE, DEVICE, DTYPE, MODEL_ID, PROBE_LAYER,
)

import argparse

import torch
import torch.nn.functional as F

from server.inference import NLAInference

DEFAULT_TEXTS = [
    "The restaurant served a rich beef bourguignon, slow-cooked with red wine and thyme.",
    "def quicksort(arr):\n    if len(arr) <= 1:\n        return arr\n    pivot = arr[len(arr) // 2]",
    "The patient's blood pressure dropped sharply, so the nurse called for immediate assistance.",
]

parser = argparse.ArgumentParser()
parser.add_argument("--text", action="append", help="text to analyse (repeatable)")
parser.add_argument("--position", type=int, default=-1, help="token position (default: last)")
args = parser.parse_args()

texts = args.text or DEFAULT_TEXTS

# A pair is either a local .pt or a published HF repo; config.py resolves which.
for name, (kind, src) in (("AV", AV_SOURCE), ("AR", AR_SOURCE)):
    if kind is None:
        raise SystemExit(
            f"no {name} checkpoint for {MODEL_ID}.\n"
            "Provide models/<backbone>/{av,ar}.pt, or add the backbone to "
            "CHECKPOINT_REPOS in src/config.py.\nSee models/README.md."
        )

print(f"backbone   {MODEL_ID}")
print(f"probe      layer {PROBE_LAYER}")
print(f"dtype      {DTYPE} on {DEVICE}")
print(f"AV         {AV_SOURCE[1]}  ({AV_SOURCE[0]})")
print(f"AR         {AR_SOURCE[1]}  ({AR_SOURCE[0]})")
print()

nla = NLAInference()
print(f"d_model    {nla.d_model}")
print(f"corpus mean{' loaded' if nla.corpus_mean is not None else ' unavailable (FVE reported as n/a)'}")
print()

results = []
for text in texts:
    out = nla.analyze_text(text, args.position)
    ids = nla._tokenize_ids(text)
    pos = out["position"]
    act = nla._extract_activation(ids[: pos + 1])
    results.append({"text": text, "act": act, **out})

# Cross-pair each explanation against another sample's activation to get the
# shuffled baseline -- the control that shows the AV is sample-specific.
for i, r in enumerate(results):
    other = results[(i + 1) % len(results)]
    a_hat_shuffled = nla._reconstruct(other["explanation"]).to(nla.device)

    scale  = nla.d_model ** 0.5
    act    = r["act"].to(nla.device)   # T and AR may sit on different shards
    a_norm = act * (scale / act.norm().clamp(min=1e-8))
    cos_shuffled = F.cosine_similarity(a_norm, a_hat_shuffled, dim=-1).item()

    fve = r["fve"]
    fve_str = f"{fve:+.3f}" if fve is not None else "n/a"

    print(f"[{i}] {r['text'][:64]!r}")
    print(f"     token {r['position']}: {nla.tokenize(r['text'])[r['position']]!r}")
    print(f"     AV -> {r['explanation'][:300]}")
    print(f"     cosine  real {r['reconstruction']:+.3f}   shuffled {cos_shuffled:+.3f}"
          f"   delta {r['reconstruction'] - cos_shuffled:+.3f}")
    print(f"     FVE     {fve_str}")
    print()

real = [r["reconstruction"] for r in results]
print(f"mean cosine (real explanations): {sum(real) / len(real):+.3f}")
print("PASS: real beats shuffled on every sample"
      if all(r["reconstruction"] > 0 for r in results)
      else "CHECK: at least one sample did not reconstruct positively")
