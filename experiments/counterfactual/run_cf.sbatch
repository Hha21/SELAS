#!/bin/bash --login
#SBATCH -p gpuH_short
#SBATCH -G 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH -t 02:00:00
#SBATCH -J selas-cf
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# Counterfactual edits on a recorded run: both modes, one served model.
#
#   score     ~735 scoring calls. Holds the reasoning fixed and edits the
#             telemetry under it, so the action must follow one or the other.
#   generate  ~735 generations plus ~735 scorings. The counterfactual proper,
#             and the only mode that can check whether the new reasoning
#             reports the number that was substituted into it.
#
#   SELAS_RUN=cmp-20260921-163753 sbatch -A "$CSF_ACCOUNT" run_cf.sbatch

set -uo pipefail
: "${SLURM_JOB_ID:=$$}"
: "${SLURM_GPUS:=1}"

REPO="${SELAS_REPO:-$HOME/SELAS}"
MODEL="${SELAS_MODEL:-google/gemma-3-27b-it}"
SERVED=csf-llm
RUN="${SELAS_RUN:?set SELAS_RUN to a run directory name under ~/selas-results}"
OUT="$HOME/selas-results/$RUN"
PORT=$(( 29000 + SLURM_JOB_ID % 3000 ))

source "$HOME/selas-env.sh"
export HF_HOME="${HF_HOME:-$HOME/h200-scratch/hf}"
cd "$REPO/experiments/counterfactual"

echo "run   $RUN"
echo "model $MODEL  port $PORT"
[ -d "$OUT/llm" ] || { echo "no llm arm under $OUT"; exit 1; }

python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" --served-model-name "$SERVED" \
    --tensor-parallel-size "$SLURM_GPUS" --host 127.0.0.1 --port "$PORT" \
    --max-model-len 8192 --max-logprobs 30 --dtype auto > "$OUT/cf_vllm.log" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT

for _ in $(seq 1 90); do
    curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
    kill -0 $VLLM_PID 2>/dev/null || { echo "vLLM died:"; tail -25 "$OUT/cf_vllm.log"; exit 1; }
    sleep 10
done
curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 || {
    echo "vLLM never healthy"; tail -25 "$OUT/cf_vllm.log"; exit 1; }
echo "vLLM healthy"

FAILED=()
for mode in score generate; do
    echo; echo "=== mode: $mode ==="
    python run_cf.py "$OUT/llm" --mode "$mode" \
        --llm-base-url "http://127.0.0.1:$PORT/v1" --llm-model "$SERVED" \
        -o "$OUT/cf_${mode}.jsonl" 2>&1 | tail -12
    n=$(wc -l < "$OUT/cf_${mode}.jsonl" 2>/dev/null || echo 0)
    if [ "$n" -lt 100 ]; then
        echo "FAILED: only $n rows in $mode mode" >&2
        FAILED+=("$mode"); continue
    fi
    echo
    python analyse_cf.py "$OUT/cf_${mode}.jsonl" -o "$OUT/counterfactual_${mode}.json" 2>&1 | tail -40
done

echo
if [ ${#FAILED[@]} -gt 0 ]; then echo "FAILED for: ${FAILED[*]}" >&2; exit 1; fi
echo "done -> $OUT/counterfactual_*.json"
