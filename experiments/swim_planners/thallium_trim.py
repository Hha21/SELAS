#!/usr/bin/env python3
"""Thallium's last step: drop the Pareto-dominated transitions from rubis.yaml.

A port of clayness/thallium python/trim-rubis.py (fec1448) from ruamel.yaml to
PyYAML, same logic: a transition n -> x of the PLA relation survives when the
Java GraphTrimmer marked it "+" in trim<W>/trimmed.txt. The pattern below is
the original's, character for character. The configs document is written back
unchanged (minus the !reach.ConfigRubis tag, which the C++ loader ignores), so
YAML indices keep their meaning.

    thallium_trim.py RESULTS_DIR [--weights W ...] [--config s,d,p]

RESULTS_DIR is laid out as run_rubis.sh leaves it: reach/rubis.yaml,
reach/rubis-step.yaml, trim<W>/trimmed.txt (W with commas as dashes). For each
weighting it writes trim<W>/rubis.yaml and copies rubis-step.yaml beside it
(Thallium trims only the immediate relation), then prints how much was trimmed
and the transitionsEvaluated the SWIM manager would report at --config.
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

import yaml

from reach_stats import predicted_count, relations


class _RawLoader(yaml.SafeLoader):
    pass


_RawLoader.add_constructor("!reach.ConfigRubis", lambda l, n: l.construct_mapping(n))


def trim(results: Path, w: str) -> tuple[int, int]:
    with open(results / "reach" / "rubis.yaml") as f:
        configs_doc, old_graph = list(yaml.load_all(f, Loader=_RawLoader))
    configs = configs_doc["configs"]
    lines = (results / f"trim{w}" / "trimmed.txt").read_text().splitlines()

    def key(c):  # ReachConfigIn: 1-based s, d, p
        return 1 + int(c["s"]), 1 + int(c["d"]), 1 + int(c["addServerProgress"])

    def check(base, child):
        bs, bd, bp = key(base)
        cs, cd, cp = key(child)
        pattern = "%2d,%2d,%2d -> %2d,%2d,%2d .* : \\+" % (bs, 2 - (bp - 1), bd - 1, cs, 2 - (cp - 1), cd - 1)
        return any(re.match(pattern, line) for line in lines)

    new_graph, n_old, n_new = {}, 0, 0
    for n, row in old_graph.items():
        row = row or {}
        new_graph[n] = {x: row[x] for x in row if check(configs[n], configs[x])}
        n_old += len(row)
        n_new += len(new_graph[n])
    out = results / f"trim{w}"
    with open(out / "rubis.yaml", "w") as f:
        yaml.safe_dump_all([{"configs": configs}, new_graph], f, default_flow_style=False)
    shutil.copy(results / "reach" / "rubis-step.yaml", out / "rubis-step.yaml")
    return n_old, n_new


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", type=Path)
    ap.add_argument("--weights", nargs="*", help="weightings as in default.weights (default: every trim* dir)")
    ap.add_argument("--config", default="1,4,2", help="s,d,p to predict transitionsEvaluated at")
    a = ap.parse_args()
    ws = [w.replace(",", "-") for w in a.weights] if a.weights else sorted(
        p.name[len("trim"):] for p in a.results.glob("trim*") if (p / "trimmed.txt").exists())
    cur = tuple(int(x) for x in a.config.split(","))
    print(f"{'weights':<16}{'kept':>6}{'of':>6}{'trimmed %':>11}{'|RI(cur)|':>11}{'predicted TE':>14}")
    for w in ws:
        n_old, n_new = trim(a.results, w)
        imm, _, rfc = relations(a.results / f"trim{w}")
        print(f"{w:<16}{n_new:>6}{n_old:>6}{100 * (n_old - n_new) / n_old:>10.1f}%"
              f"{len(imm.get(cur, {})):>11}{predicted_count(imm, rfc, cur):>14}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
