#!/usr/bin/env bash
# Submits run_comparison.sbatch with the account from csf/local.env.
#   ./submit_comparison.sh                 # full length (105 min per arm)
#   ./submit_comparison.sh --short         # 1800s sim, ~30 min, for pipeline checks
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENVF="$HERE/../../CONTROLLER/csf/local.env"
[ -f "$ENVF" ] || { echo "missing $ENVF" >&2; exit 1; }
# shellcheck disable=SC1091
source "$ENVF"
: "${CSF_ACCOUNT:?set CSF_ACCOUNT in CONTROLLER/csf/local.env}"

TIME=0-04
case "${1:-}" in
    --short) export SELAS_SIM_LIMIT=1800s; TIME=0-02 ;;
    "") ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
esac

mkdir -p "$HERE/logs"
sbatch -A "$CSF_ACCOUNT" -t "$TIME" "$HERE/run_comparison.sbatch"
