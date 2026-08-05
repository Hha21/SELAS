#!/usr/bin/env bash
# Reverse of start_polaris.sh -- stops the dashboard bridge, the POLARIS tmux
# session, and the SWIM + NATS containers.
#
# Containers are stopped, not removed, so the next start is fast (no re-pull or
# re-init). Pass --rm to remove them entirely.
#
# Usage: ./stop_polaris.sh [--rm]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$ROOT/lib.sh"

RM=false
case "${1:-}" in
    --rm) RM=true ;;
    -h|--help)
        echo "Usage: ./stop_polaris.sh [--rm]"
        echo "  --rm    also remove the SWIM and NATS containers"
        exit 0 ;;
    "") ;;
    *) err "Unknown option: $1"; exit 1 ;;
esac

stop_service "Dashboard bridge" "$RUN_DIR/bridge.pid" "scripts/dashboard_bridge.py"

info "Stopping POLARIS + SWIM"
# Reuse POLARIS's own stop script rather than duplicating its knowledge of the
# tmux session name and the container names.
if $RM; then
    "$ROOT/POLARIS/polaris_poc/stop_polaris_swim_system.sh" --rm
else
    "$ROOT/POLARIS/polaris_poc/stop_polaris_swim_system.sh"
fi

ok "POLARIS + SWIM stopped"
warn_if_listening "${BRIDGE_PORT:-8090}" 4222 4242
exit 0
