#!/bin/bash --login
#SBATCH -p gpuH_short
#SBATCH -G 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH -t 00:45:00
#SBATCH -J selas-sweep
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# Replays every recorded decision under each intervention against a served
# model. No simulator: the decision is reconstructed from the stored messages,
# so the whole battery costs one scoring call per decision per arm rather than
# a 105-minute run each.
#
#   SELAS_RUN=cmp-20260921-163753 sbatch -A "$CSF_ACCOUNT" run_sweep.sbatch

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
cd "$REPO/experiments/faithfulness"

echo "run   $RUN"
echo "model $MODEL  port $PORT"
[ -d "$OUT/llm" ] || { echo "no llm arm under $OUT"; exit 1; }

python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" --served-model-name "$SERVED" \
    --tensor-parallel-size "$SLURM_GPUS" --host 127.0.0.1 --port "$PORT" \
    --max-model-len 8192 --max-logprobs 30 --dtype auto > "$OUT/sweep_vllm.log" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT

for _ in $(seq 1 60); do
    curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
    kill -0 $VLLM_PID 2>/dev/null || { echo "vLLM died:"; tail -25 "$OUT/sweep_vllm.log"; exit 1; }
    sleep 10
done
curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 || {
    echo "vLLM never healthy"; tail -25 "$OUT/sweep_vllm.log"; exit 1; }
echo "vLLM healthy"

python rescore.py "$OUT/llm" \
    --llm-base-url "http://127.0.0.1:$PORT/v1" --llm-model "$SERVED" \
    -o "$OUT/rescored.jsonl" 2>&1 | tail -20

echo
python analyse.py "$OUT/rescored.jsonl" -o "$OUT/faithfulness.json" 2>&1 | tail -40

# An empty sweep must not look like a finished one.
n=$(wc -l < "$OUT/rescored.jsonl" 2>/dev/null || echo 0)
if [ "$n" -lt 50 ]; then
    echo "FAILED: only $n rescored rows; the sweep did not run" >&2
    exit 1
fi
echo; echo "done: $n rows -> $OUT"
