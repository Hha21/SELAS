#!/bin/bash --login
#SBATCH -p gpuH_short
#SBATCH -G 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH -t 0-08
#SBATCH -J selas-llm
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# Serves an OpenAI-compatible endpoint on the H200s for CONTROLLER to score
# against. Draft: confirm against csf/recon.sh output before first submission --
# it assumes a venv with vLLM at $VENV and weights reachable via $HF_HOME.
#
#   -G 1   gemma-3-27b-it at bf16 is ~54 GB, comfortable on one 141 GB H200
#          with room for KV cache. For Llama-3.3-70B-Instruct (~141 GB, one
#          H200 exactly, nothing left over) override at submit time:
#            SELAS_MODEL=meta-llama/Llama-3.3-70B-Instruct sbatch -G 2 -c 16 \
#                csf/serve_llm.sbatch
#          Command-line flags override #SBATCH and must precede the filename.
#   -c 8   cores, not tasks: vLLM is a single process, and `-n 8 -c 1` would
#          leave it seeing one CPU. 8 cores/GPU is the partition maximum.
#   -A     required on gpuH*, and deliberately NOT a #SBATCH line here: Slurm
#          parses these before any shell runs, so no variable would expand and
#          the account would have to be committed as a literal. It is passed at
#          submit time instead -- use csf/submit.sh, which reads it from the
#          gitignored csf/local.env.
#
#          Do not assume the account in the CSF documentation is one of yours.
#          gpuH lists a specific AllowAccounts set, and only some associations
#          are in it; `sbatch --test-only` reports where a job would land
#          without submitting anything, which is the cheap way to find out.
#
# logs/ must exist BEFORE submission -- Slurm opens the -o/-e files before the
# body runs, so mkdir here is too late.

set -euo pipefail

MODEL="${SELAS_MODEL:-google/gemma-3-27b-it}"
SERVED_NAME="${SELAS_SERVED_NAME:-csf-llm}"
MAX_LEN="${SELAS_MAX_LEN:-8192}"
ENDPOINT_DIR="$HOME/h200-scratch/endpoints"

# A fixed port would collide with another job on the same node; derive one.
PORT=$(( 20000 + SLURM_JOB_ID % 20000 ))

module purge
module load libs/cuda/12.8.1
# vllm 0.19.1 / torch 2.10.0 (cu128, sm_90 in the arch list) are already
# installed into this interpreter's user site -- no venv to activate.
module load apps/binapps/anaconda3/2024.10

# Weights live on h200-scratch, not $TMPDIR: 141 GB is too large to stage per
# job, and $TMPDIR is destroyed at job end. h200-scratch is mounted on the H200
# compute nodes and the login nodes, which is exactly the two places that need it.
export HF_HOME="${HF_HOME:-$HOME/h200-scratch/hf}"
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export VLLM_LOGGING_LEVEL=INFO

echo "job $SLURM_JOB_ID on $(hostname)"
echo "gpus=$CUDA_VISIBLE_DEVICES cores=$SLURM_CPUS_PER_TASK port=$PORT"
echo "model=$MODEL  HF_HOME=$HF_HOME"
nvidia-smi --query-gpu=index,name,memory.total --format=csv

mkdir -p "$ENDPOINT_DIR"

# Fail fast if the weights are not already local. Without this vLLM would start
# a 141 GB download while holding two H200s idle, and quite possibly hit the
# wallclock before serving a single token.
if ! python - "$MODEL" <<'PYCHECK'
import sys, os
from huggingface_hub import snapshot_download
# The same ignore_patterns the download used. Without them snapshot_download
# counts the deliberately-skipped original/*.pth as missing and raises
# IncompleteSnapshotError on a cache that is in fact complete -- aborting the
# job over 141 GB of weights that are all present.
try:
    p = snapshot_download(sys.argv[1], ignore_patterns=["original/*", "*.pth"],
                          local_files_only=True)
except Exception as exc:
    print(f"weights not present locally under HF_HOME={os.environ.get('HF_HOME')}: "
          f"{type(exc).__name__}", file=sys.stderr)
    sys.exit(1)
print(f"weights: {p}")
PYCHECK
then
    echo "ABORTING: download the weights on a login node first, e.g." >&2
    echo "  HF_HOME=\$HOME/h200-scratch/hf python ~/fetch_weights.py $MODEL" >&2
    exit 1
fi

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
        echo "tunnel:  ssh -L 8000:$(hostname):$PORT \$CSF_USER@csf3.itservices.manchester.ac.uk"
        break
    fi
    sleep 10
done

# Remove the endpoint file when the server goes away, so a stale file never
# points at a node that is no longer serving.
trap 'rm -f "$ENDPOINT_DIR/$SLURM_JOB_ID.json" "$ENDPOINT_DIR/latest.json"' EXIT
wait "$SERVER_PID"
