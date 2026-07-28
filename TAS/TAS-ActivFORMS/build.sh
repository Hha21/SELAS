#!/usr/bin/env bash
# Compiles the three TAS-ActivFORMS modules by hand, in dependency order. See
# TAS.v1.6/build.sh for the general approach this mirrors; the difference here is
# TeleAssistanceSystem/TAS_gui depend on ActivFORMSv2.7.jar (the ActivFORMS MAPE-K /
# runtime-model-checking framework) instead of the plain Retry/Select-Reliable baseline.
#
# ResearchServicePlatform (no deps, byte-identical to TAS.v1.6's copy)
#   -> TeleAssistanceSystem (RSP + JavaFX base/collections + ActivFORMSv2.7.jar)
#     -> TAS_gui (TeleAssistanceSystem + RSP transitively + JavaFX + iText + ActivFORMSv2.7.jar)
#
# JavaFX SDK version must match the installed JDK's class-file version (JDK 17 -> JavaFX 17.x).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JAVAFX_HOME="${JAVAFX_HOME:-$HOME/tools/javafx-sdk-17.0.15}"

RSP="$ROOT/ResearchServicePlatform"
TAS="$ROOT/TeleAssistanceSystem"
GUI="$ROOT/TAS_gui"

echo "== ResearchServicePlatform =="
mkdir -p "$RSP/out"
find "$RSP/src" -name "*.java" > "$ROOT/.rsp_sources.txt"
javac -d "$RSP/out" -cp "$RSP/libs/*" @"$ROOT/.rsp_sources.txt"
cp "$RSP/src/jndi.properties" "$RSP/out/"

echo "== TeleAssistanceSystem =="
mkdir -p "$TAS/out"
find "$TAS/src" -name "*.java" > "$ROOT/.tas_sources.txt"
javac -d "$TAS/out" \
  -cp "$RSP/out:$TAS/libs/*:$JAVAFX_HOME/lib/*" \
  @"$ROOT/.tas_sources.txt"

echo "== TAS_gui =="
mkdir -p "$GUI/out/application/view"
find "$GUI/src" -name "*.java" > "$ROOT/.gui_sources.txt"
# RSP's and TeleAssistanceSystem's own libs/ are needed here too (see TAS.v1.6/build.sh
# note): GUI code calls into their classes at runtime, and Eclipse's project references
# don't propagate a dependency's library jars downstream. jfxrt.jar (legacy JDK8 JavaFX
# runtime, still shipped in TAS_gui/libs here) stays excluded -- we use our own JavaFX SDK.
javac -d "$GUI/out" \
  -cp "$TAS/out:$RSP/out:$RSP/libs/*:$TAS/libs/*:$GUI/libs/antlrworks-1.5.2-complete.jar:$GUI/libs/itext-pdfa-5.5.5.jar:$GUI/libs/itext-xtra-5.5.5.jar:$GUI/libs/itextpdf-5.5.5.jar:$GUI/libs/ActivFORMSv2.7.jar:$JAVAFX_HOME/lib/*" \
  @"$ROOT/.gui_sources.txt"
# javac only compiles .java files -- fxml/css sit alongside the source and are loaded
# via getClass().getResource(...) at runtime, so copy them into the output tree too.
cp "$GUI"/src/application/view/*.css "$GUI"/src/application/view/*.fxml "$GUI/out/application/view/"

rm -f "$ROOT"/.rsp_sources.txt "$ROOT"/.tas_sources.txt "$ROOT"/.gui_sources.txt
echo "== build complete =="
