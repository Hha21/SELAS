#!/usr/bin/env bash
# Submits run_comparison.sbatch with the account from csf/local.env.
#   ./submit_comparison.sh                 # full length, bf16 70B on 2 GPUs
#   ./submit_comparison.sh --fp8           # FP8 70B on 1 GPU -- schedules far sooner
#   ./submit_comparison.sh --short         # 1800s sim, ~30 min, for pipeline checks
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENVF="$HERE/../../CONTROLLER/csf/local.env"
[ -f "$ENVF" ] || { echo "missing $ENVF" >&2; exit 1; }
# shellcheck disable=SC1091
source "$ENVF"
: "${CSF_ACCOUNT:?set CSF_ACCOUNT in CONTROLLER/csf/local.env}"

TIME=0-04
GPUS=2          # matches the #SBATCH default: bf16 70B is ~141 GB, one H200 exactly
CORES=16

while [ $# -gt 0 ]; do
    case "$1" in
        --short) export SELAS_SIM_LIMIT=1800s; TIME=0-02; shift ;;
        # FP8 70B is ~73 GB, so it fits one H200 with room for the KV cache. A
        # 1-GPU 8-core job also schedules far sooner: gpuH_short fills up, and a
        # small footprint slots into gaps a 2-GPU one waits days for.
        --fp8)   export SELAS_MODEL=nvidia/Llama-3.3-70B-Instruct-FP8
                 GPUS=1; CORES=8; shift ;;
        --model) export SELAS_MODEL="$2"; shift 2 ;;
        --gpus)  GPUS="$2"; shift 2 ;;
        --time)  TIME="$2"; shift 2 ;;
        -h|--help) sed -n '2,8p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

mkdir -p "$HERE/logs"
echo "submitting: ${SELAS_MODEL:-<sbatch default>} on ${GPUS}x GPU, ${CORES} cores, walltime $TIME"
sbatch -A "$CSF_ACCOUNT" -t "$TIME" -G "$GPUS" -n 1 -c "$CORES" "$HERE/run_comparison.sbatch"
