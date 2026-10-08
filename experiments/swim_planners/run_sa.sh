#!/bin/bash
# Run SWIM_SA managers -- PLA-SDP (either planning utility), SWIM's reactive
# managers, fixed configurations -- in selas-swim-pla:dev, on either trace.
#
#   ./run_sa.sh RUNS_FILE OUTDIR [JOBS]
#
# Each line of the run list is
#     label  config  run-index  seed-set  [key=value ...]
# config     a [Config] of swim_sa_planners.ini: Reactive, Reactive2, pladapt,
#            pladapt_seams2017a, pladapt_seams2017a_stevensrt, Static
# run-index  SWIM's run numbering: 3 = WorldCup at 180 s, 8 = ClarkNet at 180 s
# key=value  ini settings added under [General] for this run, e.g.
#            **.adaptationManager.servers=4 **.adaptationManager.dimmer=1.0;
#            relation=DIR instead mounts that reachability relation (default:
#            the PLA relation generated in the image).
#
# The ini is mounted inside the simulation directory (OMNeT++ resolves the
# network's package from the ini's location). Each run writes .sca/.vec, SWIM's
# log and summary.json (summarise_sa.py: SEAMS 2017A via swim_utility.py, the
# function collect.py uses). With KEEP_VEC=0 the .vec is deleted once
# summarised -- for the fixed-configuration grid, whose vectors would not fit.
# JOBS defaults to 4 (the cap). Containers are named pla-<label>-<pid>.
set -uo pipefail

RUNS_FILE="${1:?run list}"
OUT="${2:?output directory}"
JOBS="${3:-4}"; [ "$JOBS" -gt 4 ] && JOBS=4
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
IMAGE="${SELAS_PLA_IMAGE:-selas-swim-pla:dev}"
PY="${SELAS_PYTHON:-$REPO/POLARIS/.venv/bin/python}"
KEEP_VEC="${KEEP_VEC:-1}"
SIMDIR=/headless/pla/swim/simulations/swim_sa

mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
cp "$RUNS_FILE" "$OUT/runs.txt"
cp "$HERE/swim_sa_planners.ini" "$OUT/swim_sa_planners.ini"
docker image inspect "$IMAGE" --format '{{.Id}}' > "$OUT/image-id.txt"
mkdir -p "$OUT/relations/pladapt"
docker run --rm --name "pla-extract-$$" --network none --user "$(id -u):$(id -g)" \
    -v "$OUT/relations/pladapt":/x --entrypoint bash "$IMAGE" \
    -lc 'cp /headless/pla/yaml/pladapt/rubis.yaml /headless/pla/yaml/pladapt/rubis-step.yaml /x/'

run_one() {
    local label="$1" config="$2" run="$3" seed="$4"; shift 4
    local res="$OUT/$label" relation="$OUT/relations/pladapt" extra=()
    for kv in "$@"; do
        case "$kv" in
            relation=/*) relation="${kv#relation=}" ;;
            relation=*) relation="$REPO/${kv#relation=}" ;;
            *=*) extra+=("${kv%%=*} = ${kv#*=}") ;;
            *) echo "FAILED $label (bad setting '$kv')"; return 1 ;;
        esac
    done
    mkdir -p "$res/yaml"
    cp "$relation/rubis.yaml" "$relation/rubis-step.yaml" "$res/yaml/" \
        || { echo "FAILED $label (no relation in $relation)"; return 1; }
    { sed -n '1,/^\[General\]/p' "$OUT/swim_sa_planners.ini"
      echo "# --- per-run settings (run_sa.sh) ---"
      for line in "${extra[@]}"; do echo "$line"; done
      sed '1,/^\[General\]/d' "$OUT/swim_sa_planners.ini"; } > "$res/run.ini"
    # A memory cap per run: a runaway simulation (2026-10-08: a static manager
    # looping on addServer reached ~5 GB per run and exhausted the laptop) is
    # killed in its own container instead. PLA_MEM overrides it; PLA_TIMEOUT
    # (seconds, default 900) bounds a run's wall time the same way.
    docker run --rm --name "pla-$label-$$" --network none --user "$(id -u):$(id -g)" \
        --memory "${PLA_MEM:-2g}" --memory-swap "${PLA_MEM:-2g}" \
        -v "$res":/out -v "$res/yaml":/headless/yaml:ro -v "$res/run.ini":$SIMDIR/run.ini:ro \
        --entrypoint bash "$IMAGE" -lc "
        cd $SIMDIR
        timeout ${PLA_TIMEOUT:-900} ../../src/swim run.ini -u Cmdenv -c $config -r $run --seed-set=$seed \
            --result-dir=/out --cmdenv-express-mode=true \
            -n ..:../../src:../../../queueinglib -l ../../../queueinglib/libqueueinglib.so
    " > "$res/swim.log" 2>&1
    local rc=$?
    if [ $rc -ne 0 ] || ! ls "$res"/*.sca >/dev/null 2>&1; then
        echo "FAILED $label (exit $rc)"; tail -3 "$res/swim.log"; return 1
    fi
    "$PY" "$HERE/summarise_sa.py" "$res" > "$res/summary.json" 2> "$res/summary.err" \
        || { echo "FAILED $label (summary)"; tail -3 "$res/summary.err"; return 1; }
    [ "$KEEP_VEC" = 1 ] || rm -f "$res"/*.vec
    echo "ok     $label"
}

failed=0
while read -r line; do
    read -r -a f <<< "$line"            # split without pathname expansion (keys contain **)
    [ "${#f[@]}" -eq 0 ] || [ "${f[0]:0:1}" = "#" ] && continue
    while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do wait -n || failed=$((failed+1)); done
    run_one "${f[@]}" &
done < "$RUNS_FILE"
while [ "$(jobs -rp | wc -l)" -gt 0 ]; do wait -n || failed=$((failed+1)); done

"$PY" "$HERE/table_sa.py" "$OUT" | tee "$OUT/table.txt"
[ "$failed" -eq 0 ] || { echo "$failed runs failed" >&2; exit 1; }
