#!/usr/bin/env bash
# Convenience wrapper: start both halves on one machine.
#
# The halves are start_nla.sh (GPU, torch) and start_polaris.sh (Docker, tmux).
# They are separate scripts because they usually run on separate machines --
# the GPU box need not have Docker, and the Docker box need not have a GPU.
# This script exists for the case where one machine has both.
#
# Order matters: NLA first, because it is much the slowest to come up (a 7B
# target plus the AV/AR pair is minutes) and POLARIS's reasoner wants it there.
#
# Usage: ./start.sh [--only nla|polaris] [-- <args for that half>]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ONLY=""
PASSTHRU=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --only) ONLY="$2"; shift 2 ;;
        --)     shift; PASSTHRU=("$@"); break ;;
        -h|--help)
            cat <<EOF
Usage: ./start.sh [--only nla|polaris] [-- <args>]

  --only nla       just the NLA server          (same as ./start_nla.sh)
  --only polaris   just SWIM + POLARIS + bridge (same as ./start_polaris.sh)
  --               pass the remaining arguments to the underlying script

Running both halves on separate machines? Use the two scripts directly:

  GPU box:     ./start_nla.sh
  Docker box:  ./start_polaris.sh
  tunnel:      ssh -L 8000:127.0.0.1:8000 -R 8090:127.0.0.1:8090 user@gpu-box

Per-machine configuration lives in .env (see .env.example).
EOF
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; echo "Try --help, or pass args after --" >&2; exit 1 ;;
    esac
done

if [[ -n "$ONLY" && "$ONLY" != "nla" && "$ONLY" != "polaris" ]]; then
    echo "--only takes 'nla' or 'polaris'" >&2; exit 1
fi

if [[ "$ONLY" == "nla" ]]; then
    exec "$ROOT/start_nla.sh" "${PASSTHRU[@]+"${PASSTHRU[@]}"}"
fi
if [[ "$ONLY" == "polaris" ]]; then
    exec "$ROOT/start_polaris.sh" "${PASSTHRU[@]+"${PASSTHRU[@]}"}"
fi

"$ROOT/start_nla.sh" || { echo "NLA failed to start; not starting POLARIS" >&2; exit 1; }
"$ROOT/start_polaris.sh"
