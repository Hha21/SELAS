#!/usr/bin/env python3
"""Search for the Thallium relation behind SWIM's shipped thallium-0 run.

The trimmed relation that run used was never published. clayness/thallium's
pipeline (thallium_pipeline.sh) makes such relations from a handful of model
constants and a weighting. With thallium's default.env it reproduces the
paper's Experiment 1 exactly, but no weighting reproduces the shipped run.
This script re-implements the pipeline in Python so that constants can be
searched in a fraction of a second each:

  bounds   PRISM-games' value for every initial configuration of
           thallium/model/rubis.smg, for best (0), expected and worst arrivals.
           With arrivals fixed, the game is a 10-step minimisation over the
           system's joint dimmer/server actions. PRISM semantics are kept:
           matching reward items are summed, num_servers may exceed MAX_S
           (PRISM does not clamp it), Java double arithmetic (x/0 = inf or
           NaN), floor() as an int cast. `verify` checks it value by value
           against a pipeline directory's PRISM output.
  fuzzy    FuzzyValueCalculator: triangular values, normalisation, weighted
           minimum, rounded to the 6 decimals the Java writes (the trimmer
           re-reads the printed text, so ties depend on it).
  trim     RubisGraphTrimmer + RubisReward.isDominatedBy + trim-rubis.py.

and scores each relation against what the shipped run records. Its
transitionsEvaluated is 48,108 at every decision, and its configuration is
(1, 4, 2) from the first scored decision on: 2 servers, dimmer level 4, no
boot in progress. So a candidate must give 48,108 there (reach_stats.py's
formula), make (1, 4, 2) a sink (only the no-op left), and let the planner
reach it from the initial (2, 8, 2) within the 6 decisions before t = 900 s.

    thallium_search.py verify PIPELINE_DIR [KEY=VALUE ...]
    thallium_search.py sweep  RELATION_DIR OUT.txt [--procs 4]
    thallium_search.py dump   RELATION_DIR OUTDIR WEIGHTS [KEY=VALUE ...]

RELATION_DIR holds the PLA relation (rubis.yaml, rubis-step.yaml), e.g. the
reach/ directory thallium_pipeline.sh leaves. A candidate found here should be
regenerated with thallium_pipeline.sh, the real pipeline, before use.
"""

from __future__ import annotations

import argparse
import itertools
import math
import shutil
from collections import deque
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

import yaml

from reach_stats import _Loader, predicted_count

WEIGHTS = ["0.33,0.33,0.33", "0.99,0.00,0.00", "0.00,0.99,0.00", "0.00,0.00,0.99", "0.50,0.25,0.25",
           "0.25,0.50,0.25", "0.25,0.25,0.50", "0.50,0.50,0.00", "0.50,0.00,0.50", "0.00,0.50,0.50",
           "0.66,0.33,0.00", "0.66,0.00,0.33", "0.33,0.66,0.00", "0.33,0.00,0.66", "0.00,0.66,0.33",
           "0.00,0.33,0.66"]                                   # thallium/default.weights
DEFAULTS = dict(HORIZON=10, SECS_PER_STEP=10, SERVICE_RATE=10, DIMMER_ADJ=1.15, THRESHOLD=3000,
                SRV_COST_PER_HOUR=0.10, EXP_ARRIVAL_RATE=42, MAX_ARRIVAL_RATE=200,
                MAX_S=12, MAX_P=3, MAX_D=10)                   # thallium/default.env
TARGET_TE, CUR, START = 48108, (1, 4, 2), (2, 8, 2)

_REL: dict = {}


def load_relation(d: Path) -> None:
    with open(d / "rubis.yaml") as f:
        docs = list(yaml.load_all(f, Loader=_Loader))
    with open(d / "rubis-step.yaml") as f:
        sd = list(yaml.load_all(f, Loader=_Loader))
    _REL["dir"] = d
    _REL["configs"] = docs[0]["configs"]
    _REL["graph"] = {int(k): [int(j) for j in (row or {})] for k, row in docs[1].items()}
    _REL["step"] = {sd[0]["configs"][a]: sd[0]["configs"][next(iter(r))] for a, r in sd[1].items()}


# -- Java / PRISM arithmetic -------------------------------------------------------
def jdiv(a: float, b: float) -> float:
    if b == 0:
        return math.nan if a == 0 else math.copysign(math.inf, a)
    return a / b


def jmin(a: float, b: float) -> float:
    return math.nan if (math.isnan(a) or math.isnan(b)) else min(a, b)


def prism_floor(x: float) -> int:
    if math.isnan(x):
        return 0
    return int(max(-2**31, min(2**31 - 1, math.floor(x) if math.isfinite(x) else x)))


# -- bounds -----------------------------------------------------------------------
def bounds(P: dict, arrivals: float) -> dict:
    """{(INIT_DIMMER, INIT_PROGRESS, INIT_SERVERS): [uC, uF, uR]} as PRISM reports them."""
    H, SPS, SR, DA, THR, COST, MS, MP, MD = (P[k] for k in (
        "HORIZON", "SECS_PER_STEP", "SERVICE_RATE", "DIMMER_ADJ", "THRESHOLD",
        "SRV_COST_PER_HOUR", "MAX_S", "MAX_P", "MAX_D"))

    def service_time(dim, n):
        mu = SR * DA ** (dim - 1)
        lam = float(arrivals)
        rho = jdiv(lam, mu)
        p0 = 0.0 if rho == 0 else jdiv(1, 1 + rho + jdiv(rho ** 2, 2 * (1 - jdiv(rho, n))))
        if p0 == 0:
            lq = 0.0
        else:
            cf = math.factorial(n - 1) if 3 <= n <= MS else 1   # CFact covers 3..MAX_S only
            lq = jdiv(rho ** (n + 1) * p0, cf * (n - rho) ** 2)
        wq = 0.0 if lq == 0 else jdiv(lq, lam)
        return 0 if wq == 0 else prism_floor((wq + jdiv(1, mu)) * SPS * 1000)

    def rewards(dim, n, prog):
        t = service_time(dim, n)
        prov = n + (1 if prog > 0 else 0)
        uc = uf = ur = 0.0                     # PRISM sums every matching reward item
        if t < 0 or t > THR:
            uc += 1.0
        if t <= THR:
            uc += prov * (COST / 3600) * SPS
            uf += -1 * (1.0 / DA) ** (dim - 1) / H
        if t < 0 or prov > MS:
            ur += (THR * 2) / H
        if t >= 0 and prov <= MS:
            ur += t / H
        return uc, uf, ur

    def successors(dim, n, prog):
        dims = [dim] + ([dim - 1] if dim > 1 else []) + ([dim + 1] if dim < MD else [])
        if prog == 0:
            srv = [(n, 0)] + ([(n - 1, 0)] if n > 1 else []) + ([(n, MP - 1)] if n < MS else [])
        elif prog > 1:
            srv = [(n, prog - 1)]
        else:
            srv = [(n + 1, 0)]                 # may exceed MAX_S, as in PRISM
        return [(d2, n2, p2) for d2 in dims for n2, p2 in srv]

    out: dict = {}
    for k in range(3):
        @lru_cache(maxsize=None)
        def value(t, dim, n, prog):
            if t == H:
                return 0.0
            return min(rewards(*c)[k] + value(t + 1, *c) for c in successors(dim, n, prog))
        for d in range(1, MD + 1):
            for p in range(1, MP + 1):
                for s in range(1, MS + 1):
                    out.setdefault((d, p, s), [None] * 3)[k] = value(0, d, s, p - 1)
    return out


# -- fuzzy values and trimming --------------------------------------------------------
def fuzzy(best, exp, worst, w):
    res: dict = {}
    for k in range(3):
        m = {}
        for key in best:
            b, e, wo = -best[key][k], -exp[key][k], -worst[key][k]
            if all(math.isfinite(x) for x in (b, e, wo)):
                m[key] = (abs(wo - e), e, abs(e - b))
        pisM, nisM = max(v[1] for v in m.values()), min(v[1] for v in m.values())
        pisO, nisO = max(v[2] for v in m.values()), min(v[2] for v in m.values())
        pisP, nisP = abs(max(-v[0] for v in m.values())), abs(min(-v[0] for v in m.values()))
        for key, (p, l, o) in m.items():
            g = jmin((1 - w[0]) * abs(jdiv(nisP - p, nisP - pisP)),
                     jmin((1 - w[1]) * abs(jdiv(nisM - l, nisM - pisM)),
                          (1 - w[2]) * abs(jdiv(nisO - o, nisO - pisO))))
            d, pp, s = key
            res.setdefault((s, pp, d), [None] * 3)[k] = float("%f" % g) if math.isfinite(g) else g
    return res


def _dominated(a, b):
    for i in range(3):
        if a[i] < b[i]:
            return all(a[j] <= b[j] for j in range(3) if j != i)
    return False


def trim(fz):
    configs, graph = _REL["configs"], _REL["graph"]

    def reward(cfg):
        s, d, p = cfg
        return fz.get((s + 1, 3 - p, d + 1))
    keep = {}
    for n, row in graph.items():
        rw = {x: reward(configs[x]) for x in row}
        keep[n] = [x for x in row if rw[x] is None
                   or not any(_dominated(rw[x], rw[y]) for y in row if rw[y])]
    return keep


def score(keep):
    configs, step = _REL["configs"], _REL["step"]
    imm = {configs[a]: {configs[b]: 1 for b in row} for a, row in keep.items()}
    rfc = {c: set(imm.get(step[c], {})) for c in step}
    te = predicted_count(imm, rfc, CUR)
    idx = {c: i for i, c in enumerate(configs)}
    cur, start = idx[CUR], idx[START]
    sink = keep.get(cur) == [cur]
    seen, q, reach = {start: 0}, deque([start]), None
    while q:
        n = q.popleft()
        if n == cur:
            reach = seen[n]
            break
        for x in keep.get(n, []):
            if x not in seen:
                seen[x] = seen[n] + 1
                q.append(x)
    return te, sum(len(r) for r in keep.values()), sink, reach


def relations_for(P, weights=WEIGHTS):
    b, e, w = bounds(P, 0), bounds(P, P["EXP_ARRIVAL_RATE"]), bounds(P, P["MAX_ARRIVAL_RATE"])
    return {ws: trim(fuzzy(b, e, w, [float(x) for x in ws.split(",")])) for ws in weights}, (b, e, w)


# -- commands ---------------------------------------------------------------------
def _params(kvs):
    P = dict(DEFAULTS)
    for kv in kvs:
        k, v = kv.split("=")
        P[k] = float(v) if "." in v else int(v)
    return P


def _read_prism(path: Path):
    sec, out = -1, {}
    for line in path.read_text().splitlines():
        if line.startswith("<<"):
            sec += 1
            continue
        parts = line.split("\t")
        if len(parts) == 4 and parts[0].isdigit():
            out.setdefault(tuple(map(int, parts[:3])), [None] * 3)[sec] = float(parts[3])
    return out


def cmd_verify(a):
    load_relation(a.pipeline / "reach")
    P = _params(a.params)
    rels, (b, e, w) = relations_for(P)
    for name, mine in (("best", b), ("exp", e), ("worst", w)):
        ref = _read_prism(a.pipeline / "prism" / f"rubis-{name}.txt")
        bad = [k for k in ref for i in range(3)
               if not math.isclose(ref[k][i], mine[k][i], rel_tol=1e-9, abs_tol=1e-12)]
        print(f"bounds {name}: {len(ref)} configurations, {len(bad)} values differ from PRISM")
    for t in sorted(a.pipeline.glob("trim*/trimmed.txt")):
        ws = t.parent.name[4:].replace("-", ",")
        kept_java = sum(1 for line in t.read_text().splitlines() if line.rstrip().endswith("+"))
        te, kept, _, _ = score(rels[ws]) if ws in rels else (None, None, None, None)
        print(f"trim {ws}: Java kept {kept_java}, this port kept {kept}, predicted TE {te}")


def _sweep_one(args):
    reldir, combo = args
    if not _REL:
        load_relation(reldir)
    P = dict(DEFAULTS)
    P.update(combo)
    rels, _ = relations_for(P)
    return combo, {ws: score(k) for ws, k in rels.items()}


def cmd_sweep(a):
    grid = [dict(THRESHOLD=th, DIMMER_ADJ=da, EXP_ARRIVAL_RATE=e, MAX_ARRIVAL_RATE=m, SECS_PER_STEP=sp)
            for th, da, e, m, sp in itertools.product(
                range(250, 5001, 250), (1.1, 1.15, 1.2, 1.25, 1.3, 1.5, 2.0),
                (20, 30, 42, 50, 60), (100, 130, 150, 200), (10, 60))]
    n = hits = plausible = 0
    with Pool(a.procs) as pool, open(a.out, "w") as f:
        for combo, res in pool.imap_unordered(_sweep_one, [(a.relation, c) for c in grid], chunksize=8):
            n += len(res)
            for ws, (te, kept, sink, reach) in res.items():
                if te != TARGET_TE:
                    continue
                hits += 1
                ok = sink and reach is not None and reach <= 6
                plausible += ok
                f.write(f"{combo} weights={ws} kept={kept} sink={sink} reach_in={reach} "
                        f"{'PLAUSIBLE' if ok else ''}\n")
                f.flush()
        f.write(f"done: {len(grid)} constant combinations x {len(WEIGHTS)} weightings = {n} relations; "
                f"{hits} give transitionsEvaluated {TARGET_TE} at {CUR}; {plausible} also pass the sink "
                f"and reachability filters\n")
    print(Path(a.out).read_text().splitlines()[-1])


def cmd_dump(a):
    load_relation(a.relation)
    P = _params(a.params)
    keep = relations_for(P, [a.weights])[0][a.weights]

    class Raw(yaml.SafeLoader):
        pass
    Raw.add_constructor("!reach.ConfigRubis", lambda l, n: l.construct_mapping(n))
    with open(a.relation / "rubis.yaml") as f:
        cdoc, graph = list(yaml.load_all(f, Loader=Raw))
    a.outdir.mkdir(parents=True, exist_ok=True)
    with open(a.outdir / "rubis.yaml", "w") as f:
        yaml.safe_dump_all([cdoc, {n: {x: graph[n][x] for x in keep[n]} for n in graph}], f,
                           default_flow_style=False)
    shutil.copy(a.relation / "rubis-step.yaml", a.outdir / "rubis-step.yaml")
    print(a.outdir, score(keep))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("pipeline", type=Path)
    v.add_argument("params", nargs="*")
    s = sub.add_parser("sweep")
    s.add_argument("relation", type=Path)
    s.add_argument("out")
    s.add_argument("--procs", type=int, default=4)
    d = sub.add_parser("dump")
    d.add_argument("relation", type=Path)
    d.add_argument("outdir", type=Path)
    d.add_argument("weights")
    d.add_argument("params", nargs="*")
    a = ap.parse_args()
    {"verify": cmd_verify, "sweep": cmd_sweep, "dump": cmd_dump}[a.cmd](a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
