#!/bin/bash
# Interpretability figures for the paper, from the published-configuration runs.
#
# Spider: one polygon per prompt, each axis the mean over seed-sets 0-2. Drawn
# twice -- over all decisions (primary: holding still is a decision too) and
# over the active ones only (does the reasoning drive the action when the
# controller acts?).
#
# Pareto: SWIM's reported utility against the interpretability aggregate, one
# point per run, with do nothing, SWIM's reactive manager, PLA and Thallium as
# reference lines at their seed-set 0 utilities.
#
#   ./interpretability_figures.sh      (on CSF, after replay_all.sbatch)
set -uo pipefail
R="$HOME/selas-results"
REPO="${SELAS_REPO:-$HOME/SELAS}"
RUN=$(ls -dt "$R"/published-clarknet-* | head -1)
FIG="$R/published-figure/runs.json"          # written by published_figure.sh
source "$HOME/selas-env.sh" >/dev/null 2>&1
cd "$REPO/experiments/spider"

A=(); B=(); for s in 0 1 2; do A+=("$RUN/llm-s$s"); B+=("$RUN/formula-s$s"); done
for pool in all ACTIVE; do
    suffix=$([ "$pool" = all ] && echo "" || echo "_active")
    python3 spider.py "${A[@]}" "${B[@]}" --pool "$pool" \
        --labels "prompt A" "prompt A" "prompt A" "prompt B" "prompt B" "prompt B" \
        -o "$RUN/spider$suffix" | tail -30
    echo
done

# Reference utilities from the figure's runs.json, so they are the numbers
# plotted there rather than retyped.
refs=$(python3 - "$FIG" <<'PY'
import json, os, sys
names = {"null": "do nothing", "repro_published": "SWIM reactive", "pla": "PLA", "thallium": "Thallium"}
for r in json.load(open(sys.argv[1])):
    k = os.path.basename(r["run_dir"])
    if k in names:
        print(f"{names[k]}={r['utility_seams2017a']:.2f}")
PY
)
mapfile -t REFS <<< "$refs"
python3 pareto.py "$RUN" --pool all --reference-value "${REFS[@]}" \
    --group-labels "llm=prompt A" "formula=prompt B" -o "$RUN/pareto" | tail -20
echo "figures -> $RUN/{spider,spider_active,pareto}.png"
