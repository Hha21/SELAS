#!/bin/bash --login
#SBATCH -p gpuH_short
#SBATCH -G 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH -t 01:00:00
#SBATCH -J selas-sim
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# Leakage-adjusted simulatability for a recorded run. No simulator and no
# controller: every decision is rebuilt from its stored messages and scored
# under four conditions, so the whole thing is ~420 calls per model.
#
# Two models are served in turn on the one GPU. The student is the score; the
# controller's own model is the ceiling, and the gap between them separates
# "the explanation does not carry the decision" from "this student cannot do
# the task at all". Set SELAS_CEILING=0 to skip it.
#
#   SELAS_RUN=cmp-20260921-163753 sbatch -A "$CSF_ACCOUNT" run_sim.sbatch

set -uo pipefail
: "${SLURM_JOB_ID:=$$}"
: "${SLURM_GPUS:=1}"

REPO="${SELAS_REPO:-$HOME/SELAS}"
STUDENT="${SELAS_STUDENT:-google/gemma-3-12b-it}"
TEACHER="${SELAS_MODEL:-google/gemma-3-27b-it}"
CEILING="${SELAS_CEILING:-1}"
SERVED=csf-llm
RUN="${SELAS_RUN:?set SELAS_RUN to a run directory name under ~/selas-results}"
OUT="$HOME/selas-results/$RUN"
PORT=$(( 29000 + SLURM_JOB_ID % 3000 ))

source "$HOME/selas-env.sh"
export HF_HOME="${HF_HOME:-$HOME/h200-scratch/hf}"
cd "$REPO/experiments/simulatability"

echo "run      $RUN"
echo "student  $STUDENT"
echo "ceiling  $([ "$CEILING" = 1 ] && echo "$TEACHER" || echo skipped)"
[ -d "$OUT/llm" ] || { echo "no llm arm under $OUT"; exit 1; }

VLLM_PID=
cleanup() { [ -n "$VLLM_PID" ] && kill "$VLLM_PID" 2>/dev/null; }
trap cleanup EXIT

# Serve one model and block until it answers, or give up with its log. Called
# once per model; the previous server is stopped first so the GPU is free.
serve() {
    local model="$1" log="$2"
    cleanup; VLLM_PID=
    # vLLM releases the GPU asynchronously; starting the next server before it
    # has would fail on memory that is about to be freed.
    for _ in $(seq 1 30); do
        pgrep -u "$USER" -f "vllm.entrypoints" >/dev/null || break
        sleep 2
    done
    python -m vllm.entrypoints.openai.api_server \
        --model "$model" --served-model-name "$SERVED" \
        --tensor-parallel-size "$SLURM_GPUS" --host 127.0.0.1 --port "$PORT" \
        --max-model-len 8192 --max-logprobs 30 --dtype auto > "$log" 2>&1 &
    VLLM_PID=$!
    for _ in $(seq 1 90); do
        curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
        kill -0 "$VLLM_PID" 2>/dev/null || { echo "vLLM died serving $model:"; tail -25 "$log"; return 1; }
        sleep 10
    done
    curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 || {
        echo "vLLM never healthy for $model"; tail -25 "$log"; return 1; }
    echo "vLLM healthy: $model"
}

run_one() {
    local model="$1" tag="$2"
    serve "$model" "$OUT/sim_${tag}_vllm.log" || return 1
    python simulate.py "$OUT/llm" \
        --llm-base-url "http://127.0.0.1:$PORT/v1" --llm-model "$SERVED" \
        --label "$model" -o "$OUT/simulated_${tag}.jsonl" 2>&1 | tail -12
    local n
    n=$(wc -l < "$OUT/simulated_${tag}.jsonl" 2>/dev/null || echo 0)
    if [ "$n" -lt 50 ]; then
        echo "FAILED: only $n rows for $tag; the simulation did not run" >&2
        return 1
    fi
    echo
    python las.py "$OUT/simulated_${tag}.jsonl" -o "$OUT/simulatability_${tag}.json" 2>&1 | tail -40
    echo
}

echo; echo "=== student: $STUDENT ==="
run_one "$STUDENT" student || exit 1

if [ "$CEILING" = 1 ]; then
    echo "=== ceiling: $TEACHER (the controller scoring its own reasoning) ==="
    run_one "$TEACHER" ceiling || exit 1
fi

echo "done -> $OUT/simulatability_*.json"
