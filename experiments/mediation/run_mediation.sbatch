#!/bin/bash --login
#SBATCH -p gpuH_short
#SBATCH -G 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH -t 0-04
#SBATCH -J selas-mediation
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# The objective-swap mediation experiment (run_mediation.py) on recorded runs,
# all specs concurrently against one served controller model.
#
#   SELAS_SPECS="prompts-clarknet-20260925-220652/k2-words-s0:priority:priority-no3 ..." \
#       sbatch -A "$CSF_ACCOUNT" run_mediation.sbatch
#
# A spec is RUN/ARM:FROM:TO -- a run directory under ~/selas-results, the arm,
# the objective the arm used, and the one to swap in. Output goes next to the
# arm's decisions as mediation_<TO>.jsonl and .json.
set -uo pipefail
: "${SLURM_JOB_ID:=$$}"
: "${SLURM_GPUS:=1}"
REPO="${SELAS_REPO:-$HOME/SELAS}"
MODEL="${SELAS_MODEL:-google/gemma-3-27b-it}"
SPECS="${SELAS_SPECS:?set SELAS_SPECS to RUN/ARM:FROM:TO tokens}"
SERVED=csf-llm
PORT=$(( 26000 + SLURM_JOB_ID % 3000 ))
BASE="http://127.0.0.1:$PORT/v1"
source "$HOME/selas-env.sh"
export HF_HOME="${HF_HOME:-$HOME/h200-scratch/hf}"

for spec in $SPECS; do
    d="$HOME/selas-results/${spec%%:*}"
    [ -d "$d" ] || { echo "no arm directory $d" >&2; exit 1; }
done

python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" --served-model-name "$SERVED" \
    --tensor-parallel-size "$SLURM_GPUS" --host 127.0.0.1 --port "$PORT" \
    --max-model-len 8192 --max-logprobs 30 --dtype auto > "logs/mediation_vllm_$SLURM_JOB_ID.log" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT
for _ in $(seq 1 180); do
    curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
    kill -0 "$VLLM_PID" 2>/dev/null || { echo "vLLM died"; tail -25 "logs/mediation_vllm_$SLURM_JOB_ID.log"; exit 1; }
    sleep 10
done
curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 || { echo "vLLM never healthy"; exit 1; }
echo "vLLM healthy: $MODEL"

cd "$REPO/experiments/mediation" || exit 1
pids=""; outs=()
for spec in $SPECS; do
    IFS=: read -r path old new <<< "$spec"
    d="$HOME/selas-results/$path"
    out="$d/mediation_${new}.jsonl"; outs+=("$out")
    python run_mediation.py "$d" --from "$old" --to "$new" --llm-base-url "$BASE" \
        --llm-model "$SERVED" -o "$out" > "$d/mediation_${new}.log" 2>&1 &
    pids="$pids $!"
    echo "  started $path ($old -> $new)"
done
wait $pids

echo "=== summary ==="
bad=0
for out in "${outs[@]}"; do
    [ -s "$out" ] || { echo "MISSING $out"; bad=1; continue; }
    python analyse_mediation.py "$out" -o "${out%.jsonl}.json"
done
exit $bad
