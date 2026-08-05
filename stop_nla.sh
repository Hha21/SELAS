#!/usr/bin/env bash
# Reverse of start_nla.sh -- stops the NLA server.
#
# Nothing here is containerised, so there is no --rm equivalent. Traces already
# written are left alone: they are the output of the run, not scratch state.
#
# Usage: ./stop_nla.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$ROOT/lib.sh"

case "${1:-}" in
    -h|--help) echo "Usage: ./stop_nla.sh"; exit 0 ;;
    "") ;;
    *) err "Unknown option: $1"; exit 1 ;;
esac

stop_service "NLA server" "$RUN_DIR/nla-server.pid" "uvicorn server.main:app"

ok "NLA stopped"
warn_if_listening "${NLA_PORT:-8000}"
exit 0
