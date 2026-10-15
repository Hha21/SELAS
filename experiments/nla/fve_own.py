#!/usr/bin/env python3
"""FVE of the NLA reconstructions against our own activations' mean.

nla_pair's fve_nrm divides by the variance of the pair's *training* vectors
(VAR_NRM), i.e. its baseline is the training mean. Here the same errors are
also set against the SELAS activations at each position:

``fve_train``     fve_nrm as reported (median), the NLA paper's definition.
``meanvec_train`` fve_nrm of a constant: the leave-one-out mean of our vectors.
``spread/train``  variance of our vectors about their mean / VAR_NRM.
``fve_own``       1 - error / variance of our vectors about their mean.
``fve_centred``   the same after subtracting each side's mean over decisions:
                  how much of the decision-to-decision variation the words carry.

    python fve_own.py PILOT_DIR [PILOT_DIR ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nla_pair import VAR_NRM  # noqa: E402

PROBES = ["P0_state_end", "P0_turn", "P_sla", "P_capacity", "P_trend", "P_therefore", "P_action"]


def main() -> int:
    for out in map(Path, sys.argv[1:]):
        index = [json.loads(l) for l in (out / "index.jsonl").read_text().splitlines()]
        V = np.load(out / "vectors.npy").astype(np.float64)
        R = np.load(out / "reconstructions.npy").astype(np.float64)
        d = V.shape[1]
        nrm = lambda X: X / np.linalg.norm(X, axis=1, keepdims=True) * np.sqrt(d)  # noqa: E731
        print(f"\n{out.name}")
        print(f"{'probe':14s} {'n':>5s} {'fve_train':>9s} {'meanvec_train':>13s} {'spread/train':>12s} "
              f"{'fve_own':>8s} {'fve_centred':>11s}")
        for p in PROBES:
            k = np.array([i["source"] == "run" and i.get("probe") == p for i in index])
            if not k.any():
                continue
            g, r = nrm(V[k]), nrm(R[k])
            n, gbar = len(g), g.mean(0)
            mse = ((r - g) ** 2).mean(1)
            var_own = ((g - gbar) ** 2).mean(1).mean()
            loo = (gbar * n - g) / (n - 1)
            mse_mean = ((loo - g) ** 2).mean(1)
            mse_c = (((r - r.mean(0)) - (g - gbar)) ** 2).mean(1)
            print(f"{p:14s} {n:5d} {np.median(1 - mse / VAR_NRM):9.2f} {np.median(1 - mse_mean / VAR_NRM):13.2f} "
                  f"{var_own / VAR_NRM:12.2f} {np.median(1 - mse / var_own):8.2f} "
                  f"{np.median(1 - mse_c / var_own):11.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
