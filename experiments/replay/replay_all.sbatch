#!/bin/bash --login
#SBATCH -p gpuH_short
#SBATCH -G 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH -t 0-06
#SBATCH -J selas-replay
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# Every interpretability measurement, for every arm of a run, in one job.
#
# The arms are replayed CONCURRENTLY against one served model, the same trick
# the sweep itself uses for SWIM. Serially this is dominated by the
# counterfactual's generate mode -- 735 reasonings per arm at roughly half a
# second each, so about 27 minutes per arm and over three hours for five.
# Concurrently it is close to the cost of one arm, because the work is
# request-bound and vLLM batches across the callers.
#
# Model order is forced by what needs which. Faithfulness and the
# counterfactual re-score the controller's own decisions, so they need the
# controller's model; simulatability needs the students and then the controller
# again as a ceiling. So the controller's model is served once for the first
# two, then each student in turn.
#
#   SELAS_RUN=sweep-20260922-… SELAS_ARMS="llm free short zeroshot" \
#       sbatch -A "$CSF_ACCOUNT" replay_all.sbatch
#
# `none` is not replayable and must not be listed: it has no reasoning, so
# there is nothing to perturb and four of the five axes are undefined. It is
# the utility reference line on the Pareto plot, not a polygon.

set -uo pipefail
: "${SLURM_JOB_ID:=$$}"
: "${SLURM_GPUS:=1}"

REPO="${SELAS_REPO:-$HOME/SELAS}"
MODEL="${SELAS_MODEL:-google/gemma-3-27b-it}"
STUDENTS="${SELAS_STUDENTS:-google/gemma-3-12b-it Qwen/Qwen2.5-14B-Instruct}"
SERVED=csf-llm
RUN="${SELAS_RUN:?set SELAS_RUN to a run directory name under ~/selas-results}"
ARMS="${SELAS_ARMS:-llm}"
OUT="$HOME/selas-results/$RUN"
PORT=$(( 29000 + SLURM_JOB_ID % 3000 ))
BASE="http://127.0.0.1:$PORT/v1"

source "$HOME/selas-env.sh"
export HF_HOME="${HF_HOME:-$HOME/h200-scratch/hf}"

echo "run      $RUN"
echo "arms     $ARMS"
echo "model    $MODEL   students: $STUDENTS"
for a in $ARMS; do
    [ -d "$OUT/$a" ] || { echo "no arm directory $OUT/$a"; exit 1; }
    if [ "$a" = "none" ]; then
        echo "'none' has no reasoning to replay; drop it from SELAS_ARMS" >&2; exit 1
    fi
done

VLLM_PID=
cleanup() { [ -n "$VLLM_PID" ] && kill "$VLLM_PID" 2>/dev/null; }
trap cleanup EXIT

serve() {
    local model="$1" log="$2"
    cleanup; VLLM_PID=
    for _ in $(seq 1 60); do
        pgrep -u "$USER" -f "vllm.entrypoints" >/dev/null || break
        sleep 2
    done
    python -m vllm.entrypoints.openai.api_server \
        --model "$model" --served-model-name "$SERVED" \
        --tensor-parallel-size "$SLURM_GPUS" --host 127.0.0.1 --port "$PORT" \
        --max-model-len 8192 --max-logprobs 30 --dtype auto > "$log" 2>&1 &
    VLLM_PID=$!
    for _ in $(seq 1 180); do
        curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
        kill -0 "$VLLM_PID" 2>/dev/null || { echo "vLLM died serving $model:"; tail -25 "$log"; return 1; }
        sleep 10
    done
    curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 || {
        echo "vLLM never healthy for $model"; tail -25 "$log"; return 1; }
    echo "vLLM healthy: $model"
}

FAILED=()
# Each arm's whole battery in one background shell, so the arms overlap rather
# than the phases -- one slow arm does not hold the others at a barrier.
faith_and_cf() {
    local arm="$1" d="$OUT/$arm"
    {
        cd "$REPO/experiments/faithfulness" || exit 1
        python rescore.py "$d" --llm-base-url "$BASE" --llm-model "$SERVED" \
            -o "$d/rescored.jsonl" > "$d/replay_faith.log" 2>&1
        python analyse.py "$d/rescored.jsonl" -o "$d/faithfulness.json" \
            >> "$d/replay_faith.log" 2>&1

        cd "$REPO/experiments/counterfactual" || exit 1
        for mode in score generate; do
            python run_cf.py "$d" --mode "$mode" --llm-base-url "$BASE" \
                --llm-model "$SERVED" -o "$d/cf_${mode}.jsonl" \
                > "$d/replay_cf_${mode}.log" 2>&1
            python analyse_cf.py "$d/cf_${mode}.jsonl" \
                -o "$d/counterfactual_${mode}.json" >> "$d/replay_cf_${mode}.log" 2>&1
        done
    }
}

echo; echo "=== faithfulness + counterfactual: $MODEL ==="
serve "$MODEL" "$OUT/replay_vllm_controller.log" || exit 1
pids=""
for arm in $ARMS; do faith_and_cf "$arm" & pids="$pids $!"; echo "  started $arm (pid $!)"; done
wait $pids
for arm in $ARMS; do
    for f in faithfulness.json counterfactual_score.json counterfactual_generate.json; do
        [ -s "$OUT/$arm/$f" ] || { echo "MISSING $arm/$f"; FAILED+=("$arm/$f"); }
    done
done

for student in $STUDENTS "$MODEL"; do
    tag=$([ "$student" = "$MODEL" ] && echo ceiling || basename "$student" | tr 'A-Z' 'a-z')
    echo; echo "=== simulatability ($tag): $student ==="
    serve "$student" "$OUT/replay_vllm_${tag}.log" || { FAILED+=("serve $student"); continue; }
    pids=""
    for arm in $ARMS; do
        d="$OUT/$arm"
        {
            cd "$REPO/experiments/simulatability" || exit 1
            python simulate.py "$d" --llm-base-url "$BASE" --llm-model "$SERVED" \
                --label "$student" -o "$d/simulated_${tag}.jsonl" \
                > "$d/replay_sim_${tag}.log" 2>&1
            python las.py "$d/simulated_${tag}.jsonl" \
                -o "$d/simulatability_${tag}.json" >> "$d/replay_sim_${tag}.log" 2>&1
        } & pids="$pids $!"
    done
    wait $pids
    for arm in $ARMS; do
        [ -s "$OUT/$arm/simulatability_${tag}.json" ] || FAILED+=("$arm/simulatability_${tag}.json")
    done
done
cleanup; VLLM_PID=

echo; echo "=== per-arm summary ==="
for arm in $ARMS; do
    echo "--- $arm"
    ls -1 "$OUT/$arm"/{faithfulness,counterfactual_*,simulatability_*}.json 2>/dev/null \
        | sed 's|.*/|      |' || echo "      nothing"
done

echo
if [ ${#FAILED[@]} -gt 0 ]; then echo "FAILED: ${FAILED[*]}" >&2; exit 1; fi
echo "done -> $OUT/<arm>/*.json"
