#!/usr/bin/env python3
"""Read a pilot.py output directory: can the explanations be trusted, and what
do the activations say about the decision?

    python analyse_pilot.py OUT [-o summary.json] [--examples 3]

1. Reference: did the published worked example reproduce (norms, fve_nrm)?
2. Fidelity: fve_nrm per probe position. Low values mean the AV's words do not
   carry the vector, and nothing it says there should be read as the model's.
3. Decodability: a cross-validated linear read-out of the recorded action kind
   (add / remove / no_op / dimmer) from the vectors at each probe, against the
   same read-out from the five telemetry numbers alone. If P0_turn -- before
   any reasoning -- is already as good as P_action, the reasoning adds nothing
   the state had not settled; if neither beats telemetry, the vector says no
   more than the state.
4. Words: at P_action, the letter the explanation expects next, against the
   letter the model chose; per probe, how often the explanation talks about
   removing, adding, the dimmer or response-time risk, split by the action.
5. Examples: explanations at every probe for a few decisions of each kind.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

KINDS = ("add_server", "remove_server", "no_op", "dimmer")
PROBES = ("P0_state_end", "P0_turn", "P_sla", "P_capacity", "P_trend", "P_therefore", "P_action")
TOPICS = {
    "remove": r"\b(remov\w*|reduc\w* (the )?(number of )?servers?|fewer servers?|scal\w* down|decommission\w*)",
    "add": r"\b(add(ing)? (a |another |more )?servers?|more servers?|scal\w* up|provision\w*)",
    "dimmer": r"\bdimmer\b",
    "no_op": r"\b(no[_ ]op|no action|do nothing|maintain\w*|keep\w* (the )?(current|same))",
    "rt_risk": r"\b(latenc\w*|response[- ]time|SLA|breach\w*|violat\w*|overload\w*|queue\w*|risk\w*)",
}
_LETTER = re.compile(r'"\s*([A-H])\s*"|\'([A-H])\'|“([A-H])”')


def kind(action: str) -> str:
    return "dimmer" if action.startswith("set_dimmer") else action


def load(out: Path):
    index = [json.loads(l) for l in (out / "index.jsonl").read_text().splitlines()]
    expl = [json.loads(l) for l in (out / "explanations.jsonl").read_text().splitlines()]
    V = np.load(out / "vectors.npy")
    assert len(index) == len(expl) == len(V)
    return index, expl, V


def ridge_cv(X: np.ndarray, y: np.ndarray, k: int = 5, pcs: int = 32, lam: float = 1.0,
             seed: int = 0) -> float:
    """Accuracy of a one-vs-rest ridge classifier, stratified k-fold; the
    standardisation and PCA are fitted inside each training fold."""
    rng = np.random.default_rng(seed)
    classes = sorted(set(y))
    folds = np.empty(len(y), int)
    for c in classes:
        idx = np.flatnonzero(y == c)
        rng.shuffle(idx)
        folds[idx] = np.arange(len(idx)) % k
    correct = 0
    for f in range(k):
        tr, te = folds != f, folds == f
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
        A, B = (X[tr] - mu) / sd, (X[te] - mu) / sd
        if pcs and A.shape[1] > pcs:
            _, _, vt = np.linalg.svd(A, full_matrices=False)
            A, B = A @ vt[:pcs].T, B @ vt[:pcs].T
        A1, B1 = np.c_[A, np.ones(len(A))], np.c_[B, np.ones(len(B))]
        Y = np.stack([(y[tr] == c).astype(float) for c in classes], 1)
        W = np.linalg.solve(A1.T @ A1 + lam * np.eye(A1.shape[1]), A1.T @ Y)
        pred = np.array(classes)[(B1 @ W).argmax(1)]
        correct += int((pred == y[te]).sum())
    return correct / len(y)


def expected_letter(text: str) -> str | None:
    m = _LETTER.search(text)
    return next(g for g in m.groups() if g) if m else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("-o", "--summary", type=Path, default=None)
    ap.add_argument("--examples", type=int, default=3)
    args = ap.parse_args()
    index, expl, V = load(args.out)
    S: dict = {}

    ref = json.loads((args.out / "reference.json").read_text())
    S["reference"] = {k: ref[k] for k in ("ok", "tokens_match", "norm_max_rel_err",
                                          "fve_nrm_mean_pos4plus", "fve_nrm_mean_pos4plus_ref")}
    print(f"1. reference: ok={ref['ok']}  max norm error {ref['norm_max_rel_err']:.2%}  "
          f"fve_nrm {ref['fve_nrm_mean_pos4plus']:.3f} (published {ref['fve_nrm_mean_pos4plus_ref']:.3f})")

    rows = [(i, e, v) for i, e, v in zip(index, expl, V) if i["source"] == "run"]
    runs = sorted({i["run"] for i, _, _ in rows})

    print("\n2. fidelity (fve_nrm; the published example averages 0.82 on ordinary chat text)")
    S["fidelity"] = {}
    for p in PROBES:
        f = np.array([e["fve_nrm"] for i, e, _ in rows if i["probe"] == p])
        if not len(f):
            continue
        S["fidelity"][p] = {"n": len(f), "median": float(np.median(f)), "q25": float(np.percentile(f, 25)),
                            "q75": float(np.percentile(f, 75)), "share_below_0.5": float((f < 0.5).mean())}
        print(f"   {p:13s} median {np.median(f):6.3f}  IQR {np.percentile(f, 25):6.3f}-{np.percentile(f, 75):6.3f}"
              f"  <0.5: {(f < 0.5).mean():.0%}")

    print("\n3. decodability of the action kind (5-fold ridge on 32 PCs; chance = majority class)")
    by_dec: dict = defaultdict(dict)
    for i, e, v in rows:
        by_dec[(i["run"], i["period"])][i["probe"]] = (i, v, e)
    decs = [d for d in by_dec.values() if all(p in d for p in ("P0_turn", "P_action"))]
    y = np.array([kind(d["P_action"][0]["action"]) for d in decs])
    tele = np.array([[d["P_action"][0]["observation"][k] or 0.0 for k in
                      ("servers", "active_servers", "dimmer", "avg_rt", "arrival_rate")] for d in decs], float)
    counts = Counter(y.tolist())
    S["decodability"] = {"n": len(y), "classes": dict(counts),
                         "majority": max(counts.values()) / len(y),
                         "telemetry": ridge_cv(tele, y, pcs=0)}
    print(f"   n={len(y)} {dict(counts)}  majority {S['decodability']['majority']:.2f}  "
          f"telemetry only {S['decodability']['telemetry']:.2f}")
    for p in PROBES:
        if all(p in d for d in decs):
            X = np.stack([d[p][1] for d in decs])
            S["decodability"][p] = ridge_cv(X, y)
            print(f"   {p:13s} {S['decodability'][p]:.2f}")

    print("\n4a. the letter the P_action explanation expects next vs the letter chosen")
    S["letters"] = {}
    for run in runs:
        pairs = []
        for i, e, _ in rows:
            if i["run"] == run and i["probe"] == "P_action":
                chosen = next(oid for oid, lab in i["options"] if lab == i["action"])
                pairs.append((expected_letter(e["explanation"]), chosen))
        named = [(a, b) for a, b in pairs if a]
        agree = sum(a == b for a, b in named)
        S["letters"][run] = {"decisions": len(pairs), "letter_named": len(named), "agree": agree}
        print(f"   {run}: names a letter in {len(named)}/{len(pairs)}, the chosen one in {agree}")

    print("\n4b. topics in the explanations, share of decisions, by recorded action kind")
    S["topics"] = {}
    for p in ("P0_turn", "P_therefore", "P_action"):
        for run in runs:
            for kd in KINDS:
                sel = [e for i, e, _ in rows if i["run"] == run and i["probe"] == p and kind(i["action"]) == kd]
                if not sel:
                    continue
                share = {t: float(np.mean([bool(re.search(rx, e["explanation"], re.I)) for e in sel]))
                         for t, rx in TOPICS.items()}
                S["topics"][f"{p} | {run} | {kd}"] = {"n": len(sel), **share}
                print(f"   {p:11s} {run.split('/')[-1]:14s} {kd:13s} n={len(sel):3d}  "
                      + "  ".join(f"{t} {v:.0%}" for t, v in share.items()))

    print("\n5. examples")
    shown = Counter()
    for (run, period), d in sorted(by_dec.items()):
        kd = kind(d["P_action"][0]["action"])
        if shown[(run, kd)] >= args.examples:
            continue
        shown[(run, kd)] += 1
        i0 = d["P_action"][0]
        print(f"\n--- {run} period {period}: {i0['action']}  obs {i0['observation']}")
        print(f"    trace: {(i0['reasoning'] or '').strip()[:400]}")
        for p in PROBES:
            if p in d:
                e = d[p][2]
                print(f"    [{p} fve {e['fve_nrm']:.2f}] {e['explanation'][:300]}")

    if args.summary:
        args.summary.write_text(json.dumps(S, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
