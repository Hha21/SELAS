#!/usr/bin/env bash
# Convenience wrapper: stop both halves on one machine.
#
# Reverse order of start.sh -- POLARIS first, so its reasoner is not mid-call
# against a model that has just gone away.
#
# Usage: ./stop.sh [--rm] [--only nla|polaris]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RM=""
ONLY=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --rm)   RM="--rm"; shift ;;
        --only) ONLY="$2"; shift 2 ;;
        -h|--help)
            cat <<EOF
Usage: ./stop.sh [--rm] [--only nla|polaris]

  --rm             also remove the SWIM and NATS containers
  --only nla       just the NLA server          (same as ./stop_nla.sh)
  --only polaris   just SWIM + POLARIS + bridge (same as ./stop_polaris.sh)
EOF
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

if [[ -n "$ONLY" && "$ONLY" != "nla" && "$ONLY" != "polaris" ]]; then
    echo "--only takes 'nla' or 'polaris'" >&2; exit 1
fi

if [[ "$ONLY" == "nla" ]]; then
    exec "$ROOT/stop_nla.sh"
fi
if [[ "$ONLY" == "polaris" ]]; then
    exec "$ROOT/stop_polaris.sh" $RM
fi

"$ROOT/stop_polaris.sh" $RM
"$ROOT/stop_nla.sh"
