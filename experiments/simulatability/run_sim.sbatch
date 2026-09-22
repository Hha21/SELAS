#!/bin/bash --login
#SBATCH -p gpuH_short
#SBATCH -G 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH -t 02:00:00
#SBATCH -J selas-sim
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# Leakage-adjusted simulatability for a recorded run. No simulator and no
# controller: every decision is rebuilt from its stored messages and scored
# under four conditions, so each model costs ~420 calls.
#
# Several models are served in turn on the one GPU, because "can a reader
# predict the action from this reasoning" depends on the reader, and a result
# that holds for only one of them is a fact about that model rather than about
# the explanation:
#
#   gemma-3-12b-it        same family as the controller. Same chat template and
#                         tokenizer, so the prompt renders identically and the
#                         only difference is capability.
#   Qwen2.5-14B-Instruct  a different family. Shares no pretraining idiosyncrasy
#                         with the controller, so an explanation that works here
#                         is not merely one written in a dialect the reader
#                         already speaks. Closest in spirit to the original,
#                         which simulates with T5.
#   the controller itself the ceiling. Bounds how much of any shortfall is the
#                         explanation and how much is the student being weaker
#                         at the task. Set SELAS_CEILING=0 to skip.
#
#   SELAS_RUN=cmp-20260921-163753 sbatch -A "$CSF_ACCOUNT" run_sim.sbatch

set -uo pipefail
: "${SLURM_JOB_ID:=$$}"
: "${SLURM_GPUS:=1}"

REPO="${SELAS_REPO:-$HOME/SELAS}"
STUDENTS="${SELAS_STUDENTS:-google/gemma-3-12b-it Qwen/Qwen2.5-14B-Instruct}"
TEACHER="${SELAS_MODEL:-google/gemma-3-27b-it}"
CEILING="${SELAS_CEILING:-1}"
SERVED=csf-llm
RUN="${SELAS_RUN:?set SELAS_RUN to a run directory name under ~/selas-results}"
OUT="$HOME/selas-results/$RUN"
PORT=$(( 29000 + SLURM_JOB_ID % 3000 ))

source "$HOME/selas-env.sh"
export HF_HOME="${HF_HOME:-$HOME/h200-scratch/hf}"
cd "$REPO/experiments/simulatability"

echo "run       $RUN"
echo "students  $STUDENTS"
echo "ceiling   $([ "$CEILING" = 1 ] && echo "$TEACHER" || echo skipped)"
echo "port      $PORT"
[ -d "$OUT/llm" ] || { echo "no llm arm under $OUT"; exit 1; }

VLLM_PID=
cleanup() { [ -n "$VLLM_PID" ] && kill "$VLLM_PID" 2>/dev/null; }
trap cleanup EXIT

# Serve one model and block until it answers, or give up with its log.
serve() {
    local model="$1" log="$2"
    cleanup; VLLM_PID=
    # vLLM releases the GPU asynchronously, so the next server must not start
    # until the last one is gone or it fails on memory that is about to free.
    for _ in $(seq 1 60); do
        pgrep -u "$USER" -f "vllm.entrypoints" >/dev/null || break
        sleep 2
    done
    python -m vllm.entrypoints.openai.api_server \
        --model "$model" --served-model-name "$SERVED" \
        --tensor-parallel-size "$SLURM_GPUS" --host 127.0.0.1 --port "$PORT" \
        --max-model-len 8192 --max-logprobs 30 --dtype auto > "$log" 2>&1 &
    VLLM_PID=$!
    # Generous: an uncached model downloads before it serves.
    for _ in $(seq 1 180); do
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
}

# A model that fails does not take the others down with it: an uncached
# download that dies should not lose the results already in hand.
FAILED=()
for model in $STUDENTS; do
    tag=$(basename "$model" | tr 'A-Z' 'a-z')
    echo; echo "=== student: $model ==="
    run_one "$model" "$tag" || FAILED+=("$model")
done

if [ "$CEILING" = 1 ]; then
    echo; echo "=== ceiling: $TEACHER (the controller scoring its own reasoning) ==="
    run_one "$TEACHER" ceiling || FAILED+=("$TEACHER (ceiling)")
fi

echo
if [ ${#FAILED[@]} -gt 0 ]; then
    echo "FAILED for: ${FAILED[*]}" >&2
    exit 1
fi
echo "done -> $OUT/simulatability_*.json"
