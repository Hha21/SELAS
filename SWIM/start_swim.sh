#!/usr/bin/env bash
# Starts the SWIM Docker container and launches the OMNeT++ simulation inside it,
# opening the external TCP control interface on port 4242. Standalone -- SWIM has
# no notion of NATS/POLARIS; this just brings up the managed system being controlled.
# POLARIS connects to this over TCP separately once it's up.
set -uo pipefail

SWIM_PORT=4242

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
