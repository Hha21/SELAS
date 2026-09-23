#!/bin/bash
# SWIM's own adaptation managers, run in its self-adaptive network (SWIM_SA).
#
# Why these and not our Python port: SWIM ships two networks. `swim`, which the
# LLM needs, is externally controlled over a socket and has no adaptation
# manager of its own. `swim_sa` has the built-in ReactiveAdaptationManager and
# ReactiveAdaptationManager2 and is what SWIM's published results were produced
# with. A baseline a reviewer can check against SWIM's own code is better than
# a port of it, and the port has already been wrong once (its dimmer step).
#
# swim_sa uses the ordinary event scheduler rather than the real-time socket
# one, so a full 6300 s run takes a few seconds on one core. That is what makes
# ten seeds per cell affordable.
#
# Each line of the run list is:
#     label  config  run-index  seed-set  initialServers  maxServers  levels
# Run index selects trace x boot delay (`swim -q runs`): 3 = WorldCup at 180 s,
# 8 = ClarkNet at 180 s.
#
#   ./run_builtin.sh runs.txt OUTDIR [JOBS]
set -uo pipefail

RUNS_FILE="${1:?run list}"
OUT="${2:?output directory}"
JOBS="${3:-${SLURM_CPUS_PER_TASK:-4}}"
REPO="${SELAS_REPO:-$HOME/SELAS}"
# ~/scratch, not ~/h200-scratch: the latter is not mounted on CPU nodes.
SIF="${SELAS_SIF:-$HOME/scratch/selas-images/swim.sif}"
BASE_INI="$REPO/SWIM/simulations/swim_sa/swim_sa.ini"
mkdir -p "$OUT"
cp "$RUNS_FILE" "$OUT/runs.txt"

run_one() {
    local label="$1" config="$2" run="$3" seed="$4" init="$5" max="$6" levels="$7"
    local res="$OUT/$label"
    mkdir -p "$res"
    sed -e "s/^\*\.initialServers *=.*/*.initialServers = $init/" \
        -e "s/^\*\.maxServers *=.*/*.maxServers = $max/" \
        -e "s/^\*\.numberOfBrownoutLevels *=.*/*.numberOfBrownoutLevels = $levels/" \
        "$BASE_INI" > "$res/swim_sa.ini"
    apptainer exec \
        --bind "$res":/out \
        --bind "$res/swim_sa.ini":/headless/seams-swim/swim/simulations/swim_sa/swim_sa.ini \
        "$SIF" bash -lc "
        cd /headless/seams-swim/swim/simulations/swim_sa
        export PATH=/opt/omnetpp-5.4.1/bin:\$PATH
        export LD_LIBRARY_PATH=/opt/omnetpp-5.4.1/lib:\$LD_LIBRARY_PATH
        ../../src/swim swim_sa.ini -u Cmdenv -c $config -r $run --seed-set=$seed \
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
while read -r label config run seed init max levels; do
    [ -z "${label:-}" ] || [ "${label:0:1}" = "#" ] && continue
    while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do wait -n || failed=$((failed+1)); done
    run_one "$label" "$config" "$run" "$seed" "$init" "$max" "$levels" &
done < "$RUNS_FILE"
while [ "$(jobs -rp | wc -l)" -gt 0 ]; do wait -n || failed=$((failed+1)); done

dirs=(); for d in "$OUT"/*/; do dirs+=("${d%/}"); done
cd "$REPO/experiments/controller_comparison"
python3 collect.py "${dirs[@]}" -o "$OUT/results.json" > "$OUT/collect.log" 2>&1 \
    || { echo "collect.py failed"; tail -5 "$OUT/collect.log"; exit 1; }
python3 "$REPO/experiments/builtin_baselines/summarise.py" "$OUT/results.json"

[ "$failed" -eq 0 ] || { echo "$failed runs failed" >&2; exit 1; }
