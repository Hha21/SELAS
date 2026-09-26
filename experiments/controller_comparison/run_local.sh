#!/usr/bin/env bash
# The local counterpart of run_comparison.sbatch: SWIM in Docker on this
# machine, the model through OpenRouter. For trying models that are not on CSF.
#
#   run_local.sh --model qwen/qwen3-235b-a22b-2507 --provider Parasail \
#       --arms "k2@0 k2-words@0 k2-formula@0" --tag qwen3-prompts --port-base 15000
#
# Everything that defines a run is shared with the CSF job rather than copied:
# the arms are read out of run_comparison.sbatch's ARM_SPEC, the configuration is
# SWIM's published one (--classic there), and the same checks apply -- the
# backend is proved before SWIM starts, a port already in use is refused, each
# arm must end with its own .vec and decisions, and every run goes through the
# integration check. SWIM's image here is gabrielmoreno/swim, the image CSF's
# swim.sif was built from, and its swim.ini is the repository's.
#
# The key is read from ~/.config/selas/openrouter.env (OPENROUTER_API_KEY) and
# is never printed. Runs are 105 minutes of real time: the machine must stay
# awake, so the script holds a sleep inhibitor where systemd allows it.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
IMAGE="${SELAS_SWIM_IMAGE:-gabrielmoreno/swim:latest}"
PY="${SELAS_PYTHON:-python3}"
PLOT_PY="${SELAS_PLOT_PYTHON:-$REPO/.venv/bin/python}"

MODEL=""; PROVIDER=""; ARMS=""; TAG="local"; PORT_BASE=15000; DECIDE=score
TRACE=clarknet; INITIAL_SERVERS=3; MAX_SERVERS=12; BROWNOUT_LEVELS=10; BOOT_DELAY=180
PERIOD=60; TEMPERATURE=0
SIM_LIMIT="${SELAS_SIM_LIMIT:-}"      # e.g. 180s for a smoke test; empty = SWIM's 6300 s
while [ $# -gt 0 ]; do
    case "$1" in
        --model) MODEL="$2"; shift 2 ;;
        --provider) PROVIDER="$2"; shift 2 ;;
        --decide) DECIDE="$2"; shift 2 ;;       # score (vLLM-style) or generate; see run_controller.py
        --arms) ARMS="$2"; shift 2 ;;
        --tag) TAG="$2"; shift 2 ;;
        --port-base) PORT_BASE="$2"; shift 2 ;;
        --trace) TRACE="$2"; shift 2 ;;                 # clarknet | worldcup
        --boot-delay) BOOT_DELAY="$2"; shift 2 ;;       # 0 | 60 | 120 | 180 | 240
        --max-servers) MAX_SERVERS="$2"; shift 2 ;;
        --initial-servers) INITIAL_SERVERS="$2"; shift 2 ;;
        -h|--help) sed -n '2,20p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "unknown option $1" >&2; exit 1 ;;
    esac
done
[ -n "$ARMS" ] || { echo "--arms is required" >&2; exit 1; }

# bootDelay is a sweep variable in swim.ini, selected by run index (`swim -q
# runs`): WorldCup is runs 0-4 and ClarkNet runs 5-9, at boot delays 0, 60,
# 120, 180, 240 s in that order. The published configuration is ClarkNet at
# 180 s, run 8. The controller is told the same delay, since SWIM does not
# report it over the socket.
case "$TRACE" in clarknet) base=5 ;; worldcup) base=0 ;;
    *) echo "--trace must be clarknet or worldcup" >&2; exit 1 ;; esac
case "$BOOT_DELAY" in 0|60|120|180|240) ;;
    *) echo "--boot-delay must be one of 0 60 120 180 240 (SWIM's sweep)" >&2; exit 1 ;; esac
RUN_INDEX=$(( base + BOOT_DELAY / 60 ))

# The arms, from the one place they are defined.
eval "$(sed -n '/^declare -A ARM_SPEC=(/,/^)/p' "$HERE/run_comparison.sbatch")"

if [ -f "$HOME/.config/selas/openrouter.env" ]; then
    set -a; . "$HOME/.config/selas/openrouter.env"; set +a
fi

RUN_ID="$TAG-$(date -u +%Y%m%d-%H%M%S)"
OUT="${SELAS_RESULTS:-$REPO/results-local}/$RUN_ID"
mkdir -p "$OUT"
exec > >(tee -a "$OUT/job.log") 2>&1
echo "run       $RUN_ID"
echo "model     ${MODEL:-<none>} @ ${PROVIDER:-any provider}, decide=$DECIDE"
echo "arms      $ARMS"
echo "config    $TRACE (run $RUN_INDEX), servers $INITIAL_SERVERS..$MAX_SERVERS, boot $BOOT_DELAY s, $BROWNOUT_LEVELS levels"

# The same edit of the repository's swim.ini as the CSF job.
SWIM_INI="$OUT/swim.ini"
sed -e "s/^\*\.initialServers *=.*/*.initialServers = $INITIAL_SERVERS/" \
    -e "s/^\*\.maxServers *=.*/*.maxServers = $MAX_SERVERS/" \
    -e "s/^\*\.numberOfBrownoutLevels *=.*/*.numberOfBrownoutLevels = $BROWNOUT_LEVELS/" \
    "$REPO/SWIM/simulations/swim/swim.ini" > "$SWIM_INI"

needs_model=0
for t in $ARMS; do case "${ARM_SPEC[${t%@*}]:-}" in *"--policy llm"*) needs_model=1 ;; esac; done
llm_flags=(--backend openrouter --llm-model "$MODEL" --prompt-format chat --temperature "$TEMPERATURE"
           --decide "$DECIDE")
[ -n "$PROVIDER" ] && llm_flags+=(--provider "$PROVIDER")

cd "$REPO/CONTROLLER"
if [ "$needs_model" = 1 ]; then
    [ -n "$MODEL" ] || { echo "an LLM arm needs --model" >&2; exit 1; }
    "$PY" run_controller.py --check-backend "${llm_flags[@]}" --boot-delay "$BOOT_DELAY" \
        --dimmer-levels "$BROWNOUT_LEVELS" > "$OUT/check_backend.txt" 2>&1
    tail -1 "$OUT/check_backend.txt"
    grep -q "^OK" "$OUT/check_backend.txt" || { echo "backend check failed; not starting SWIM" >&2; exit 1; }
fi

CONTAINERS=""; CTL_PIDS=""; SWIM_PIDS=""
cleanup() {
    for pid in $CTL_PIDS; do kill "$pid" 2>/dev/null; done
    for c in $CONTAINERS; do docker kill "$c" >/dev/null 2>&1; done
}
trap cleanup EXIT

i=0
for token in $ARMS; do
    arm="${token%@*}"; seed=0
    case "$token" in *@*) seed="${token##*@}" ;; esac
    label="${token/@/-s}"
    [ -n "${ARM_SPEC[$arm]:-}" ] || { echo "unknown arm '$arm'" >&2; exit 1; }
    port=$(( PORT_BASE + i )); i=$(( i + 1 ))
    res="$OUT/$label"; mkdir -p "$res"
    if (exec 3<>/dev/tcp/127.0.0.1/$port) 2>/dev/null; then
        echo "port $port is already in use; refusing to start '$label'" >&2; exit 1
    fi
    name="selas-$RUN_ID-$label"
    echo "starting SWIM for '$label' (seed-set $seed) on :$port"
    docker run --rm --name "$name" --network host --user "$(id -u):$(id -g)" \
        -v "$res":/headless/seams-swim/results \
        -v "$SWIM_INI":/headless/seams-swim/swim/simulations/swim/swim.ini:ro \
        --entrypoint bash "$IMAGE" -lc "
        cd /headless/seams-swim/swim/simulations/swim
        export PATH=/opt/omnetpp-5.4.1/bin:\$PATH
        export LD_LIBRARY_PATH=/opt/omnetpp-5.4.1/lib:\$LD_LIBRARY_PATH
        ../../src/swim swim.ini -u Cmdenv -c sim -r $RUN_INDEX --seed-set=$seed \
            --socketrtscheduler-port=$port ${SIM_LIMIT:+--sim-time-limit=$SIM_LIMIT} \
            -n ..:../../src:../../../queueinglib -l ../../../queueinglib/libqueueinglib.so
    " > "$res/swim.log" 2>&1 &
    swim_pid=$!
    SWIM_PIDS="$SWIM_PIDS $swim_pid"; CONTAINERS="$CONTAINERS $name"

    up=0
    for _ in $(seq 1 60); do
        (exec 3<>/dev/tcp/127.0.0.1/$port) 2>/dev/null && { up=1; break; }
        sleep 1
    done
    if [ "$up" != 1 ] || ! kill -0 "$swim_pid" 2>/dev/null; then
        echo "SWIM for '$label' is not listening on :$port" >&2; tail -5 "$res/swim.log" >&2; exit 1
    fi

    read -r -a extra <<< "${ARM_SPEC[$arm]}"
    case "${ARM_SPEC[$arm]}" in *"--policy llm"*) extra+=("${llm_flags[@]}") ;; esac
    "$PY" run_controller.py --port "$port" --period "$PERIOD" \
        --boot-delay "$BOOT_DELAY" --dimmer-levels "$BROWNOUT_LEVELS" --random-seed "$seed" \
        --run-dir "$res" --run-id "$label" "${extra[@]}" > "$res/controller.log" 2>&1 &
    CTL_PIDS="$CTL_PIDS $!"
    echo "  controller '$label' started"
done

echo "waiting for the simulations..."
wait $SWIM_PIDS
sleep 15
for pid in $CTL_PIDS; do kill "$pid" 2>/dev/null; done
sleep 3

echo "=== collecting ==="
cd "$HERE"
dirs=(); labels=(); for t in $ARMS; do dirs+=("$OUT/${t/@/-s}"); labels+=("${t/@/-s}"); done
"$PY" collect.py "${dirs[@]}" -o "$OUT/runs.json" > "$OUT/collect.txt" 2>&1 || echo "collect.py failed"
[ -x "$PLOT_PY" ] && "$PLOT_PY" plot.py "$OUT/runs.json" -o "$OUT/comparison" --labels "${labels[@]}" \
    --title "$MODEL, run $RUN_INDEX (local)" > /dev/null 2>&1

bad=0
echo "=== integration check ==="
for t in $ARMS; do
    d="$OUT/${t/@/-s}"
    n_vec=$(find "$d" -name "*.vec" -size +0 2>/dev/null | wc -l)
    n_dec=$(cat "$d"/*/decisions.jsonl 2>/dev/null | wc -l)
    if [ "$n_vec" -eq 0 ] || [ "$n_dec" -eq 0 ]; then
        echo "  FAILED ${t/@/-s}: $n_vec .vec, $n_dec decisions"; bad=1; continue
    fi
    "$PY" "$REPO/CONTROLLER/tests/audit_swim_integration.py" check --results "$d" --unscripted \
        --brief > "$d/integration_check.json" 2>&1
    "$PY" - "$d/integration_check.json" "${t/@/-s}" <<'PY' || bad=1
import json, sys
txt = open(sys.argv[1]).read()
try:
    rep = json.loads(txt[txt.index("{"):])
except ValueError:
    print(f"  {sys.argv[2]:18s} check did not run"); sys.exit(1)
print(f"  {sys.argv[2]:18s} {len(rep['problems'])} problems, {len(rep['notes'])} notes")
sys.exit(1 if rep["problems"] else 0)
PY
done
"$PY" - "$OUT/runs.json" <<'PY'
import json, sys
try:
    runs = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
for r in (runs if isinstance(runs, list) else runs.get("runs", [])):
    if r.get("utility_seams2017a") is None:
        continue                         # nothing scored, e.g. a run shorter than the warm-up
    print(f"  {r['run_dir'].rstrip('/').split('/')[-1]:18s} utility {r['utility_seams2017a']:9.1f}  "
          f"late {r['late_periods_seams']}/{r['scored_periods']}")
PY
[ "$bad" = 1 ] && { echo "FAILED: see above -> $OUT"; exit 1; }
echo "done -> $OUT"
