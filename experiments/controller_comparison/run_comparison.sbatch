#!/bin/bash --login
#SBATCH -p gpuH_short
#SBATCH -G 2
#SBATCH -n 1
#SBATCH -c 16
#SBATCH -t 0-04
#SBATCH -J selas-compare
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err
#
# One vLLM server, two SWIM instances, two controllers -- the reactive rule and
# the LLM -- driven concurrently over the same wall clock.
#
# Submit with experiments/controller_comparison/submit_comparison.sh, which
# supplies -A from the gitignored csf/local.env.
#
# Concurrency is possible because the external-control port is configurable:
# queueinglib/SocketRTScheduler.cc registers `socketrtscheduler-port` (default
# 4242), so each instance gets its own. Running the arms together rather than
# back to back costs one GPU allocation instead of two and puts both under the
# same machine load, which matters when the scheduler is real-time.
#
# Ordering is not arbitrary. cSocketRTScheduler::setupListener() binds and
# listens but never blocks on accept, so a simulation starts advancing the
# moment it launches whether or not anything is controlling it. The model is
# therefore brought up and proved FIRST; SWIM is started last, and its
# controller within a second of it.

set -uo pipefail

# $HOME/SELAS, which every node mounts -- h200-scratch is invisible to CPU nodes
REPO="${SELAS_REPO:-$HOME/SELAS}"
SIF="${SELAS_SIF:-$HOME/h200-scratch/images/swim.sif}"
MODEL="${SELAS_MODEL:-meta-llama/Llama-3.3-70B-Instruct}"
SERVED=csf-llm
RUN_INDEX="${SELAS_RUN_INDEX:-6}"
SEED_SET="${SELAS_SEED_SET:-1}"
SIM_LIMIT="${SELAS_SIM_LIMIT:-}"          # e.g. 1800s for a short pipeline test
PERIOD="${SELAS_PERIOD:-60}"
RUN_ID="${SELAS_RUN_ID:-cmp-$(date -u +%Y%m%d-%H%M%S)}"

# Results go to HOME, not h200-scratch, and not inside the repo clone.
#
# h200-scratch is the right home for weights and the container image: large,
# fast, next to the GPUs, and everything on it can be re-downloaded. It is the
# wrong home for results, because it has no backup, no recycle bin and no
# recovery -- and a run's output is the one artefact here that cannot be
# regenerated without another 105 minutes of wall clock and a GPU allocation.
#
# Writing them inside the repo clone is separately untidy: they are not
# gitignored, so every `git status` on CSF shows them, and a `git pull` has to
# step around them.
OUT="${SELAS_RESULTS:-$HOME/selas-results}/$RUN_ID"

# Slurm sets these for a batch job but not inside an `srun` step, and `set -u`
# turns that into an instant death on line 47 rather than a degraded run. The
# defaults exist so the script can be exercised interactively under
# `srun --jobid=...`, which is the cheapest way to debug it -- a batch job costs
# a queue wait to learn the same thing.
: "${SLURM_JOB_ID:=$$}"
: "${SLURM_CPUS_PER_TASK:=8}"
: "${SLURM_GPUS:=1}"
: "${CUDA_VISIBLE_DEVICES:=unset}"

# initialServers: swim.ini ships initialServers = maxServers = 3, so the run
# starts at the ceiling and every available move is downward. On that
# configuration doing nothing scored 5431 against the reactive rule's 2417 and
# gemma's 4959 -- the optimal policy was inaction, which makes it a poor test of
# adaptation. Starting at 1 forces scaling up to be necessary.
INITIAL_SERVERS="${SELAS_INITIAL_SERVERS:-1}"
MAX_SERVERS="${SELAS_MAX_SERVERS:-3}"
# bootDelay is chosen by RUN_INDEX (it is a sweep variable), but the controller
# has to be told separately because SWIM does not expose it over the socket.
# The two must agree, and the run is aborted below if they do not.
BOOT_DELAY="${SELAS_BOOT_DELAY:-60}"
BROWNOUT_LEVELS="${SELAS_BROWNOUT_LEVELS:-5}"
PROMPT_FORMAT="${SELAS_PROMPT_FORMAT:-chat}"

VLLM_PORT=$(( 20000 + SLURM_JOB_ID % 20000 ))
# null costs nothing and is the control that says whether acting helped at all.
ARMS="${SELAS_ARMS:-reactive null llm}"

# What each arm *is*, as controller flags. Everything the prompting sweep varies
# lives here rather than in a second copy of this script: the arms share one
# vLLM, one node, one wall clock and one simulator build, and running them from
# separate scripts would let those drift apart silently -- which is exactly the
# confound a comparison across prompting configurations cannot afford.
#
# The LLM arms differ in one dimension each, against `llm` as the reference:
#
#   llm       the scaffolded fields, 200 tokens, both exemplars
#   free      "think step by step" instead of named fields -- tests whether the
#             scaffold is what makes the conclusion carry the decision
#   short     the same scaffold on a 60-token budget -- tests whether reasoning
#             length buys anything beyond latency
#   zeroshot  no exemplars -- tests how much of the reasoning is the model and
#             how much is our two hand-written examples
#   none      no reasoning at all. Not a point on the interpretability axes,
#             which need an explanation to exist; it is the reference line for
#             what utility costs when nothing is explained.
declare -A ARM_SPEC=(
    [reactive]="--policy reactive"
    [null]="--policy null"
    [llm]="--policy llm --reasoning scaffold --max-reasoning-tokens 200"
    [free]="--policy llm --reasoning free --max-reasoning-tokens 200"
    [short]="--policy llm --reasoning scaffold --max-reasoning-tokens 60"
    [zeroshot]="--policy llm --reasoning scaffold --max-reasoning-tokens 200 --exemplars 0"
    [none]="--policy llm --reasoning none"
    # Config B: the utility function itself, and each period's utility shown.
    # `llm` is config A: the same prompt with the priority order in words.
    [formula]="--policy llm --reasoning scaffold --max-reasoning-tokens 200 --objective formula --utility-feedback"
    # The prompt built up one component at a time (PLAN.md step 3), all on the
    # scaffold with 200 tokens. The name lists what is added to the base
    # (constraints, legend, state, field names):
    #   k2        the two worked exemplars
    #   words     the objective as a priority order in words (config A's)
    #   formula   the objective as SWIM's utility function, with its constants
    #   fb        each period's utility shown in the state and its history
    # k2-words is config A and k2-formula-fb config B, on the fixed prompt.
    [k0]="--policy llm --reasoning scaffold --max-reasoning-tokens 200 --exemplars 0 --objective none"
    [k2]="--policy llm --reasoning scaffold --max-reasoning-tokens 200 --exemplars 2 --objective none"
    [k2-words]="--policy llm --reasoning scaffold --max-reasoning-tokens 200 --exemplars 2 --objective priority"
    [k2-formula]="--policy llm --reasoning scaffold --max-reasoning-tokens 200 --exemplars 2 --objective formula"
    [k2-words-fb]="--policy llm --reasoning scaffold --max-reasoning-tokens 200 --exemplars 2 --objective priority --utility-feedback"
    [k2-formula-fb]="--policy llm --reasoning scaffold --max-reasoning-tokens 200 --exemplars 2 --objective formula --utility-feedback"
)

# Ports are handed out in order rather than fixed per arm, so adding an arm does
# not mean remembering to add a port and finding out it collided at runtime.
#
# The base comes from the job id, as the vLLM port does. A fixed base (4242) let
# two jobs on one node claim the same ports (2026-09-26, jobs 21384049/50): the
# second SWIM on each port crashed at start-up, and its controller found the
# port open -- served by the *other* job's simulation -- and drove that one.
# 10000-18990 stays clear of the vLLM range (20000-39999) and of the kernel's
# ephemeral ports (32768+).
PORT_BASE="${SELAS_PORT_BASE:-$(( 10000 + SLURM_JOB_ID % 900 * 10 ))}"

# Empty means "do not pass the flag", which leaves run_controller.py's own
# default (0.7) in charge and keeps this script's behaviour unchanged. The
# sweep sets it to 0: with one run per arm, sampling noise would sit on exactly
# the differences between arms that the comparison is built on.
TEMPERATURE="${SELAS_TEMPERATURE:-}"

source "$HOME/selas-env.sh"
export HF_HOME="${HF_HOME:-$HOME/h200-scratch/hf}"

# initialServers cannot be set on the OMNeT++ command line: --<option>=<value>
# takes *configuration options* (which is why --sim-time-limit works) and not
# NED parameter assignments, so `--*.initialServers=1` is rejected outright with
# "Unknown command-line configuration option" and the simulation never starts.
# Instead, edit a copy of the ini and bind-mount it over the container's own --
# the container is read-only, and this keeps the change visible in the run
# directory rather than hidden in the image.
SWIM_INI="$OUT/swim.ini"
mkdir -p "$OUT"
sed -e "s/^\*\.initialServers *=.*/*.initialServers = $INITIAL_SERVERS/" \
    -e "s/^\*\.maxServers *=.*/*.maxServers = $MAX_SERVERS/" \
    -e "s/^\*\.numberOfBrownoutLevels *=.*/*.numberOfBrownoutLevels = $BROWNOUT_LEVELS/" \
    "$REPO/SWIM/simulations/swim/swim.ini" > "$SWIM_INI"
grep -E "^\*\.(initialServers|maxServers|numberOfBrownoutLevels)" "$SWIM_INI" \
    | sed "s/^/  ini: /"
# bootDelay is a sweep variable, not a plain assignment, so it is selected by
# run index rather than edited. `swim -q runs` lists the mapping; index 8 is
# ClarkNet at latency 180, which is the published configuration.
grep -E "^\*\.bootDelay" "$SWIM_INI" | sed "s/^/  ini: /"
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
mkdir -p "$OUT"

echo "run       $RUN_ID"
echo "node      $(hostname)   gpus=$CUDA_VISIBLE_DEVICES   cores=$SLURM_CPUS_PER_TASK"
echo "model     $MODEL  (vllm :$VLLM_PORT)"
echo "swim      run $RUN_INDEX, seed-set $SEED_SET, servers $INITIAL_SERVERS/$MAX_SERVERS, boot ${BOOT_DELAY}s${SIM_LIMIT:+, sim-time-limit $SIM_LIMIT}"
echo "arms      $ARMS   (llm arms in $PROMPT_FORMAT format${TEMPERATURE:+, temperature $TEMPERATURE})"
for t in $ARMS; do printf '            %-12s %s\n' "$t" "${ARM_SPEC[${t%@*}]:-UNKNOWN}"; done
echo "out       $OUT"

# Collection runs from the EXIT trap, not only inline. The dry run reached the
# end of the simulations, wrote 20 decisions and four .sca/.vec files, and then
# exited before the collection block -- leaving a complete run with no tidy
# output and no plot, recoverable only by hand. Whatever caused that (the
# controllers are killed just above it), the results are too expensive to lose
# to it: 105 minutes of wall clock and a GPU allocation. Running collection from
# the trap means it happens on every exit path, and the guard makes it
# idempotent when the inline call already succeeded.
collect_results() {
    [ -n "${COLLECTED:-}" ] && return 0
    COLLECTED=1
    echo "=== collecting results ==="
    cd "$REPO/experiments/controller_comparison" || { echo "cannot cd to collect"; return 1; }
    local dirs=(); for t in $ARMS; do dirs+=("$OUT/${t/@/-s}"); done
    python collect.py "${dirs[@]}" -o "$OUT/runs.json" 2>&1 | tee "$OUT/collect.txt" \
        || echo "collect.py failed"
    local labels=(); for t in $ARMS; do labels+=("${t/@/-s}"); done
    # The seeds the arms actually ran on: "arm@N" overrides SEED_SET, so the
    # job default alone mislabelled a run of k0@0 ... as seed-set 1.
    local seeds
    seeds=$(for t in $ARMS; do case "$t" in *@*) echo "${t##*@}" ;; *) echo "$SEED_SET" ;; esac; done \
            | sort -un | paste -sd, -)
    python plot.py "$OUT/runs.json" -o "$OUT/comparison" --labels "${labels[@]}" \
        --title "SWIM run $RUN_INDEX, seed-set $seeds, $MODEL" 2>&1 \
        || echo "plot.py failed"
    ls -la "$OUT" 2>/dev/null

    # A run that produced nothing must not look like a run that succeeded.
    # The first three-arm attempt exited 0 after 3 minutes with no .sca, no
    # decisions and a tidy set of empty directories, because every simulation
    # had died on a rejected command-line option -- and nothing in the job
    # noticed. Slurm reported COMPLETED. Checked per arm: when two jobs shared
    # ports, half the arms lost their simulation and half their decisions, and
    # a check across the whole job still passed.
    local bad=0 t d n_vec n_dec
    for t in $ARMS; do
        d="$OUT/${t/@/-s}"
        n_vec=$(find "$d" -name "*.vec" -size +0 2>/dev/null | wc -l)
        n_dec=$(cat "$d"/*/decisions.jsonl 2>/dev/null | wc -l)
        if [ "$n_vec" -eq 0 ] || [ "$n_dec" -eq 0 ]; then
            echo "FAILED: ${t/@/-s} has $n_vec .vec files and $n_dec decisions" >&2
            tail -4 "$d/swim.log" 2>/dev/null | sed "s/^/        /" >&2
            bad=1
        fi
    done
    [ "$bad" = 1 ] && COLLECT_FAILED=1

    # Every run is checked against SWIM's own record: each command sent must be
    # exactly one recorded change of the right value, no change may lack a
    # command, and what the controller observed must match SWIM's state. This
    # is what exposes a controller driving the wrong simulation.
    echo "=== integration check ==="
    for t in $ARMS; do
        d="$OUT/${t/@/-s}"
        [ -n "$(find "$d" -name "*.vec" -size +0 2>/dev/null)" ] || continue
        python "$REPO/CONTROLLER/tests/audit_swim_integration.py" check --results "$d" \
            --unscripted --brief > "$d/integration_check.json" 2>&1
        python - "$d/integration_check.json" "${t/@/-s}" <<'PY' || bad=1
import json, sys
txt = open(sys.argv[1]).read()
try:
    rep = json.loads(txt[txt.index("{"):])
except ValueError:
    print(f"  {sys.argv[2]:18s} check did not run:", txt.strip().splitlines()[-1:]); sys.exit(1)
print(f"  {sys.argv[2]:18s} {len(rep['problems'])} problems, {len(rep['notes'])} notes")
for x in rep["problems"][:5]:
    print("      ", x[:160])
sys.exit(1 if rep["problems"] else 0)
PY
    done
    [ "$bad" = 1 ] && COLLECT_FAILED=1
}

cleanup() {
    echo "cleaning up"
    [ -n "${VLLM_PID:-}" ] && kill "$VLLM_PID" 2>/dev/null
    for pid in ${SWIM_PIDS:-} ${CTL_PIDS:-}; do kill "$pid" 2>/dev/null; done
    collect_results
}
trap cleanup EXIT

# ----------------------------------------------------------------- 1. the model
echo "starting vLLM..."
python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" --served-model-name "$SERVED" \
    --tensor-parallel-size "$SLURM_GPUS" \
    --host 127.0.0.1 --port "$VLLM_PORT" \
    --max-model-len 8192 --max-logprobs 30 --dtype auto \
    > "$OUT/vllm.log" 2>&1 &
VLLM_PID=$!

for _ in $(seq 1 180); do
    curl -sf "http://127.0.0.1:$VLLM_PORT/health" >/dev/null 2>&1 && break
    kill -0 "$VLLM_PID" 2>/dev/null || { echo "vLLM died during startup:"; tail -30 "$OUT/vllm.log"; exit 1; }
    sleep 10
done
curl -sf "http://127.0.0.1:$VLLM_PORT/health" >/dev/null 2>&1 || {
    echo "vLLM never became healthy"; tail -30 "$OUT/vllm.log"; exit 1; }
echo "vLLM healthy"

# Prove it can actually score before any simulated time is spent.
cd "$REPO/CONTROLLER"
python run_controller.py --check-backend --backend openai \
    --prompt-format "$PROMPT_FORMAT" \
    --llm-base-url "http://127.0.0.1:$VLLM_PORT/v1" --llm-model "$SERVED" \
    | tee "$OUT/check_backend.txt"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "backend check failed; not starting SWIM"; exit 1; }

# ------------------------------------------------------- 2. simulations + arms
SWIM_PIDS=""
CTL_PIDS=""
arm_index=0
for token in $ARMS; do
    # "llm@2" is the llm arm on seed-set 2. Repeats therefore cost slots in one
    # allocation rather than a whole extra job: six concurrent simulations is
    # proven, so three arms at two seeds is the same 105 minutes as six arms at
    # one, and it is the only way to see run-to-run spread without paying twice.
    arm="${token%@*}"
    seed="$SEED_SET"
    case "$token" in *@*) seed="${token##*@}" ;; esac
    label="${token/@/-s}"
    if [ -z "${ARM_SPEC[$arm]:-}" ]; then
        echo "unknown arm '$arm' (from '$token'); known: ${!ARM_SPEC[*]}" >&2; exit 1
    fi
    port=$(( PORT_BASE + arm_index )); arm_index=$(( arm_index + 1 ))
    res="$OUT/$label"; mkdir -p "$res"

    # Something already answering here would be taken for this arm's SWIM.
    if (exec 3<>/dev/tcp/127.0.0.1/$port) 2>/dev/null; then
        echo "port $port is already in use on $(hostname); refusing to start '$label'" >&2
        exit 1
    fi

    echo "starting SWIM for '$label' (seed-set $seed) on :$port"
    apptainer exec \
        --bind "$res":/headless/seams-swim/results \
        --bind "$SWIM_INI":/headless/seams-swim/swim/simulations/swim/swim.ini \
        "$SIF" bash -lc "
        cd /headless/seams-swim/swim/simulations/swim
        export PATH=/opt/omnetpp-5.4.1/bin:\$PATH
        export LD_LIBRARY_PATH=/opt/omnetpp-5.4.1/lib:\$LD_LIBRARY_PATH
        ../../src/swim swim.ini -u Cmdenv -c sim -r $RUN_INDEX --seed-set=$seed \
            --socketrtscheduler-port=$port ${SIM_LIMIT:+--sim-time-limit=$SIM_LIMIT} \
            -n ..:../../src:../../../queueinglib -l ../../../queueinglib/libqueueinglib.so
    " > "$res/swim.log" 2>&1 &
    swim_pid=$!
    SWIM_PIDS="$SWIM_PIDS $swim_pid"

    # The clock is already running, so the controller follows immediately --
    # but only once this arm's own SWIM is listening. The port being open is
    # not enough on its own: it must be open with our process still alive.
    up=0
    for _ in $(seq 1 30); do
        (exec 3<>/dev/tcp/127.0.0.1/$port) 2>/dev/null && { up=1; break; }
        sleep 1
    done
    if [ "$up" != 1 ] || ! kill -0 "$swim_pid" 2>/dev/null; then
        echo "SWIM for '$label' is not listening on :$port (see $res/swim.log)" >&2
        tail -5 "$res/swim.log" >&2
        exit 1
    fi

    read -r -a extra <<< "${ARM_SPEC[$arm]}"
    case "${ARM_SPEC[$arm]}" in
        *"--policy llm"*)
            extra+=(--backend openai --prompt-format "$PROMPT_FORMAT"
                    --llm-base-url "http://127.0.0.1:$VLLM_PORT/v1"
                    --llm-model "$SERVED")
            [ -n "$TEMPERATURE" ] && extra+=(--temperature "$TEMPERATURE")
            ;;
    esac
    python run_controller.py --port "$port" --period "$PERIOD" \
        --boot-delay "$BOOT_DELAY" --dimmer-levels "$BROWNOUT_LEVELS" \
        --run-dir "$res" --run-id "$label" "${extra[@]}" \
        > "$res/controller.log" 2>&1 &
    CTL_PIDS="$CTL_PIDS $!"
    echo "  controller '$label' started (pid $!)"
done

# Verify the boot delay we told the model matches the one the simulation is
# using. SWIM records it as a scalar, so a mismatch is detectable rather than
# something that quietly makes the prompt wrong for 105 minutes. Checked once a
# .sca exists -- after the run, since that is when it is written.
check_boot_delay() {
    local sca
    sca=$(find "$OUT" -name "*.sca" -size +0 2>/dev/null | head -1)
    [ -n "$sca" ] || return 0
    python - "$sca" "$BOOT_DELAY" <<'PY'
import sqlite3, sys
sca, told = sys.argv[1], float(sys.argv[2])
try:
    c = sqlite3.connect(f"file:{sca}?mode=ro", uri=True)
    row = c.execute("SELECT scalarValue FROM scalar WHERE scalarName "
                    "LIKE '%bootDelay%' LIMIT 1").fetchone()
    c.close()
except Exception as exc:
    print(f"  (could not read bootDelay from {sca}: {exc})"); sys.exit(0)
if row is None:
    print("  (bootDelay not recorded; skipping the check)"); sys.exit(0)
actual = float(row[0])
if abs(actual - told) > 1e-6:
    print(f"WARNING: the prompt told the model servers boot in {told:.0f} s, "
          f"but the simulation used {actual:.0f} s. Every decision was taken "
          f"against a false constraint; set SELAS_BOOT_DELAY to match "
          f"SELAS_RUN_INDEX.")
else:
    print(f"  bootDelay check: prompt and simulation agree at {actual:.0f} s")
PY
}

echo "waiting for all simulations to finish..."
wait $SWIM_PIDS
echo "simulations done; giving controllers a moment to flush"
sleep 15
# By recorded pid, not pkill -f: that pattern also matches any enclosing shell
# whose command line contains it, which kills the job rather than the child.
for pid in $CTL_PIDS; do kill "$pid" 2>/dev/null; done
sleep 3

# --------------------------------------------------------------- 3. collection
echo "reached the collection step"
check_boot_delay
collect_results

cat > "$OUT/manifest.json" <<JSON
{"run_id": "$RUN_ID", "job_id": "$SLURM_JOB_ID", "node": "$(hostname)",
 "model": "$MODEL", "run_index": $RUN_INDEX, "seed_set": $SEED_SET,
 "sim_time_limit": "${SIM_LIMIT:-default}", "period_s": $PERIOD,
 "initial_servers": $INITIAL_SERVERS, "max_servers": $MAX_SERVERS,
 "brownout_levels": $BROWNOUT_LEVELS, "arms": "$ARMS", "prompt_format": "$PROMPT_FORMAT",
 "temperature": "${TEMPERATURE:-default}",
 "finished": "$(date -uIseconds)"}
JSON
if [ -n "${COLLECT_FAILED:-}" ]; then
    echo "an arm produced no usable output or failed its integration check -> $OUT"
    exit 1
fi
echo "done -> $OUT"
