#!/usr/bin/env bash
# Removes build output produced by build.sh. Needed before a rebuild whenever a .java
# file has been renamed or deleted -- javac only compiles what it's given, so a stale
# .class file from a removed/renamed source file is never cleaned up on its own.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

rm -rf "$ROOT/ResearchServicePlatform/out" \
       "$ROOT/TeleAssistanceSystem/out" \
       "$ROOT/TAS_gui/out"
rm -f "$ROOT"/.rsp_sources.txt "$ROOT"/.tas_sources.txt "$ROOT"/.gui_sources.txt

echo "== clean complete =="
