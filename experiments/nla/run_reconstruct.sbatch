#!/bin/bash --login
#SBATCH -p gpuA
#SBATCH -G 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH -t 0-01
#SBATCH -J selas-nla-recon
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# reconstruct.py on a finished pilot: the AR's vectors for its explanations.
# On gpuA (no -A; the cache copy on ~/scratch), or pass -p gpuH_short -A ...
# and SELAS_HF_HOME unset for the H200 cache.
#
#   SELAS_OUT=$HOME/selas-results/nla-pilot-clarknet-a100 sbatch experiments/nla/run_reconstruct.sbatch
set -uo pipefail
OUT="${SELAS_OUT:?set SELAS_OUT to a pilot output directory}"
export SELAS_HF_HOME="${SELAS_HF_HOME:-$HOME/scratch/hf}"
source "$HOME/selas-env.sh"
export HF_HUB_OFFLINE=1
cd "${SELAS_REPO:-$HOME/SELAS}/experiments/nla" || exit 1
python reconstruct.py "$OUT"
