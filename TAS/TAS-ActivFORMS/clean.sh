#!/usr/bin/env bash
# See TAS.v1.6/clean.sh for rationale (javac doesn't clean up stale .class files
# from renamed/deleted .java files on its own).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

rm -rf "$ROOT/ResearchServicePlatform/out" \
       "$ROOT/TeleAssistanceSystem/out" \
       "$ROOT/TAS_gui/out"
rm -f "$ROOT"/.rsp_sources.txt "$ROOT"/.tas_sources.txt "$ROOT"/.gui_sources.txt

echo "== clean complete =="
