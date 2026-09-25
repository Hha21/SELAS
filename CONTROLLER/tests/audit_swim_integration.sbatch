#!/bin/bash --login
#SBATCH -p multicore
#SBATCH -n 1
#SBATCH -c 8
#SBATCH -t 0-00:50
#SBATCH -J audit-swim
#SBATCH -o %x_%j.out
#SBATCH -e %x_%j.err
#
# Audit: drive real SWIM instances with scripted commands (see audit_swim_integration.py).
# Launch exactly as experiments/controller_comparison/run_baseline.sbatch does, except
# warmup-period = 0 so that events before 900 s are recorded in the vectors.
#
#   cd ~/scratch/audit && sbatch audit_swim_integration.sbatch
set -uo pipefail
: "${SLURM_JOB_ID:=$$}"
REPO="$HOME/SELAS"
SIF="$HOME/scratch/selas-images/swim.sif"
AUD="$HOME/scratch/audit"
OUT="$AUD/results-$SLURM_JOB_ID"
source "$HOME/selas-env.sh"
export PYTHONPATH="$REPO/CONTROLLER"
mkdir -p "$OUT"

launch() {   # name run init max levels limit port
    local name=$1 run=$2 init=$3 max=$4 levels=$5 limit=$6 port=$7
    local res="$OUT/$name"; mkdir -p "$res"
    sed -e "s/^\*\.initialServers *=.*/*.initialServers = $init/" \
        -e "s/^\*\.maxServers *=.*/*.maxServers = $max/" \
        -e "s/^\*\.numberOfBrownoutLevels *=.*/*.numberOfBrownoutLevels = $levels/" \
        -e "s/^warmup-period *=.*/warmup-period = 0s/" \
        "$REPO/SWIM/simulations/swim/swim.ini" > "$res/swim.ini"
    apptainer exec --bind "$res":/headless/seams-swim/results \
        --bind "$res/swim.ini":/headless/seams-swim/swim/simulations/swim/swim.ini "$SIF" bash -lc "
        cd /headless/seams-swim/swim/simulations/swim
        export PATH=/opt/omnetpp-5.4.1/bin:\$PATH
        export LD_LIBRARY_PATH=/opt/omnetpp-5.4.1/lib:\$LD_LIBRARY_PATH
        ../../src/swim swim.ini -u Cmdenv -c sim -r $run --seed-set=1 \
            --socketrtscheduler-port=$port --sim-time-limit=$limit \
            -n ..:../../src:../../../queueinglib -l ../../../queueinglib/libqueueinglib.so
    " > "$res/swim.log" 2>&1 &
    echo $! > "$res/swim.pid"
    for _ in $(seq 1 30); do
        (exec 3<>/dev/tcp/127.0.0.1/$port) 2>/dev/null && break
        sleep 1
    done
}

BASE=$(( 5000 + SLURM_JOB_ID % 500 * 10 ))

# which run index is which (trace x bootDelay)
apptainer exec --bind "$REPO/SWIM/simulations/swim/swim.ini":/headless/seams-swim/swim/simulations/swim/swim.ini "$SIF" bash -lc "
    cd /headless/seams-swim/swim/simulations/swim
    export PATH=/opt/omnetpp-5.4.1/bin:\$PATH LD_LIBRARY_PATH=/opt/omnetpp-5.4.1/lib:\$LD_LIBRARY_PATH
    ../../src/swim swim.ini -u Cmdenv -c sim -q runs -n ..:../../src:../../../queueinglib -l ../../../queueinglib/libqueueinglib.so" \
    > "$OUT/runs.txt" 2>&1

# A: published configuration, scripted policy through the production path
launch A 8 3 12 10 1500s $BASE
python "$AUD/audit_swim_integration.py" drive-a --port $BASE --out "$OUT/A" --periods 25 \
    > "$OUT/A/driver.log" 2>&1 &
A_DRV=$!

# B: raw illegal commands, one fresh simulator each (they may corrupt or kill it)
i=1
for spec in "add_while_booting 6 2 4 150s" "add_at_max 5 3 3 60s" \
            "remove_last 5 1 3 60s" "dimmer_values 5 3 3 60s"; do
    set -- $spec
    port=$(( BASE + i )); i=$(( i + 1 ))
    launch "B_$1" $2 $3 $4 5 $5 $port
    python "$AUD/audit_swim_integration.py" drive-b --case $1 --port $port --out "$OUT/B_$1" \
        > "$OUT/B_$1/driver.log" 2>&1
    wait "$(cat "$OUT/B_$1/swim.pid")" 2>/dev/null
    echo "B_$1 swim exit: $?" >> "$OUT/B_exit.txt"
    tail -5 "$OUT/B_$1/swim.log" >> "$OUT/B_exit.txt"
done

wait "$(cat "$OUT/A/swim.pid")"
echo "A swim exit: $?" > "$OUT/A_exit.txt"
sleep 5; kill $A_DRV 2>/dev/null
python "$AUD/audit_swim_integration.py" check --results "$OUT/A" > "$OUT/A_check.json" 2>&1
echo "check exit: $?" >> "$OUT/A_exit.txt"
echo done
