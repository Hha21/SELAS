#!/usr/bin/env bash
# Runs the SA-BSN exemplar (bsn/) inside a disposable ROS Melodic Docker
# container, headless (rosmon instead of upstream run.sh's per-node
# gnome-terminal windows, which don't exist in a container).
#
# Usage: ./run_bsn_docker.sh [duration_seconds] [launch_file]
#   duration_seconds : how long to let the exemplar run, in seconds (default 300,
#                       matching upstream run.sh's default)
#   launch_file       : which launch file to run (default bsn_full.launch, which
#                       includes the uncertainty injector, matching what upstream
#                       run.sh actually launches; use bsn.launch to skip it)
set -euo pipefail

DURATION="${1:-300}"
LAUNCH_FILE="${2:-bsn_full.launch}"

if ! [[ "${DURATION}" =~ ^[0-9]+$ ]]; then
    echo "duration_seconds must be a non-negative integer, got: ${DURATION}" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BSN_DIR="${SCRIPT_DIR}/bsn"
IMAGE_TAG="bsn-exemplar:dev"
CONTAINER_NAME="bsn-run-$$"

if [[ ! -f "${BSN_DIR}/${LAUNCH_FILE}" ]]; then
    echo "No such launch file: ${BSN_DIR}/${LAUNCH_FILE}" >&2
    exit 1
fi

cleanup() {
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker build -t "${IMAGE_TAG}" -f "${BSN_DIR}/Dockerfile.dev" "${BSN_DIR}"

set +e
docker run --rm \
    --name "${CONTAINER_NAME}" \
    -v "${BSN_DIR}:/workspaces/bsn" \
    -w /workspaces/bsn \
    -e DURATION="${DURATION}" \
    -e LAUNCH_FILE="${LAUNCH_FILE}" \
    "${IMAGE_TAG}" \
    bash -lc '
        set -e
        source /opt/ros/melodic/setup.bash
        rosdep install --from-paths src --ignore-src -r -y
        catkin_make
        source devel/setup.bash

        roscore &
        ROSCORE_PID=$!
        trap "kill \${ROSCORE_PID} 2>/dev/null || true" EXIT
        sleep 5

        # timeout owns the wall-clock budget: sends SIGINT (rosmon shuts its
        # nodes down cleanly on that) after DURATION seconds, SIGKILL 15s
        # later if it has not exited by then. Exit code 124/137 (timed out)
        # is the expected/normal outcome here, not a failure.
        # (rosmon launch file the "mon" command wraps -- rosmon_core -- run
        # directly so timeout can exec it; "mon" is only a shell function,
        # not on PATH, which timeout cannot exec.)
        timeout --signal=INT --kill-after=15 "${DURATION}" \
            rosrun rosmon_core rosmon --disable-ui "${LAUNCH_FILE}"
    '
DOCKER_EXIT=$?
set -e

# 0: mon exited on its own before the deadline. 124/137: timeout did its job
# (SIGINT/SIGKILL) -- both are the expected shutdown path, not failures.
if [[ "${DOCKER_EXIT}" -ne 0 && "${DOCKER_EXIT}" -ne 124 && "${DOCKER_EXIT}" -ne 137 ]]; then
    echo "bsn container exited with unexpected status ${DOCKER_EXIT} -- check output above" >&2
    exit "${DOCKER_EXIT}"
fi

echo "Run complete (exit ${DOCKER_EXIT}). Logs: ${BSN_DIR}/src/sa-bsn/knowledge_repository/resource/logs"
