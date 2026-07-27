#!/usr/bin/env bash
# Compiles the three TAS.v1.6 modules by hand, in dependency order, mirroring
# what Eclipse's .project/.classpath files would otherwise do:
#   ResearchServicePlatform (no deps)
#     -> TeleAssistanceSystem (depends on RSP + JavaFX base/collections)
#       -> TAS_gui (depends on TeleAssistanceSystem + RSP transitively + JavaFX + iText)
#
# JavaFX SDK version must match the installed JDK's class-file version (JDK 17 -> JavaFX 17.x;
# newer JavaFX SDKs are compiled for newer JDKs and javac will refuse to read their jars).
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
javac -d "$GUI/out" \
  -cp "$TAS/out:$RSP/out:$GUI/libs/antlrworks-1.5.2-complete.jar:$GUI/libs/itext-pdfa-5.5.5.jar:$GUI/libs/itext-xtra-5.5.5.jar:$GUI/libs/itextpdf-5.5.5.jar:$JAVAFX_HOME/lib/*" \
  @"$ROOT/.gui_sources.txt"
# javac only compiles .java files -- fxml/css sit alongside the source and are loaded
# via getClass().getResource(...) at runtime, so copy them into the output tree too
# (Eclipse does this automatically for anything in a source folder; we do it by hand).
cp "$GUI"/src/application/view/*.css "$GUI"/src/application/view/*.fxml "$GUI/out/application/view/"

rm -f "$ROOT"/.rsp_sources.txt "$ROOT"/.tas_sources.txt "$ROOT"/.gui_sources.txt
echo "== build complete =="
