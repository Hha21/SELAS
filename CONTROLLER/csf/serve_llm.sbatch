#!/bin/bash --login
#SBATCH -p gpuH_short
#SBATCH -A gpu-h200-fse-pgdr
#SBATCH -G 2
#SBATCH -n 1
#SBATCH -c 16
#SBATCH -t 0-08
#SBATCH -J selas-llm
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# Serves an OpenAI-compatible endpoint on the H200s for CONTROLLER to score
# against. Draft: confirm against csf/recon.sh output before first submission --
# it assumes a venv with vLLM at $VENV and weights reachable via $HF_HOME.
#
#   -G 2   70B at bf16 is ~141 GB, one H200 exactly, leaving nothing for KV
#          cache. Two GPUs is the minimum sane allocation, not a luxury.
#   -c 16  cores, not tasks: vLLM is a single process, and `-n 16 -c 1` would
#          leave it seeing one CPU. 8 cores/GPU is the partition maximum.
#   -A     required on gpuH*; the job is rejected outright without it.
#
# logs/ must exist BEFORE submission -- Slurm opens the -o/-e files before the
# body runs, so mkdir here is too late.

set -euo pipefail

WORKDIR="${SELAS_WORKDIR:-$HOME/selas}"
VENV="${SELAS_VENV:-$HOME/h200-scratch/venvs/vllm}"
MODEL="${SELAS_MODEL:-meta-llama/Llama-3.3-70B-Instruct}"
SERVED_NAME="${SELAS_SERVED_NAME:-csf-llm}"
MAX_LEN="${SELAS_MAX_LEN:-8192}"
ENDPOINT_DIR="$HOME/h200-scratch/endpoints"

# A fixed port would collide with another job on the same node; derive one.
PORT=$(( 20000 + SLURM_JOB_ID % 20000 ))

cd "$WORKDIR"
module purge
module load libs/cuda/12.8.1

# Weights live on h200-scratch, not $TMPDIR: 141 GB is too large to stage per
# job, and $TMPDIR is destroyed at job end.
export HF_HOME="${HF_HOME:-$HOME/h200-scratch/hf}"
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export VLLM_LOGGING_LEVEL=INFO

# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "job $SLURM_JOB_ID on $(hostname)"
echo "gpus=$CUDA_VISIBLE_DEVICES cores=$SLURM_CPUS_PER_TASK port=$PORT"
echo "model=$MODEL  HF_HOME=$HF_HOME"
nvidia-smi --query-gpu=index,name,memory.total --format=csv

mkdir -p "$ENDPOINT_DIR"

# --max-logprobs: the controller asks for the top 20 at the action position so
# that all eight options usually arrive in one request. vLLM's default cap is
# exactly 20; raising it leaves headroom and costs nothing.
python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --served-model-name "$SERVED_NAME" \
    --tensor-parallel-size "$SLURM_GPUS" \
    --host 0.0.0.0 \
    --port "$PORT" \
    --max-model-len "$MAX_LEN" \
    --max-logprobs 30 \
    --dtype bfloat16 &
SERVER_PID=$!

# Publish the endpoint only once the server actually answers, so the file's
# existence is a readiness signal rather than an intention.
for _ in $(seq 1 120); do
    if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
        cat > "$ENDPOINT_DIR/$SLURM_JOB_ID.json" <<JSON
{"job_id": "$SLURM_JOB_ID", "node": "$(hostname)", "port": $PORT,
 "model": "$SERVED_NAME", "hf_model": "$MODEL",
 "base_url": "http://127.0.0.1:$PORT/v1",
 "started": "$(date -uIseconds)"}
JSON
        cp "$ENDPOINT_DIR/$SLURM_JOB_ID.json" "$ENDPOINT_DIR/latest.json"
        echo "READY: $(hostname):$PORT  -> $ENDPOINT_DIR/$SLURM_JOB_ID.json"
        echo "tunnel:  ssh -L 8000:$(hostname):$PORT t95317ha@csf3.itservices.manchester.ac.uk"
        break
    fi
    sleep 10
done

# Remove the endpoint file when the server goes away, so a stale file never
# points at a node that is no longer serving.
trap 'rm -f "$ENDPOINT_DIR/$SLURM_JOB_ID.json" "$ENDPOINT_DIR/latest.json"' EXIT
wait "$SERVER_PID"
