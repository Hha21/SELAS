#!/bin/bash --login
#SBATCH -p multicore
#SBATCH -n 1
#SBATCH -c 2
#SBATCH -t 0-03
#SBATCH -J selas-baseline
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# One SWIM instance driven by a policy that needs no model: `null` (never acts)
# or `reactive` (SWIM's own rule). Deliberately a CPU job -- neither arm touches
# an LLM, so queueing them behind the H200s wastes days for nothing, and the
# GPU partitions are the scarce resource.
#
# swim.sif is read from ~/scratch rather than ~/h200-scratch: the latter is
# mounted only on H200 and login nodes, so a CPU node cannot see it.
#
#   SELAS_POLICY=null sbatch experiments/controller_comparison/run_baseline.sbatch

set -uo pipefail

: "${SLURM_JOB_ID:=$$}"
: "${SLURM_CPUS_PER_TASK:=2}"

REPO="${SELAS_REPO:-$HOME/h200-scratch/SELAS}"
SIF="${SELAS_SIF:-$HOME/scratch/selas-images/swim.sif}"
POLICY="${SELAS_POLICY:-null}"
RUN_INDEX="${SELAS_RUN_INDEX:-6}"
SEED_SET="${SELAS_SEED_SET:-1}"
SIM_LIMIT="${SELAS_SIM_LIMIT:-}"
PERIOD="${SELAS_PERIOD:-60}"
PORT="${SELAS_PORT:-$(( 4300 + SLURM_JOB_ID % 200 ))}"
RUN_ID="${SELAS_RUN_ID:-baseline-$POLICY-$(date -u +%Y%m%d-%H%M%S)}"
OUT="${SELAS_RESULTS:-$HOME/selas-results}/$RUN_ID"

source "$HOME/selas-env.sh"
mkdir -p "$OUT/$POLICY"

echo "run    $RUN_ID"
echo "node   $(hostname)  policy=$POLICY  port=$PORT"
echo "swim   run $RUN_INDEX, seed-set $SEED_SET${SIM_LIMIT:+, limit $SIM_LIMIT}"
echo "out    $OUT"

collect_results() {
    [ -n "${COLLECTED:-}" ] && return 0
    COLLECTED=1
    echo "=== collecting ==="
    cd "$REPO/experiments/controller_comparison" || return 1
    python collect.py "$OUT/$POLICY" -o "$OUT/runs.json" 2>&1 | tee "$OUT/collect.txt" \
        || echo "collect.py failed"
}
cleanup() {
    [ -n "${SWIM_PID:-}" ] && kill "$SWIM_PID" 2>/dev/null
    [ -n "${CTL_PID:-}" ]  && kill "$CTL_PID"  2>/dev/null
    collect_results
}
trap cleanup EXIT

apptainer exec --bind "$OUT/$POLICY":/headless/seams-swim/results "$SIF" bash -lc "
    cd /headless/seams-swim/swim/simulations/swim
    export PATH=/opt/omnetpp-5.4.1/bin:\$PATH
    export LD_LIBRARY_PATH=/opt/omnetpp-5.4.1/lib:\$LD_LIBRARY_PATH
    ../../src/swim swim.ini -u Cmdenv -c sim -r $RUN_INDEX --seed-set=$SEED_SET \
        --socketrtscheduler-port=$PORT ${SIM_LIMIT:+--sim-time-limit=$SIM_LIMIT} \
        -n ..:../../src:../../../queueinglib -l ../../../queueinglib/libqueueinglib.so
" > "$OUT/$POLICY/swim.log" 2>&1 &
SWIM_PID=$!

for _ in $(seq 1 30); do
    (exec 3<>/dev/tcp/127.0.0.1/$PORT) 2>/dev/null && break
    sleep 1
done

cd "$REPO/CONTROLLER"
python run_controller.py --port "$PORT" --period "$PERIOD" --policy "$POLICY" \
    --run-dir "$OUT/$POLICY" --run-id ctl > "$OUT/$POLICY/controller.log" 2>&1 &
CTL_PID=$!

echo "waiting for the simulation..."
wait $SWIM_PID
sleep 15
kill "$CTL_PID" 2>/dev/null
sleep 3
collect_results
echo "done -> $OUT"
