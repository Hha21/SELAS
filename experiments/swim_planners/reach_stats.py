#!/usr/bin/env python3
"""Size of a PLA-SDP reachability relation, and the work it implies per decision.

The SWIM ProactiveAdaptationManager (clayness/swim) records
``transitionsEvaluated`` at every decision: the number of innermost iterations
of SDPAdaptationManager::evaluate(). That number is a function only of the two
reachability relations (rubis.yaml, rubis-step.yaml), the environment tree and
the current configuration, so it lets us check a regenerated relation against
the shipped runs *before* simulating anything:

    t = 0      : |RI(cur)| * |part1|
    t = 1      : sum over s in RI(cur) of |part1| * |RFC(s)| * |part2|
    t = 2..H-1 : sum over all s of |part_t| * |RFC(s)| * |part_t+1|

RI is the immediate relation (rubis.yaml), RFC(s) = RI(step(s)) with step from
rubis-step.yaml. With the scenario tree the manager builds
(createScenarioTree(1, 10): branch once into 3, then chains) every part after
the root has 3 states, so the last line is 72 * sum_s |RFC(s)|.

    reach_stats.py DIR [--config s,d,p ...]

prints the relation sizes and the predicted count for the given configurations
(0-based servers, dimmer level, add-server progress as in the YAML).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


class _Loader(yaml.SafeLoader):
    pass


def _config(loader, node):
    m = loader.construct_mapping(node)
    return (int(m["s"]), int(m["d"]), int(m["addServerProgress"]))


_Loader.add_constructor("!reach.ConfigRubis", _config)


def load(path: Path) -> tuple[list[tuple[int, int, int]], dict[int, dict[int, list[str]]]]:
    with open(path) as f:
        docs = list(yaml.load_all(f, Loader=_Loader))
    # Configs are tagged !reach.ConfigRubis as reach writes them, plain mappings
    # once thallium_trim.py has rewritten the file.
    configs = [c if isinstance(c, tuple) else (int(c["s"]), int(c["d"]), int(c["addServerProgress"]))
               for c in docs[0]["configs"]]
    rel = {int(k): {int(j): (v or []) for j, v in (row or {}).items()} for k, row in docs[1].items()}
    return configs, rel


def relations(d: Path):
    ci, ri = load(d / "rubis.yaml")
    cs, rs = load(d / "rubis-step.yaml")
    # Map both files' indices onto (s, d, p) tuples, as the C++ loader does.
    imm = {ci[a]: {ci[b]: tuple(sorted(t)) for b, t in row.items()} for a, row in ri.items()}
    step = {}
    for a, row in rs.items():
        targets = [cs[b] for b in row]
        assert len(targets) == 1, "step relation must be a function"
        step[cs[a]] = targets[0]
    rfc = {c: set(imm.get(step[c], {})) for c in step}
    return imm, step, rfc


def predicted_count(imm, rfc, cur, horizon=10, part=3):
    ri = imm.get(cur, {})
    n = part * len(ri)                                        # t = 0
    n += sum(part * len(rfc.get(s, ())) * part for s in ri)   # t = 1
    n += (horizon - 2) * part * part * sum(len(v) for v in rfc.values())
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", type=Path)
    ap.add_argument("--config", action="append", default=[],
                    help="s,d,p (0-based) to predict transitionsEvaluated for")
    a = ap.parse_args()
    imm, step, rfc = relations(a.dir)
    n_imm = sum(len(v) for v in imm.values())
    print(f"{a.dir}: {len(imm)} configs with immediate transitions, {n_imm} immediate transitions "
          f"({n_imm - len(imm)} excluding no-ops), sum |RFC| = {sum(len(v) for v in rfc.values())}")
    tactics: dict[tuple, int] = {}
    for row in imm.values():
        for t in row.values():
            tactics[t] = tactics.get(t, 0) + 1
    print("  tactic sets:", {"+".join(k) or "noop": v for k, v in sorted(tactics.items())})
    for c in a.config:
        cur = tuple(int(x) for x in c.split(","))
        print(f"  config {cur}: |RI| = {len(imm.get(cur, {}))}, predicted transitionsEvaluated = "
              f"{predicted_count(imm, rfc, cur)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
