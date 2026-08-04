#!/usr/bin/env bash
# Reverse of start.sh -- stops the NLA server, the dashboard bridge, the POLARIS
# tmux session, and the SWIM + NATS containers.
#
# Containers are stopped, not removed, so the next start is fast (no re-pull or
# re-init). Pass --rm to remove them entirely.
#
# Usage: ./stop.sh [--rm] [--only nla|polaris]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT/run"
RM=false
ONLY=""

GRN=$'\033[0;32m'; YLW=$'\033[1;33m'; BLU=$'\033[0;34m'; NC=$'\033[0m'
info() { echo "${BLU}[INFO]${NC} $*"; }
ok()   { echo "${GRN}[ OK ]${NC} $*"; }
warn() { echo "${YLW}[WARN]${NC} $*"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --rm)   RM=true; shift ;;
        --only) ONLY="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: ./stop.sh [--rm] [--only nla|polaris]"
            echo "  --rm    also remove the SWIM and NATS containers"
            echo "  --only  stop just one part"
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

want_nla()     { [[ -z "$ONLY" || "$ONLY" == "nla"     ]]; }
want_polaris() { [[ -z "$ONLY" || "$ONLY" == "polaris" ]]; }

# stop_service <name> <pidfile> <match>
# Terminates by pid, then falls back to a pattern match so a service started by
# hand (not through start.sh, so with no pidfile) is still cleaned up.
stop_service() {
    local name="$1" pidfile="$2" match="$3" pid stopped=false

    if [[ -f "$pidfile" ]]; then
        pid="$(cat "$pidfile")"
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            for _ in $(seq 1 20); do
                kill -0 "$pid" 2>/dev/null || { stopped=true; break; }
                sleep 0.5
            done
            $stopped || { kill -9 "$pid" 2>/dev/null; stopped=true; }
            ok "$name stopped (pid $pid)"
        fi
        rm -f "$pidfile"
    fi

    if ! $stopped; then
        local strays
        strays="$(pgrep -f "$match" 2>/dev/null || true)"
        if [[ -n "$strays" ]]; then
            # shellcheck disable=SC2086
            kill $strays 2>/dev/null
            sleep 1
            strays="$(pgrep -f "$match" 2>/dev/null || true)"
            # shellcheck disable=SC2086
            [[ -n "$strays" ]] && kill -9 $strays 2>/dev/null
            ok "$name stopped (matched '$match')"
        else
            info "$name was not running"
        fi
    fi
}

if want_nla; then
    stop_service "Dashboard bridge" "$RUN_DIR/bridge.pid"     "scripts/dashboard_bridge.py"
    stop_service "NLA server"       "$RUN_DIR/nla-server.pid" "uvicorn server.main:app"
fi

if want_polaris; then
    info "Stopping POLARIS + SWIM"
    # Reuse POLARIS's own stop script rather than duplicating its knowledge of
    # the tmux session name and container names.
    if $RM; then
        "$ROOT/POLARIS/polaris_poc/stop_polaris_swim_system.sh" --rm
    else
        "$ROOT/POLARIS/polaris_poc/stop_polaris_swim_system.sh"
    fi
fi

echo
ok "Shutdown complete"

leftovers=""
for port in 8000 8090 4222 4242; do
    if ss -ltn 2>/dev/null | grep -q ":$port "; then
        leftovers+=" $port"
    fi
done
[[ -n "$leftovers" ]] && warn "Still listening on:$leftovers (started outside start.sh?)"
exit 0
