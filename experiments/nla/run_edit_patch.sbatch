#!/bin/bash --login
#SBATCH -p gpuA
#SBATCH -G 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH -t 0-06
#SBATCH -J selas-nla-patch
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# edit_patch.py on a finished pilot: edit the AV's explanation at the action
# cue to name another option, reconstruct, patch layer 41, re-read the letter.
# On gpuA (no -A; the cache copy on ~/scratch), or pass -p gpuH_short -A ...
#
#   SELAS_PILOT=nla-gemma27b-final sbatch experiments/nla/run_edit_patch.sbatch
#
# SELAS_PILOT is a pilot.py output directory under ~/selas-results whose runs
# are also there. Output: ~/selas-results/$SELAS_PILOT/patch (or SELAS_OUT).
set -uo pipefail
REPO="${SELAS_REPO:-$HOME/SELAS}"
PILOT="$HOME/selas-results/${SELAS_PILOT:?set SELAS_PILOT to a pilot directory under ~/selas-results}"
OUT="${SELAS_OUT:-$PILOT/patch}"
source "$HOME/selas-env.sh"
export HF_HOME="${HF_HOME:-$HOME/h200-scratch/hf}"
export HF_HUB_OFFLINE=1

[ -s "$PILOT/explanations.jsonl" ] || { echo "no finished pilot in $PILOT" >&2; exit 1; }
cd "$REPO/experiments/nla" || exit 1
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
python edit_patch.py "$PILOT" -o "$OUT" ${SELAS_LIMIT:+--limit "$SELAS_LIMIT"} \
    ${SELAS_ALPHAS:+--alphas $SELAS_ALPHAS}
status=$?
[ $status -eq 0 ] && python analyse_patch.py "$OUT" -o "$OUT/patch.json"
echo "exit $status -> $OUT"
exit $status
