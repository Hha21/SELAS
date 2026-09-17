#!/usr/bin/env bash
# Submits serve_llm.sbatch with the account and overrides that must not be
# committed. Slurm parses #SBATCH lines before any shell runs, so -A cannot be a
# variable inside the job script -- it has to be supplied here.
#
#   ./submit.sh                 # default model on one GPU
#   ./submit.sh --70b           # Llama-3.3-70B-Instruct on two
#   ./submit.sh --gpus 2 --time 0-04
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --help must work before any configuration exists, or the first thing a new
# checkout does is fail at the one command meant to explain itself.
case "${1:-}" in -h|--help) sed -n '2,8p' "$0" | sed 's/^# \?//'; exit 0 ;; esac

[ -f "$HERE/local.env" ] || {
    echo "csf/local.env missing. Create it:" >&2
    echo "  cp $HERE/local.env.example $HERE/local.env && \$EDITOR $HERE/local.env" >&2
    exit 1; }
# shellcheck disable=SC1091
source "$HERE/local.env"

: "${CSF_ACCOUNT:?set CSF_ACCOUNT in csf/local.env}"
PARTITION="${CSF_PARTITION:-gpuH_short}"
MODEL="${SELAS_MODEL:-google/gemma-3-27b-it}"
GPUS=1
CORES=8
TIME=0-08
TEST_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --70b)   MODEL=meta-llama/Llama-3.3-70B-Instruct; GPUS=2; CORES=16; shift ;;
        --model) MODEL="$2"; shift 2 ;;
        --gpus)  GPUS="$2"; shift 2 ;;
        --cores) CORES="$2"; shift 2 ;;
        --time)  TIME="$2"; shift 2 ;;
        --test-only) TEST_ONLY=true; shift ;;
        -h|--help) sed -n '2,8p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# -o/-e directories must exist before submission: Slurm opens those files before
# the job body runs, so an mkdir inside the script would be too late.
mkdir -p "$HERE/../logs"

args=(-p "$PARTITION" -A "$CSF_ACCOUNT" -G "$GPUS" -n 1 -c "$CORES" -t "$TIME")
$TEST_ONLY && args+=(--test-only)

echo "submitting: $MODEL on ${GPUS}x GPU, $PARTITION, account $CSF_ACCOUNT, walltime $TIME"
SELAS_MODEL="$MODEL" sbatch "${args[@]}" "$HERE/serve_llm.sbatch"
