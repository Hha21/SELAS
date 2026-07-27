#!/usr/bin/env bash
# Runs the TAS GUI. Must launch with TAS_gui/ as the working directory, since
# ApplicationController resolves resources/results paths relative to CWD (baseDir=""),
# not via the classpath.
#
# JavaFX is put on --module-path (not -cp): the JVM launcher refuses to start a main
# class that directly extends javafx.application.Application unless javafx.graphics
# is a named module on the module path, even if the classes are present via classpath.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JAVAFX_HOME="${JAVAFX_HOME:-$HOME/tools/javafx-sdk-17.0.15}"

RSP="$ROOT/ResearchServicePlatform"
TAS="$ROOT/TeleAssistanceSystem"
GUI="$ROOT/TAS_gui"

cd "$GUI"
exec java --module-path "$JAVAFX_HOME/lib" --add-modules javafx.controls,javafx.fxml,javafx.swing \
  -cp "out:$TAS/out:$RSP/out:libs/antlrworks-1.5.2-complete.jar:libs/itext-pdfa-5.5.5.jar:libs/itext-xtra-5.5.5.jar:libs/itextpdf-5.5.5.jar" \
  application.MainGui
