#!/bin/bash --login
#SBATCH -p gpuH_short
#SBATCH -G 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH -t 00:30:00
#SBATCH -J selas-verify
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# Proves the chat-format decision path against a live endpoint, and nothing
# else. Deliberately a batch job rather than an interactive allocation: the
# checks need no interaction, and salloc cancels its job the moment the
# requesting shell exits, so a request that has not been granted yet simply
# disappears. A short walltime is also far more backfillable -- gemma loads in
# about four minutes and the checks take seconds, so 30 minutes is generous.
#
# Submit with -A from csf/local.env:
#   source CONTROLLER/csf/local.env
#   sbatch -A "$CSF_ACCOUNT" CONTROLLER/csf/verify_chat.sbatch

set -uo pipefail
: "${SLURM_JOB_ID:=$$}"
: "${SLURM_CPUS_PER_TASK:=8}"

REPO="${SELAS_REPO:-$HOME/SELAS}"
MODEL="${SELAS_MODEL:-google/gemma-3-27b-it}"
SERVED=csf-llm
PORT=$(( 26000 + SLURM_JOB_ID % 3000 ))
OUT="$HOME/selas-results/verify-chat-$SLURM_JOB_ID"

source "$HOME/selas-env.sh"
export HF_HOME="${HF_HOME:-$HOME/h200-scratch/hf}"
mkdir -p "$OUT"
cd "$REPO/CONTROLLER"

echo "node $(hostname)  model $MODEL  port $PORT"

# 1. The rendered turns, before any GPU work -- if the prompt is wrong there is
#    no point serving a model to score it.
echo; echo "=============== rendered chat turns ==============="
python run_controller.py --print-prompt --prompt-format chat --probe 2>/dev/null \
  || python - <<'PY'
import sys; sys.path.insert(0, ".")
from controller import ContextBuilder, Trajectory, synthetic_observation
b = ContextBuilder(); t = Trajectory(); t.record_observation(0, synthetic_observation())
msgs, opts = b.build_messages(0, t)
for m in msgs:
    print(f"----- {m['role']} " + "-" * (56 - len(m['role'])))
    print(m["content"])
print("-" * 64)
print("options:", [f"{o}={a}" for o, a in opts])
PY

python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" --served-model-name "$SERVED" \
    --tensor-parallel-size "${SLURM_GPUS:-1}" --host 127.0.0.1 --port "$PORT" \
    --max-model-len 8192 --max-logprobs 30 --dtype auto > "$OUT/vllm.log" 2>&1 &
VLLM_PID=$!
trap 'kill $VLLM_PID 2>/dev/null' EXIT

for _ in $(seq 1 60); do
    curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
    kill -0 $VLLM_PID 2>/dev/null || { echo "vLLM died:"; tail -25 "$OUT/vllm.log"; exit 1; }
    sleep 10
done
curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 || {
    echo "vLLM never healthy"; tail -25 "$OUT/vllm.log"; exit 1; }
echo "vLLM healthy"

# 2. The real unknowns: does continue_final_message put the scored token where we
#    think, and do all eight options survive in top-k without the echo fallback?
echo; echo "=============== chat ==============="
python run_controller.py --check-backend --backend openai --prompt-format chat \
    --llm-base-url "http://127.0.0.1:$PORT/v1" --llm-model "$SERVED" 2>&1 | tee "$OUT/check_chat.txt"
CHAT_RC=${PIPESTATUS[0]}

# 3. Same decision on the old path, as a reference point.
echo; echo "=============== completion (reference) ==============="
python run_controller.py --check-backend --backend openai --prompt-format completion \
    --llm-base-url "http://127.0.0.1:$PORT/v1" --llm-model "$SERVED" 2>&1 | tee "$OUT/check_completion.txt"

echo; echo "chat check exit: $CHAT_RC   -> $OUT"
exit "$CHAT_RC"
