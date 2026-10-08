#!/bin/bash
# Run SWIM's PLA-SDP manager (and Thallium-trimmed variants) in SWIM_SA, locally,
# in the selas-swim-pla:dev image (see Dockerfile and README.md).
#
#   ./run_planners.sh runs.txt OUTDIR [JOBS]
#
# Each line of the run list is
#     label  config  seed-set  relation
# config    a [Config] of clayness/swim's swim_sa.ini: `pladapt` or `thallium`
#           (the same ProactiveAdaptationManager; the name only labels output).
# relation  the reachability relation the manager loads from /headless/yaml:
#           `image:pladapt` for the one generated in the image at build time,
#           or a host directory holding rubis.yaml and rubis-step.yaml
#           (absolute, or relative to the repository root).
#
# The ini is clayness/swim's as committed: ClarkNet, 180 s boot delay, servers
# 3 of 12, 10 dimmer levels, 60 s period, 6300 s with a 900 s warm-up -- the
# same configuration as SWIM's run 8 that our other baselines use. Its only run
# (-r 0) is that trace and boot delay, so the seed is set with --seed-set.
#
# Every run records the relation it used (OUTDIR/<label>/yaml/) and SWIM's log.
# SWIM_SA uses the ordinary event scheduler, so a run takes seconds. JOBS is
# capped at 2. Containers are named pla-<label>-<pid>; nothing else is touched.
set -uo pipefail

RUNS_FILE="${1:?run list}"
OUT="${2:?output directory}"
JOBS="${3:-2}"; [ "$JOBS" -gt 2 ] && JOBS=2
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
IMAGE="${SELAS_PLA_IMAGE:-selas-swim-pla:dev}"
PY="${SELAS_PYTHON:-$REPO/POLARIS/.venv/bin/python}"
# Default (true) is what the shipped runs used: a tactic takes effect after the
# measured wall-clock time of the decision. false applies it at once, which
# makes a run independent of machine speed (see README, "Determinism").
DECISION_DELAY="${SELAS_PLA_DECISION_DELAY:-true}"

mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
cp "$RUNS_FILE" "$OUT/runs.txt"
docker image inspect "$IMAGE" --format '{{.Id}}' > "$OUT/image-id.txt"

# The image's own relation, once, so runs can mount it like any other.
mkdir -p "$OUT/relations/pladapt"
docker run --rm --name "pla-extract-$$" --network none --user "$(id -u):$(id -g)" \
    -v "$OUT/relations/pladapt":/x --entrypoint bash "$IMAGE" \
    -lc 'cp /headless/pla/yaml/pladapt/rubis.yaml /headless/pla/yaml/pladapt/rubis-step.yaml /x/ &&
         cat /headless/pla/swim/simulations/swim_sa/swim_sa.ini' > "$OUT/swim_sa.ini"

run_one() {
    local label="$1" config="$2" seed="$3" relation="$4"
    local res="$OUT/$label"
    mkdir -p "$res/yaml"
    case "$relation" in
        image:pladapt) relation="$OUT/relations/pladapt" ;;
        /*) ;;
        *) relation="$REPO/$relation" ;;        # relative paths are from the repo root
    esac
    cp "$relation/rubis.yaml" "$relation/rubis-step.yaml" "$res/yaml/" \
        || { echo "FAILED $label (no relation in $relation)"; return 1; }
    # OMNeT++ 5.4 takes no parameter assignments on the command line, so the
    # non-default setting goes into a copy of the ini, mounted over the original
    # (it must stay in the simulation directory, or SWIM_SA's package is lost).
    # The default uses the ini as committed.
    local mount_ini=()
    if [ "$DECISION_DELAY" != true ]; then
        sed "/^\[General\]/a **.adaptationManager.simulateDecisionDelay = $DECISION_DELAY" \
            "$OUT/swim_sa.ini" > "$res/swim_sa.ini"
        mount_ini=(-v "$res/swim_sa.ini":/headless/pla/swim/simulations/swim_sa/swim_sa.ini:ro)
    fi
    docker run --rm --name "pla-$label-$$" --network none --user "$(id -u):$(id -g)" \
        -v "$res":/out -v "$res/yaml":/headless/yaml:ro "${mount_ini[@]}" \
        --entrypoint bash "$IMAGE" -lc "
        cd /headless/pla/swim/simulations/swim_sa
        ../../src/swim swim_sa.ini -u Cmdenv -c $config -r 0 --seed-set=$seed \
            --result-dir=/out --cmdenv-express-mode=true \
            -n ..:../../src:../../../queueinglib -l ../../../queueinglib/libqueueinglib.so
    " > "$res/swim.log" 2>&1
    local rc=$?
    if [ $rc -ne 0 ] || ! ls "$res"/*.sca >/dev/null 2>&1; then
        echo "FAILED $label (exit $rc)"; tail -3 "$res/swim.log"; return 1
    fi
    echo "ok     $label"
}

failed=0
while read -r label config seed relation; do
    [ -z "${label:-}" ] || [ "${label:0:1}" = "#" ] && continue
    while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do wait -n || failed=$((failed+1)); done
    run_one "$label" "$config" "$seed" "$relation" &
done < "$RUNS_FILE"
while [ "$(jobs -rp | wc -l)" -gt 0 ]; do wait -n || failed=$((failed+1)); done

dirs=(); for d in "$OUT"/*/; do [ -n "$(ls "$d"*.sca 2>/dev/null)" ] && dirs+=("${d%/}"); done
"$PY" "$REPO/experiments/controller_comparison/collect.py" "${dirs[@]}" -o "$OUT/results.json" \
    > "$OUT/collect.log" 2>&1 || { echo "collect.py failed"; tail -5 "$OUT/collect.log"; exit 1; }
"$PY" "$HERE/summarise_planners.py" "$OUT/results.json" | tee "$OUT/summary.txt"

[ "$failed" -eq 0 ] || { echo "$failed runs failed" >&2; exit 1; }
