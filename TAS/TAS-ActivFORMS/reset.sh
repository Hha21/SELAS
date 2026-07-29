#!/usr/bin/env bash
# Kills any running TAS GUI processes and frees ports 9000-9002 (ActivFORMSEngine's
# fixed ports for Model Adaptation/Model Evolution/Goal Management). These JavaFX/GTK
# processes don't always exit cleanly on their own (the "... Is Not Responding" hang
# needs Force Quit / SIGKILL) -- if one's left running, the next launch's engine
# constructors fail with "BindException: Address already in use". Matches
# application.MainGui (also catches a stray TAS.v1.6 instance -- same class name)
# and the standalone ActivFORMS viewer (ActivFORMSv2.7.jar).
set -uo pipefail

PIDS="$(pgrep -f 'application\.MainGui' || true) $(pgrep -f 'ActivFORMSv2\.7\.jar' || true)"
PIDS="$(echo "$PIDS" | tr ' ' '\n' | grep -v '^$' | sort -u)"

if [ -z "$PIDS" ]; then
    echo "No running TAS processes found."
else
    echo "Killing: $(echo "$PIDS" | tr '\n' ' ')"
    kill -9 $PIDS 2>/dev/null
    sleep 1
fi

for port in 9000 9001 9002; do
    if ss -ltn 2>/dev/null | grep -q ":$port "; then
        echo "Warning: port $port is still in use"
    fi
done

echo "reset complete"
