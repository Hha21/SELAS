#!/usr/bin/env bash
# Start the NLA server: the target model T, the AV/AR pair, activation trace
# capture, the OpenAI-compatible endpoint POLARIS calls, and the web UI.
#
# This half needs a GPU and torch. It does NOT need Docker, tmux, or NATS --
# nothing here talks to them, so this runs on a machine that has none of the
# three. POLARIS + SWIM are the other half: see start_polaris.sh.
#
# Split across two machines, the GPU box runs this and the Docker box runs the
# other, joined by one SSH command from the POLARIS side:
#
#     ssh -L 8000:127.0.0.1:8000 -R 8090:127.0.0.1:8090 user@gpu-box
#
#   -L 8000  POLARIS's reasoner reaches this server at 127.0.0.1:8000/v1
#   -R 8090  this server reaches POLARIS's dashboard bridge at 127.0.0.1:8090
#
# Both match the defaults below, so the tunnel needs no extra configuration.
#
# Usage: ./start_nla.sh [options]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$ROOT/lib.sh"

NLA_PORT="${NLA_PORT:-8000}"
BIND="${NLA_BIND:-127.0.0.1}"
BRIDGE_URL="${POLARIS_BRIDGE_URL:-}"
DEVICE="${NLA_DEVICE:-}"                # blank -> src/config.py decides
MODEL="${NLA_MODEL_ID:-}"               # blank -> config default (Qwen2.5-0.5B)
MAX_NEW_TOKENS="${NLA_MAX_NEW_TOKENS:-256}"
WAIT_MODEL="${NLA_WAIT_MODEL:-600}"     # 7B from cold cache is minutes, not seconds
FOREGROUND=false

usage() {
    cat <<EOF
Usage: ./start_nla.sh [options]

  --port PORT            listen port (default $NLA_PORT)
  --bind ADDR            bind address (default $BIND; 0.0.0.0 to expose directly)
  --device cpu|cuda|auto override NLA_DEVICE ('auto' shards across all GPUs)
  --model REPO_ID        override NLA_MODEL_ID (e.g. Qwen/Qwen2.5-7B-Instruct)
  --max-new-tokens N     generation cap per LLM call (default $MAX_NEW_TOKENS)
  --bridge-url URL       POLARIS dashboard bridge (default http://127.0.0.1:8090)
  --wait N               seconds to allow for model load (default $WAIT_MODEL)
  --foreground           run in this terminal instead of detaching
  -h, --help             this message

Defaults come from .env at the repo root (see .env.example); explicit flags win.
EOF
}

load_env
# load_env may have supplied these, so re-read after it runs.
NLA_PORT="${NLA_PORT:-8000}"
BIND="${NLA_BIND:-$BIND}"
DEVICE="${NLA_DEVICE:-$DEVICE}"
MODEL="${NLA_MODEL_ID:-$MODEL}"
MAX_NEW_TOKENS="${NLA_MAX_NEW_TOKENS:-$MAX_NEW_TOKENS}"
BRIDGE_URL="${POLARIS_BRIDGE_URL:-$BRIDGE_URL}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)            NLA_PORT="$2"; shift 2 ;;
        --bind)            BIND="$2"; shift 2 ;;
        --device)          DEVICE="$2"; shift 2 ;;
        --model)           MODEL="$2"; shift 2 ;;
        --max-new-tokens)  MAX_NEW_TOKENS="$2"; shift 2 ;;
        --bridge-url)      BRIDGE_URL="$2"; shift 2 ;;
        --wait)            WAIT_MODEL="$2"; shift 2 ;;
        --foreground)      FOREGROUND=true; shift ;;
        -h|--help)         usage; exit 0 ;;
        *) err "Unknown option: $1"; usage; exit 1 ;;
    esac
done

mkdir -p "$RUN_DIR"

# ------------------------------------------------------------------ preflight
[[ -x "$ROOT/NLA/.venv/bin/python" ]] || {
    err "NLA/.venv missing. Create it and:"
    err "  python3 -m venv NLA/.venv"
    err "  NLA/.venv/bin/pip install --no-cache-dir -r NLA/requirements.txt"
    exit 1; }

# Checkpoints live in models/<backbone>/, matching src/config.py's CHECKPOINT_DIR.
# Fail rather than warn: without the AV/AR pair the server raises on startup, and
# a clear message here beats a traceback 60s into loading.
# Two checkpoint forms are valid: a local av.pt/ar.pt from our own training, or
# a published HF pair resolved from CHECKPOINT_REPOS. config.py decides which,
# so ask it rather than re-implementing the rule here.
ckpt_check=$(
    cd "$ROOT/NLA" && NLA_MODEL_ID="${MODEL:-}" ./.venv/bin/python -c "
import sys
sys.path.insert(0, '.')
from src.config import AV_SOURCE, AR_SOURCE, MODEL_ID
if AV_SOURCE[0] is None or AR_SOURCE[0] is None:
    print(f'MISSING no AV/AR checkpoint for {MODEL_ID}')
else:
    print(f'OK {AV_SOURCE[0]}:{AV_SOURCE[1]} {AR_SOURCE[0]}:{AR_SOURCE[1]}')
" 2>/dev/null
)
if [[ "$ckpt_check" != OK* ]]; then
    err "${ckpt_check:-could not resolve checkpoints}"
    err "Provide NLA/models/<backbone>/{av,ar}.pt, or add the backbone to"
    err "CHECKPOINT_REPOS in NLA/src/config.py (public pairs: kitft/nla-*)."
    exit 1
fi
info "checkpoints ${ckpt_check#OK }"

PIDFILE="$RUN_DIR/nla-server.pid"
if is_running "$PIDFILE"; then
    warn "NLA server already running (pid $(cat "$PIDFILE")) -- ./stop_nla.sh first"
    exit 0
fi

export NLA_MAX_NEW_TOKENS="$MAX_NEW_TOKENS"
export POLARIS_BRIDGE_URL="${BRIDGE_URL:-http://127.0.0.1:8090}"
export NLA_RUN_ID="${NLA_RUN_ID:-$(date -u +run-%Y%m%d-%H%M%S)}"
[[ -n "$DEVICE" ]] && export NLA_DEVICE="$DEVICE"
[[ -n "$MODEL"  ]] && export NLA_MODEL_ID="$MODEL"

info "model      ${MODEL:-Qwen/Qwen2.5-0.5B}"
info "device     ${DEVICE:-auto-detect}"
info "bridge     $POLARIS_BRIDGE_URL"
info "run id     $NLA_RUN_ID"

if $FOREGROUND; then
    info "Starting NLA server on $BIND:$NLA_PORT (foreground; Ctrl-C to stop)"
    cd "$ROOT/NLA" || exit 1
    exec ./.venv/bin/uvicorn server.main:app --host "$BIND" --port "$NLA_PORT"
fi

info "Starting NLA server on $BIND:$NLA_PORT"
(
    cd "$ROOT/NLA" || exit 1
    setsid nohup ./.venv/bin/uvicorn server.main:app \
        --host "$BIND" --port "$NLA_PORT" \
        > "$RUN_DIR/nla-server.log" 2>&1 < /dev/null &
    echo $! > "$PIDFILE"
)

info "Waiting for the model to load (up to ${WAIT_MODEL}s; first run also downloads weights)"
deadline=$((SECONDS + WAIT_MODEL))
until curl -sf --max-time 3 "http://127.0.0.1:$NLA_PORT/api/health" >/dev/null 2>&1; do
    if ! is_running "$PIDFILE"; then
        err "NLA server exited during startup. Last lines:"
        tail -n 20 "$RUN_DIR/nla-server.log" >&2
        exit 1
    fi
    (( SECONDS > deadline )) && {
        err "NLA server did not become healthy in ${WAIT_MODEL}s (--wait to extend)"
        exit 1; }
    sleep 3
done
ok "NLA server healthy on $BIND:$NLA_PORT"

echo
echo "  Activation Inspector   http://localhost:$NLA_PORT/"
echo "  Architecture view      http://localhost:$NLA_PORT/architecture.html"
echo "  API docs               http://localhost:$NLA_PORT/docs"
echo "  Traces                 ${NLA_TRACE_DIR:-$ROOT/traces}/$NLA_RUN_ID"
echo "  Server log             $RUN_DIR/nla-server.log"
echo
echo "  Stop                   ./stop_nla.sh"
echo
