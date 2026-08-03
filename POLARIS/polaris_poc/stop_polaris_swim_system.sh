#!/usr/bin/env bash
# Reverse of start_polaris_swim_system.sh -- kills the tmux session and stops
# the SWIM + NATS Docker containers. Containers are stopped, not removed (so
# the next start_polaris_swim_system.sh run is fast, no re-pull/re-init),
# unless --rm is passed.
#
# Usage: ./stop_polaris_swim_system.sh [--rm] [session-name]
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMUX_SESSION="polaris-swim"
RM=false

for arg in "$@"; do
    case "$arg" in
        --rm) RM=true ;;
        *) TMUX_SESSION="$arg" ;;
    esac
done

if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "Killing tmux session: $TMUX_SESSION"
    tmux kill-session -t "$TMUX_SESSION"
else
    echo "No tmux session named '$TMUX_SESSION' found."
fi

if [[ "$RM" == true ]]; then
    if docker rm -f polaris-nats &>/dev/null; then
        echo "polaris-nats container removed"
    else
        echo "No polaris-nats container found."
    fi
    "$SCRIPT_DIR/../../SWIM/stop_swim.sh" --rm
else
    if docker stop polaris-nats &>/dev/null; then
        echo "polaris-nats container stopped"
    else
        echo "No running polaris-nats container found."
    fi
    "$SCRIPT_DIR/../../SWIM/stop_swim.sh"
fi

echo "POLARIS SWIM system stopped."
