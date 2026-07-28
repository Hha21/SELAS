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
# RSP's and TeleAssistanceSystem's own libs/ (xstream, javax.jms-api, activemq) are needed
# here too: GUI code calls into their classes at runtime (e.g. ProfileExecutor's XStream
# usage), and those dependencies don't propagate downstream on their own -- see build.sh.
#
# --add-opens: XStream 1.5.0's constructor eagerly registers every built-in converter,
# several of which reflectively setAccessible() on private JDK-internal fields (TreeMap's
# comparator, Proxy's handler, AttributedCharacterIterator$Attribute's name, AWT's
# TextAttribute map). JPMS blocks that by default since Java 9; these opens are the
# minimal set found by trial-and-error against ProfileExecutor.readFromXml (the Inspect/Edit
# Profile action). A different XStream code path could need further packages opened.
exec java --module-path "$JAVAFX_HOME/lib" --add-modules javafx.controls,javafx.fxml,javafx.swing \
  --add-opens java.base/java.util=ALL-UNNAMED \
  --add-opens java.base/java.lang.reflect=ALL-UNNAMED \
  --add-opens java.base/java.text=ALL-UNNAMED \
  --add-opens java.desktop/java.awt.font=ALL-UNNAMED \
  -cp "out:$TAS/out:$RSP/out:$RSP/libs/*:$TAS/libs/*:libs/antlrworks-1.5.2-complete.jar:libs/itext-pdfa-5.5.5.jar:libs/itext-xtra-5.5.5.jar:libs/itextpdf-5.5.5.jar" \
  application.MainGui
