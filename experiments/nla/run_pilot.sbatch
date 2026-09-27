#!/bin/bash --login
#SBATCH -p gpuH_short
#SBATCH -G 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH -t 0-03
#SBATCH -J selas-nla-pilot
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# The NLA pilot (pilot.py) on recorded gemma-3-27b-it runs: layer-41 vectors at
# the decision positions, the released AV's explanations, the AR's
# reconstruction scores, and the published worked example as a check.
#
#   SELAS_RUNS="prompts-clarknet-20260925-220652/k2-s0 ..." \
#       sbatch -A "$CSF_ACCOUNT" experiments/nla/run_pilot.sbatch
#
# Runs are directories under ~/selas-results. The pair (kitft/nla-gemma3-27b-L41-
# {av,ar}) and the target must already be in $HF_HOME: the job runs offline.
# Rerunning with the same SELAS_OUT reuses the captured vectors.
set -uo pipefail
: "${SLURM_JOB_ID:=$$}"
REPO="${SELAS_REPO:-$HOME/SELAS}"
RUNS="${SELAS_RUNS:?set SELAS_RUNS to run directories under ~/selas-results}"
OUT="${SELAS_OUT:-$HOME/selas-results/nla-pilot-$SLURM_JOB_ID}"
source "$HOME/selas-env.sh"
export HF_HOME="${HF_HOME:-$HOME/h200-scratch/hf}"
export HF_HUB_OFFLINE=1

args=()
for r in $RUNS; do
    d="$HOME/selas-results/$r"
    [ -d "$d" ] || { echo "no run directory $d" >&2; exit 1; }
    args+=("$d")
done

cd "$REPO/experiments/nla" || exit 1
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
python pilot.py "${args[@]}" -o "$OUT" ${SELAS_LIMIT:+--limit "$SELAS_LIMIT"}
status=$?
echo "exit $status -> $OUT"
exit $status
