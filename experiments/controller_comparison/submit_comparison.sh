#!/usr/bin/env bash
# Submits run_comparison.sbatch with the account from csf/local.env.
#   ./submit_comparison.sh                 # full length, default model (gemma-3-27b-it)
#   ./submit_comparison.sh --gemma27       # gemma-3-27b-it, the NLA-compatible target
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
GPUS=""         # resolved from the model below unless given explicitly
CORES=""

# The GPU count is a property of the weights, so deriving it beats a default
# that silently mismatches the model: SELAS_MODEL naming a bf16 70B while GPUS
# stayed at 1 would OOM on load, after queueing for the allocation. Same lesson
# as CONTROLLER/csf/submit.sh.
gpus_for_model() {
    case "$1" in
        *Llama-3.3-70B-Instruct-FP8*) echo 1 ;;   # ~73 GB
        *Llama-3.3-70B*)              echo 2 ;;   # ~141 GB: one H200 exactly, no KV room
        *gemma-3-27b*)                echo 1 ;;   # ~55 GB
        *gemma-3-12b*)                echo 1 ;;   # ~24 GB
        *Qwen2.5-14B*)                echo 1 ;;   # ~28 GB
        *) echo "WARNING: unknown model '$1'; assuming 1 GPU. Override with --gpus." >&2
           echo 1 ;;
    esac
}

while [ $# -gt 0 ]; do
    case "$1" in
        --short) export SELAS_SIM_LIMIT=1800s; TIME=0-02; shift ;;
        # FP8 70B is ~73 GB, so it fits one H200 with room for the KV cache. A
        # 1-GPU 8-core job also schedules far sooner: gpuH_short fills up, and a
        # small footprint slots into gaps a 2-GPU one waits days for.
        --fp8)    export SELAS_MODEL=nvidia/Llama-3.3-70B-Instruct-FP8; shift ;;
        --gemma27) export SELAS_MODEL=google/gemma-3-27b-it; shift ;;
        --model) export SELAS_MODEL="$2"; shift 2 ;;
        --gpus)  GPUS="$2"; shift 2 ;;
        --time)  TIME="$2"; shift 2 ;;
        -h|--help) sed -n '2,8p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

MODEL="${SELAS_MODEL:-google/gemma-3-27b-it}"
export SELAS_MODEL="$MODEL"
[ -n "$GPUS" ]  || GPUS=$(gpus_for_model "$MODEL")
[ -n "$CORES" ] || CORES=$(( GPUS * 8 ))       # 8 cores/GPU is the partition maximum

mkdir -p "$HERE/logs"
echo "submitting: $MODEL on ${GPUS}x GPU, ${CORES} cores, walltime $TIME"
sbatch -A "$CSF_ACCOUNT" -t "$TIME" -G "$GPUS" -n 1 -c "$CORES" "$HERE/run_comparison.sbatch"
