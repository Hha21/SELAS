#!/bin/bash --login
#SBATCH -p multicore
#SBATCH -n 1
#SBATCH -c 4
#SBATCH -t 00:45:00
#SBATCH -J selas-builtin
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# SWIM's built-in managers over a pre-committed run list. CPU only.
#   sbatch -A "$CSF_ACCOUNT" run_builtin.sbatch
set -uo pipefail
REPO="${SELAS_REPO:-$HOME/SELAS}"
OUT="${SELAS_OUT:-$HOME/selas-results/builtin-$(date -u +%Y%m%d-%H%M%S)}"
cd "$REPO/experiments/builtin_baselines"
./run_builtin.sh runs.txt "$OUT" "${SLURM_CPUS_PER_TASK:-4}"
