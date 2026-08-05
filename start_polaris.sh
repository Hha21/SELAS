#!/usr/bin/env bash
# Start the managing + managed system: SWIM, NATS, POLARIS's 9 components, and
# the dashboard bridge.
#
# This half needs Docker and tmux. It does NOT need a GPU or torch -- the
# reasoner reaches the model over plain HTTP, so the NLA server can be on
# another machine entirely (see start_nla.sh for the SSH tunnel).
#
# SWIM and NATS are brought up by POLARIS's own start_polaris_swim_system.sh,
# which owns the container names and the tmux session; this script does not
# duplicate that knowledge, it just sets the LLM backend and adds the bridge.
#
# The bridge lives on this side on purpose: it speaks NATS, and NLA deliberately
# has no nats-py. It exposes the traffic to the NLA frontend over HTTP instead.
#
# Usage: ./start_polaris.sh [options]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$ROOT/lib.sh"

BRIDGE_PORT="${BRIDGE_PORT:-8090}"
NLA_URL="${NLA_BASE_URL:-http://127.0.0.1:8000/v1}"
NLA_MODEL_NAME="${NLA_MODEL_NAME:-local-nla}"
USE_NLA=true

usage() {
    cat <<EOF
Usage: ./start_polaris.sh [options]

  --nla-url URL          OpenAI-compatible base URL for the reasoner
                         (default $NLA_URL -- an SSH -L tunnel to the GPU box)
  --nla-model NAME       model name sent to that endpoint (default $NLA_MODEL_NAME)
  --no-nla               leave the reasoner on its configured backend
                         (Gemini/OpenRouter) instead of pointing at NLA
  --bridge-port PORT     dashboard bridge port (default $BRIDGE_PORT)
  --no-bridge            skip the dashboard bridge
  -h, --help             this message

Defaults come from .env at the repo root (see .env.example); explicit flags win.
EOF
}

load_env
BRIDGE_PORT="${BRIDGE_PORT:-8090}"
NLA_URL="${NLA_BASE_URL:-$NLA_URL}"
NLA_MODEL_NAME="${NLA_MODEL_NAME:-$NLA_MODEL_NAME}"
WANT_BRIDGE=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --nla-url)     NLA_URL="$2"; shift 2 ;;
        --nla-model)   NLA_MODEL_NAME="$2"; shift 2 ;;
        --no-nla)      USE_NLA=false; shift ;;
        --bridge-port) BRIDGE_PORT="$2"; shift 2 ;;
        --no-bridge)   WANT_BRIDGE=false; shift ;;
        -h|--help)     usage; exit 0 ;;
        *) err "Unknown option: $1"; usage; exit 1 ;;
    esac
done

mkdir -p "$RUN_DIR"

# ------------------------------------------------------------------ preflight
command -v docker >/dev/null || { err "docker not found (needed for SWIM and NATS)"; exit 1; }
docker info >/dev/null 2>&1 || {
    err "docker daemon not reachable."
    err "If it is running, you are probably not in the 'docker' group:"
    err "  sudo usermod -aG docker \$USER   (then log out and back in)"
    exit 1; }
command -v tmux >/dev/null || { err "tmux not found -- POLARIS runs its components in tmux"; exit 1; }
[[ -x "$ROOT/POLARIS/.venv/bin/python" ]] || {
    err "POLARIS/.venv missing. Create it and:"
    err "  python3 -m venv POLARIS/.venv"
    err "  POLARIS/.venv/bin/pip install -r POLARIS/polaris_poc/requirements.txt"
    exit 1; }

# The reasoner is checked but not required to be up: POLARIS retries, and
# bringing SWIM up first is still useful when the GPU box is still loading.
if $USE_NLA; then
    if curl -sf --max-time 3 "${NLA_URL%/v1}/api/health" >/dev/null 2>&1; then
        ok "NLA server reachable at $NLA_URL"
    else
        warn "NLA server not reachable at $NLA_URL"
        warn "  Start it on the GPU box (./start_nla.sh) and open the tunnel:"
        warn "  ssh -L 8000:127.0.0.1:8000 -R $BRIDGE_PORT:127.0.0.1:$BRIDGE_PORT user@gpu-box"
        warn "  Continuing anyway -- the reasoner will fail its calls until it appears."
    fi
fi

# -------------------------------------------------------------------- bridge
# Started before POLARIS on purpose: it retries NATS internally, so starting it
# first means it does not miss the first messages POLARIS publishes.
if $WANT_BRIDGE; then
    PIDFILE="$RUN_DIR/bridge.pid"
    if is_running "$PIDFILE"; then
        warn "Dashboard bridge already running (pid $(cat "$PIDFILE"))"
    else
        info "Starting dashboard bridge on :$BRIDGE_PORT"
        (
            cd "$ROOT/POLARIS/polaris_poc" || exit 1
            setsid nohup ../.venv/bin/python src/scripts/dashboard_bridge.py \
                --port "$BRIDGE_PORT" \
                > "$RUN_DIR/bridge.log" 2>&1 < /dev/null &
            echo $! > "$PIDFILE"
        )
        sleep 2
        is_running "$PIDFILE" \
            && ok "Dashboard bridge on :$BRIDGE_PORT" \
            || { err "bridge failed to start:"; tail -n 10 "$RUN_DIR/bridge.log" >&2; }
    fi
fi

# ------------------------------------------------------------- SWIM + POLARIS
info "Starting SWIM + POLARIS (also brings up the NATS container)"
LLM_ARGS=()
if $USE_NLA; then
    LLM_ARGS=(--llm-provider openai_compatible
              --llm-model    "$NLA_MODEL_NAME"
              --llm-base-url "$NLA_URL")
    info "  reasoner LLM -> $NLA_URL"
else
    warn "  --no-nla: leaving the reasoner on its configured LLM backend"
fi

# start_polaris_swim_system.sh ends with `exec tmux attach-session`, which cannot
# succeed without a TTY. That failure is expected and harmless -- the components
# are already running detached by then -- so success is judged by the tmux
# session existing, not by the exit code.
(
    cd "$ROOT/POLARIS/polaris_poc" || exit 1
    OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-local}" \
    ./start_polaris_swim_system.sh "${LLM_ARGS[@]}" \
        > "$RUN_DIR/polaris-start.log" 2>&1 < /dev/null
)
if tmux has-session -t polaris-swim 2>/dev/null; then
    ok "POLARIS running in tmux session 'polaris-swim'"
else
    err "POLARIS did not start. Last lines of run/polaris-start.log:"
    tail -n 25 "$RUN_DIR/polaris-start.log" >&2
    exit 1
fi

echo
echo "  POLARIS components     tmux attach-session -t polaris-swim"
echo "  POLARIS logs           $ROOT/POLARIS/polaris_poc/logs/"
echo "  SWIM (noVNC)           http://localhost:6901/"
echo "  Bridge log             $RUN_DIR/bridge.log"
echo
echo "  Stop                   ./stop_polaris.sh"
echo
