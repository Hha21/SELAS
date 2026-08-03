#!/usr/bin/env bash
# Stops the SWIM container. It's kept around (not removed) so a later
# start_swim.sh / `docker start swim` is instant instead of re-pulling the image
# and re-initialising the desktop. Pass --rm to remove the container entirely.
set -uo pipefail

if [ "${1:-}" = "--rm" ]; then
    if docker rm -f swim 2>/dev/null; then
        echo "swim container removed"
    else
        echo "No swim container found."
    fi
else
    if docker stop swim 2>/dev/null; then
        echo "swim container stopped"
    else
        echo "No running swim container found."
    fi
fi
