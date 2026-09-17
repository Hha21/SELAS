#!/usr/bin/env bash
# Starts the SWIM Docker container and launches the OMNeT++ simulation inside it,
# opening the external TCP control interface on port 4242. Standalone -- SWIM has
# no notion of the controller; this just brings up the managed system.
#
# Container startup and simulation startup are deliberately separate steps,
# because only the second one starts a clock. `swim.ini` sets
# `scheduler-class = "cSocketRTScheduler"`, pinning the simulation to real time:
# once `run.sh` is launched, 6300 simulated seconds take 6300 wall seconds
# whether or not anything is controlling it. The container, by contrast, can sit
# idle indefinitely at no cost.
#
# --wait-for exploits that gap. The container comes up immediately; the
# simulation is held back until the LLM endpoint answers, so a queued Slurm job
# or a slow 70B load costs no simulated time.
#
# Usage:
#   ./start_swim.sh
#   ./start_swim.sh --wait-for http://localhost:8000/health --wait-timeout 7200
#   ./start_swim.sh --container-only        # bring the container up, start nothing
set -uo pipefail

SWIM_PORT=4242
WAIT_FOR=""
WAIT_TIMEOUT=3600
CONTAINER_ONLY=false

usage() {
    sed -n '2,20p' "$0" | sed 's/^# \?//'
    exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --wait-for)       WAIT_FOR="$2"; shift 2 ;;
        --wait-timeout)   WAIT_TIMEOUT="$2"; shift 2 ;;
        --container-only) CONTAINER_ONLY=true; shift ;;
        -h|--help)        usage 0 ;;
        *) echo "Unknown option: $1" >&2; usage 1 ;;
    esac
done

if docker ps --filter name=swim --filter status=running --format '{{.Names}}' | grep -q '^swim$'; then
    echo "swim container already running"
elif docker ps -a --filter name=swim --format '{{.Names}}' | grep -q '^swim$'; then
    echo "Starting existing swim container..."
    docker start swim >/dev/null
else
    echo "Creating swim container (pulls gabrielmoreno/swim if not cached)..."
    docker run -d --name swim -p 4242:4242 -p 5901:5901 -p 6901:6901 gabrielmoreno/swim
fi

echo "Waiting for SWIM container's desktop to initialise..."
sleep 8

if [ "$CONTAINER_ONLY" = true ]; then
    echo "--container-only: container up, simulation NOT started (no clock running)."
    echo "Start it later with: ./start_swim.sh"
    exit 0
fi

# ---------------------------------------------------------------- readiness gate
# Held here rather than after `run.sh` on purpose: past this point the simulation
# is consuming its 105 minutes of wall clock, so everything it depends on has to
# be answering first.
if [ -n "$WAIT_FOR" ]; then
    echo "Waiting for $WAIT_FOR (timeout ${WAIT_TIMEOUT}s) before starting the simulation..."
    deadline=$(( $(date +%s) + WAIT_TIMEOUT ))
    backend_ready=false
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if curl -sf --max-time 10 "$WAIT_FOR" >/dev/null 2>&1; then
            backend_ready=true
            break
        fi
        remaining=$(( deadline - $(date +%s) ))
        printf '\r  not ready yet; %ds left ' "$remaining"
        sleep 10
    done
    printf '\r%*s\r' 40 ''
    if [ "$backend_ready" != true ]; then
        echo "TIMEOUT: $WAIT_FOR never answered." >&2
        echo "The simulation was NOT started, so no simulated time has been spent." >&2
        echo "The container is up; rerun this script once the endpoint is live." >&2
        exit 1
    fi
    echo "Endpoint is live. Starting the simulation now."
fi

echo "Starting SWIM OMNeT++ simulation (run.sh sim 0)..."
docker exec -d swim bash -c "cd /headless/seams-swim/swim/simulations/swim && PATH=/opt/omnetpp-5.4.1/bin:\$PATH LD_LIBRARY_PATH=/opt/omnetpp-5.4.1/lib:\$LD_LIBRARY_PATH ./run.sh sim 0"

echo "Waiting for SWIM to open port $SWIM_PORT..."
ready=false
for _ in $(seq 1 30); do
    if nc -z localhost "$SWIM_PORT" &>/dev/null; then
        ready=true
        break
    fi
    sleep 1
done

if [ "$ready" != true ]; then
    echo "SWIM failed to open port $SWIM_PORT -- check container logs: docker logs swim" >&2
    exit 1
fi

echo "SWIM is ready: tcp://localhost:$SWIM_PORT  (VNC :5901, browser http://localhost:6901)"
