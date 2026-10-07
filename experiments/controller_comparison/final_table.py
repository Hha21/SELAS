#!/usr/bin/env python3
"""The Part A table: utility per model, with and without reasoning, and the
objective ablation (the same two arms with no objective stated).

    python final_table.py RESULTS_DIR [RESULTS_DIR ...] [--json out.json]

Each RESULTS_DIR is a run directory holding ``runs.json`` (collect.py) and one
sub-directory per arm (``cot-sN`` / ``direct-sN``, and ``cot-noobj-sN`` /
``direct-noobj-sN`` for the objective ablation). The model is read from the
directory name: ``final-<model>-...`` (CSF, vLLM scoring) or ``fo-<model>-...``
(OpenRouter, the letter the model writes). Directories of the same model and
method are pooled.

Per model and method: utility mean ± SD over seed-sets for each arm, late
periods, how many periods the controller acted in (anything but no_op), and the
paired difference reasoning − no reasoning by seed-set with its 95% t-interval.
Where the no-objective arms exist, a second table gives them and the paired
effect of stating the objective (objective − none) with and without reasoning.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics as st
from collections import defaultdict
from pathlib import Path

# two-sided 95% t quantiles by degrees of freedom
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}
ARMS = ("cot", "direct", "cot-noobj", "direct-noobj")


def model_of(d: Path) -> tuple[str, str]:
    m = re.match(r"(final|fo)-(.+?)-\d{8}-\d{6}", d.name)
    if not m:
        raise SystemExit(f"cannot read a model from {d.name}")
    return m.group(2), ("CSF" if m.group(1) == "final" else "OpenRouter")


def actions_taken(arm_dir: Path) -> int | None:
    f = next(iter(sorted(arm_dir.rglob("decisions.jsonl"))), None)
    if f is None:
        return None
    return sum(json.loads(l)["decision"]["action"] != "no_op" for l in f.read_text().splitlines() if l.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", type=Path, nargs="+")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    # Only arms that passed their integration check count: the check ran, found
    # no problems, and saw all 105 decisions. A seed re-run after a failure
    # appears twice; directories are read oldest first, so a later passing run
    # replaces an earlier one.
    runs: dict[tuple[str, str], dict[tuple[str, int], dict]] = defaultdict(dict)
    excluded = []
    for d in sorted(args.dirs, key=lambda p: p.name):
        key = model_of(d)
        if not (d / "runs.json").exists():
            excluded.append(f"{d.name}: no runs.json")
            continue
        for r in json.loads((d / "runs.json").read_text()):
            name = r["run_dir"].rstrip("/").split("/")[-1]
            m = re.match(r"(cot-noobj|direct-noobj|cot|direct)-s(\d+)$", name)
            if not m:
                continue
            check = d / name / "integration_check.json"
            try:
                c = json.loads(check.read_text()) if check.exists() else None
            except json.JSONDecodeError:
                c = None                     # a check that never finished writing

            if not c or c.get("problems") or (c.get("decisions") or 0) < 105:
                excluded.append(f"{d.name}/{name}: " + ("no check" if not c else
                                f"{len(c.get('problems') or [])} problems, {c.get('decisions')} decisions"))
                continue
            r = dict(r, actions=actions_taken(d / name))
            runs[key][(m.group(1), int(m.group(2)))] = r

    def paired(R, a, b):
        seeds = sorted({s for x, s in R if x == a} & {s for x, s in R if x == b})
        d = [R[(a, s)]["utility_seams2017a"] - R[(b, s)]["utility_seams2017a"] for s in seeds]
        if len(d) < 2:
            return None
        m, h = st.mean(d), T95[min(len(d) - 1, 9)] * st.stdev(d) / len(d) ** 0.5
        return {"mean": m, "lo": m - h, "hi": m + h, "n": len(d)}

    def cell(row, a):
        u = row[a]["utility"]
        return f"{st.mean(u):8.0f} ± {st.stdev(u):5.0f} (n={len(u)})" if len(u) > 1 else "—"

    def dtxt(diff):
        return f"{diff['mean']:+7.0f} [{diff['lo']:+.0f}, {diff['hi']:+.0f}]" if diff else "—"

    out = {}
    print(f"{'model':16s} {'method':10s} {'reasoning (cot)':>22s} {'no reasoning (direct)':>22s} "
          f"{'cot − direct [95% CI]':>28s}  late cot / direct   acts cot / direct")
    for (model, method), R in sorted(runs.items()):
        row = {}
        for arm in ARMS:
            seeds = sorted(s for a, s in R if a == arm)
            row[arm] = {"seeds": seeds,
                        "utility": [R[(arm, s)]["utility_seams2017a"] for s in seeds],
                        "late": [R[(arm, s)]["late_periods_seams"] for s in seeds],
                        "actions": [R[(arm, s)]["actions"] for s in seeds],
                        "mean_servers": [R[(arm, s)]["mean_servers"] for s in seeds],
                        "mean_dimmer": [R[(arm, s)]["mean_dimmer"] for s in seeds]}
        row["cot_minus_direct"] = paired(R, "cot", "direct")
        row["noobj_cot_minus_direct"] = paired(R, "cot-noobj", "direct-noobj")
        row["objective_effect_cot"] = paired(R, "cot", "cot-noobj")
        row["objective_effect_direct"] = paired(R, "direct", "direct-noobj")
        out[f"{model} ({method})"] = row
        print(f"{model:16s} {method:10s} {cell(row, 'cot'):>22s} {cell(row, 'direct'):>22s} "
              f"{dtxt(row['cot_minus_direct']):>28s}  "
              f"{str(row['cot']['late']):>9s} / {str(row['direct']['late']):9s}  "
              f"{str(row['cot']['actions'])} / {str(row['direct']['actions'])}")

    if any(row["cot-noobj"]["utility"] or row["direct-noobj"]["utility"] for row in out.values()):
        print(f"\nobjective ablation\n{'model':28s} {'no objective, cot':>22s} {'no objective, direct':>22s} "
              f"{'objective effect, cot':>28s} {'objective effect, direct':>28s}")
        for key, row in out.items():
            print(f"{key:28s} {cell(row, 'cot-noobj'):>22s} {cell(row, 'direct-noobj'):>22s} "
                  f"{dtxt(row['objective_effect_cot']):>28s} {dtxt(row['objective_effect_direct']):>28s}")
    if excluded:
        print(f"\nexcluded ({len(excluded)}): " + "; ".join(excluded))
    if args.json:
        args.json.write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
