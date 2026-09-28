#!/usr/bin/env python3
"""Re-run the AR on a pilot's explanations and keep the reconstructed vectors.

pilot.py first kept only the scores; the centred analysis in analyse_pilot.py
(does a reconstruction's deviation from the SELAS mean point along the
activation's deviation, against a shuffled-explanation control?) needs the
vectors themselves. Writes OUT/reconstructions.npy (float32, one row per
explanation, the AR's raw output) and checks the scores it recomputes against
the ones pilot.py stored.

    python reconstruct.py OUT [--ar-repo kitft/nla-gemma3-27b-L41-ar]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nla_pair import AR_REPO, Reconstructor, reconstruction_scores  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--ar-repo", default=AR_REPO)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--batch-size", type=int, default=16)
    args = ap.parse_args()

    expl = [json.loads(l) for l in (args.out / "explanations.jsonl").read_text().splitlines()]
    V = np.load(args.out / "vectors.npy")
    assert len(expl) == len(V)
    import torch
    ar = Reconstructor(args.ar_repo, device=args.device,
                       dtype=torch.bfloat16 if args.device != "cpu" else torch.float32)
    P = ar.reconstruct([e["explanation"] for e in expl], batch_size=args.batch_size)
    np.save(args.out / "reconstructions.npy", P.astype(np.float32))
    s = reconstruction_scores(P, V, ar.mse_scale)
    stored = np.array([e["fve_nrm"] for e in expl])
    diff = np.abs(s["fve_nrm"] - stored)
    print(f"wrote {len(P)} reconstructions; recomputed fve_nrm vs stored: "
          f"median |diff| {np.median(diff):.4f}, max {diff.max():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
