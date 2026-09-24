#!/bin/bash
# The performance result for the paper: one figure and one table.
#
# SWIM's published configuration, unchanged -- ClarkNet, 12 servers starting
# from 3, 180 s boots, 10 dimmer levels -- scored with SWIM's reported utility
# (SEAMS 2017A, swim_utility.py). The figure uses seed-set 0 for every
# controller, which is the seed of SWIM's shipped PLA and Thallium runs, so all
# of them face the same random draws. The table adds seed-sets 1 and 2 for the
# LLM configurations and 10 seeds for SWIM's reactive manager.
#
#   ./published_figure.sh            (on CSF, after the runs exist)
set -uo pipefail
R="$HOME/selas-results"
REPO="${SELAS_REPO:-$HOME/SELAS}"
LLM=$(ls -dt "$R"/published-clarknet-* | head -1)
NULL=$(ls -dt "$R"/published-null-* | head -1)
BUILTIN=$(ls -dt "$R"/builtin-* | head -1)
OUT="$R/published-figure"
rm -rf "$OUT"; mkdir -p "$OUT/pla" "$OUT/thallium"
T="$REPO/SWIM/tools/THALLIUM"
cp "$T/pladapt-0.sca" "$T/pladapt-0.vec" "$OUT/pla/"
cp "$T/thallium-0.sca" "$T/thallium-0.vec" "$OUT/thallium/"
echo "llm      $LLM"; echo "null     $NULL"; echo "builtin  $BUILTIN"

source "$HOME/selas-env.sh" >/dev/null 2>&1
cd "$REPO/experiments/controller_comparison"
python3 collect.py "$LLM/llm-s0" "$LLM/formula-s0" "$OUT/pla" "$OUT/thallium" \
    "$BUILTIN/repro_published" "$NULL/null" -o "$OUT/runs.json" > "$OUT/collect.log" 2>&1 \
    || { echo "collect failed"; tail "$OUT/collect.log"; exit 1; }
python3 plot.py "$OUT/runs.json" -o "$OUT/comparison" \
    --labels "LLM, prompt A" "LLM, prompt B" "PLA" "Thallium" "SWIM reactive" "do nothing" \
    --title "SWIM, ClarkNet, published configuration (seed-set 0)"

dirs=(); for d in "$LLM"/*/; do dirs+=("${d%/}"); done
python3 collect.py "${dirs[@]}" -o "$OUT/llm_seeds.json" > /dev/null 2>&1
python3 - "$OUT/runs.json" "$OUT/llm_seeds.json" "$BUILTIN/results.json" <<'PY'
import json, os, re, statistics as st, sys
fig = json.load(open(sys.argv[1]))
seeds = json.load(open(sys.argv[2]))
builtin = json.load(open(sys.argv[3]))
def row(name, us, late):
    sd = st.stdev(us) if len(us) > 1 else float("nan")
    print("%-26s %2d  %9.1f  %8.1f  %8.1f" % (name, len(us), st.mean(us), sd, st.mean(late)))
print("\nutility = SWIM reported (SEAMS 2017A); late = periods over the SLA, of 90")
print("%-26s %2s  %9s  %8s  %8s" % ("controller", "n", "mean", "sd", "late"))
for arm, name in (("llm", "LLM, prompt A"), ("formula", "LLM, prompt B")):
    rs = [r for r in seeds if re.fullmatch(arm + r"-s\d+", os.path.basename(r["run_dir"]))]
    row(name + " (seeds 0-2)", [r["utility_seams2017a"] for r in rs], [r["late_periods_seams"] for r in rs])
rs = [r for r in builtin if os.path.basename(r["run_dir"]).startswith("Reactive_clarknet_i3_s")]
row("SWIM reactive (seeds 1-10)", [r["utility_seams2017a"] for r in rs], [r["late_periods_seams"] for r in rs])
print("\nseed-set 0, as in the figure:")
for r in fig:
    print("  %-22s %9.1f   late %3s   servers %.2f   dimmer %.2f" % (os.path.basename(r["run_dir"]),
          r["utility_seams2017a"], r["late_periods_seams"], r["mean_servers"], r["mean_dimmer"]))
PY
echo "figure -> $OUT/comparison.png"
