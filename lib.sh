#!/usr/bin/env bash
# Shared helpers for start_nla.sh / stop_nla.sh / start_polaris.sh / stop_polaris.sh.
#
# Sourced, never executed. Everything here is deliberately dependency-free: these
# scripts run on two different machines (the GPU box serves NLA, the Docker box
# runs POLARIS + SWIM) and only one of them has torch, tmux or a docker daemon.

# ROOT is set by the caller before sourcing (it knows its own location).
: "${ROOT:?lib.sh: ROOT must be set before sourcing}"
RUN_DIR="$ROOT/run"

RED=$'\033[0;31m'; GRN=$'\033[0;32m'; YLW=$'\033[1;33m'; BLU=$'\033[0;34m'; NC=$'\033[0m'
info()  { echo "${BLU}[INFO]${NC} $*"; }
ok()    { echo "${GRN}[ OK ]${NC} $*"; }
warn()  { echo "${YLW}[WARN]${NC} $*"; }
err()   { echo "${RED}[FAIL]${NC} $*" >&2; }

# Load .env from the repo root, if present. Values already exported win, so
# `NLA_DEVICE=cpu ./start_nla.sh` still overrides the file. Mirrors what
# POLARIS's own start script does with polaris_poc/.env, so there is one
# convention across the repo rather than two.
load_env() {
    local f="$ROOT/.env"
    [[ -f "$f" ]] || return 0
    local before after
    while IFS= read -r line; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ "$line" =~ ^[[:space:]]*$ ]] && continue
        [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)= ]] || continue
        local key="${BASH_REMATCH[1]}"
        # Already set in the environment -> leave it alone.
        [[ -n "${!key+x}" ]] && continue
        local val="${line#*=}"
        val="${val%\"}"; val="${val#\"}"
        val="${val%\'}"; val="${val#\'}"
        export "$key=$val"
    done < "$f"
    info "Loaded config from .env"
}

is_running() { [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null; }

# stop_service <name> <pidfile> <match>
# Terminates by pid, then falls back to a pattern match so a service started by
# hand (no pidfile) is still cleaned up.
stop_service() {
    local name="$1" pidfile="$2" match="$3" pid stopped=false

    if [[ -f "$pidfile" ]]; then
        pid="$(cat "$pidfile")"
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            for _ in $(seq 1 20); do
                kill -0 "$pid" 2>/dev/null || { stopped=true; break; }
                sleep 0.5
            done
            $stopped || { kill -9 "$pid" 2>/dev/null; stopped=true; }
            ok "$name stopped (pid $pid)"
        fi
        rm -f "$pidfile"
    fi

    if ! $stopped; then
        local strays
        strays="$(pgrep -f "$match" 2>/dev/null || true)"
        if [[ -n "$strays" ]]; then
            # shellcheck disable=SC2086
            kill $strays 2>/dev/null
            sleep 1
            strays="$(pgrep -f "$match" 2>/dev/null || true)"
            # shellcheck disable=SC2086
            [[ -n "$strays" ]] && kill -9 $strays 2>/dev/null
            ok "$name stopped (matched '$match')"
        else
            info "$name was not running"
        fi
    fi
}

# warn_if_listening <port>...
warn_if_listening() {
    local leftovers="" port
    for port in "$@"; do
        ss -ltn 2>/dev/null | grep -q ":$port " && leftovers+=" $port"
    done
    [[ -n "$leftovers" ]] && warn "Still listening on:$leftovers (started outside these scripts?)"
    return 0
}
