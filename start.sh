#!/usr/bin/env bash
# Start the full experimental setup: NLA server + dashboard bridge + POLARIS + SWIM.
#
#   NLA server   holds the target model resident, serves the OpenAI-compatible
#                endpoint POLARIS calls, writes activation traces, serves the UI
#   bridge       mirrors POLARIS's NATS traffic to the UI's architecture view
#   POLARIS      the managing system (9 components in a tmux session)
#   SWIM         the managed system (Docker container, TCP control on 4242)
#
# The pieces are independent on purpose -- each can be started alone with
# --only. Stop everything with ./stop.sh
#
# Usage: ./start.sh [options]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT/run"

NLA_PORT=8000
BRIDGE_PORT=8090
DEVICE=""                       # blank -> NLA/src/config.py decides (cuda if present)
MODEL=""                        # blank -> NLA_MODEL_ID default (Qwen2.5-0.5B)
MAX_NEW_TOKENS=256
ONLY=""
WAIT_MODEL=300                  # seconds to allow for loading T + AV + AR

RED=$'\033[0;31m'; GRN=$'\033[0;32m'; YLW=$'\033[1;33m'; BLU=$'\033[0;34m'; NC=$'\033[0m'
info()  { echo "${BLU}[INFO]${NC} $*"; }
ok()    { echo "${GRN}[ OK ]${NC} $*"; }
warn()  { echo "${YLW}[WARN]${NC} $*"; }
err()   { echo "${RED}[FAIL]${NC} $*" >&2; }

usage() {
    cat <<EOF
Usage: ./start.sh [options]

  --only nla|polaris     start just one part (default: everything)
  --nla-port PORT        NLA server port (default $NLA_PORT)
  --bridge-port PORT     dashboard bridge port (default $BRIDGE_PORT)
  --device cpu|cuda      override NLA_DEVICE
  --model REPO_ID        override NLA_MODEL_ID (e.g. Qwen/Qwen2.5-7B)
  --max-new-tokens N     generation cap per LLM call (default $MAX_NEW_TOKENS)
  -h, --help             this message

Logs and pidfiles go to run/ (gitignored).
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --only)            ONLY="$2"; shift 2 ;;
        --nla-port)        NLA_PORT="$2"; shift 2 ;;
        --bridge-port)     BRIDGE_PORT="$2"; shift 2 ;;
        --device)          DEVICE="$2"; shift 2 ;;
        --model)           MODEL="$2"; shift 2 ;;
        --max-new-tokens)  MAX_NEW_TOKENS="$2"; shift 2 ;;
        -h|--help)         usage; exit 0 ;;
        *) err "Unknown option: $1"; usage; exit 1 ;;
    esac
done

if [[ -n "$ONLY" && "$ONLY" != "nla" && "$ONLY" != "polaris" ]]; then
    err "--only takes 'nla' or 'polaris'"; exit 1
fi
want_nla()     { [[ -z "$ONLY" || "$ONLY" == "nla"     ]]; }
want_polaris() { [[ -z "$ONLY" || "$ONLY" == "polaris" ]]; }

mkdir -p "$RUN_DIR"

# --------------------------------------------------------------- preflight
command -v docker >/dev/null || { err "docker not found (needed for SWIM and NATS)"; exit 1; }
docker info >/dev/null 2>&1   || { err "docker daemon not reachable"; exit 1; }

if want_polaris; then
    command -v tmux >/dev/null || { err "tmux not found -- POLARIS runs its components in tmux"; exit 1; }
    [[ -x "$ROOT/POLARIS/.venv/bin/python" ]] || {
        err "POLARIS/.venv missing. Create it and: POLARIS/.venv/bin/pip install -r POLARIS/polaris_poc/requirements.txt"
        exit 1; }
fi
if want_nla; then
    [[ -x "$ROOT/NLA/.venv/bin/python" ]] || {
        err "NLA/.venv missing. Create it and: NLA/.venv/bin/pip install -r NLA/requirements.txt"
        exit 1; }

    # Checkpoints live in models/<backbone>/, matching src/config.py's
    # CHECKPOINT_DIR. Warn rather than fail: the OpenAI-compatible endpoint and
    # trace capture need only the target model, so POLARIS can run without the
    # AV/AR pair -- it is the explanations that would be unavailable.
    ckpt_dir="$ROOT/NLA/models/$(basename "${MODEL:-Qwen/Qwen2.5-0.5B}")"
    if [[ ! -f "$ckpt_dir/av.pt" || ! -f "$ckpt_dir/ar.pt" ]]; then
        warn "No av.pt/ar.pt in $ckpt_dir -- the server will fail to load."
        warn "See NLA/models/README.md for how to fetch them (rsync from the workstation)."
    fi
fi

# is_running <pidfile>
is_running() { [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null; }

# ------------------------------------------------------------- NLA server
if want_nla; then
    PIDFILE="$RUN_DIR/nla-server.pid"
    if is_running "$PIDFILE"; then
        warn "NLA server already running (pid $(cat "$PIDFILE"))"
    else
        info "Starting NLA server on :$NLA_PORT"
        (
            cd "$ROOT/NLA" || exit 1
            [[ -n "$DEVICE" ]] && export NLA_DEVICE="$DEVICE"
            [[ -n "$MODEL"  ]] && export NLA_MODEL_ID="$MODEL"
            export NLA_MAX_NEW_TOKENS="$MAX_NEW_TOKENS"
            export POLARIS_BRIDGE_URL="http://127.0.0.1:$BRIDGE_PORT"
            export NLA_RUN_ID="${NLA_RUN_ID:-$(date -u +run-%Y%m%d-%H%M%S)}"
            setsid nohup ./.venv/bin/uvicorn server.main:app \
                --host 0.0.0.0 --port "$NLA_PORT" \
                > "$RUN_DIR/nla-server.log" 2>&1 < /dev/null &
            echo $! > "$PIDFILE"
        )
        info "Waiting for the model to load (up to ${WAIT_MODEL}s; first run also downloads weights)"
        deadline=$((SECONDS + WAIT_MODEL))
        until curl -sf --max-time 3 "http://127.0.0.1:$NLA_PORT/api/health" >/dev/null 2>&1; do
            if ! is_running "$PIDFILE"; then
                err "NLA server exited during startup. Last lines:"
                tail -n 15 "$RUN_DIR/nla-server.log" >&2
                exit 1
            fi
            (( SECONDS > deadline )) && { err "NLA server did not become healthy in ${WAIT_MODEL}s"; exit 1; }
            sleep 3
        done
        ok "NLA server healthy on :$NLA_PORT"
    fi

    # Bridge retries NATS internally, so it is safe to start before POLARIS.
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
        is_running "$RUN_DIR/bridge.pid" \
            && ok "Dashboard bridge on :$BRIDGE_PORT" \
            || { err "bridge failed to start:"; tail -n 10 "$RUN_DIR/bridge.log" >&2; }
    fi
fi

# --------------------------------------------------------- POLARIS + SWIM
if want_polaris; then
    info "Starting SWIM + POLARIS (this also brings up the NATS container)"
    LLM_ARGS=()
    if want_nla; then
        LLM_ARGS=(--llm-provider openai_compatible
                  --llm-model    local-nla
                  --llm-base-url "http://127.0.0.1:$NLA_PORT/v1")
        info "  reasoner LLM -> http://127.0.0.1:$NLA_PORT/v1 (local NLA server)"
    else
        warn "  --only polaris: leaving the reasoner on its configured LLM backend"
    fi

    # The POLARIS script ends with `exec tmux attach-session`, which cannot
    # succeed without a TTY. That failure is expected and harmless -- the
    # components are already running detached by then -- so success is judged
    # by the tmux session existing, not by the exit code.
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
fi

# ------------------------------------------------------------------ summary
echo
ok "Startup complete"
echo
if want_nla; then
    echo "  Activation Inspector   http://localhost:$NLA_PORT/"
    echo "  Architecture view      http://localhost:$NLA_PORT/architecture.html"
    echo "  API docs               http://localhost:$NLA_PORT/docs"
    echo "  Traces                 $ROOT/traces/"
fi
if want_polaris; then
    echo "  POLARIS components     tmux attach-session -t polaris-swim"
    echo "  POLARIS logs           $ROOT/POLARIS/polaris_poc/logs/"
    echo "  SWIM (noVNC)           http://localhost:6901/"
fi
echo "  Service logs           $RUN_DIR/"
echo
echo "  Stop everything        ./stop.sh"
echo
