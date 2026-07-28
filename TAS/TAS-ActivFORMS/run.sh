#!/usr/bin/env bash
# Runs the TAS-ActivFORMS GUI. See TAS.v1.6/run.sh for the rationale behind CWD,
# --module-path, and --add-opens (all apply identically here: ProfileExecutor's
# XStream usage is unchanged, and resources/results paths are still CWD-relative).
#
# Note: TASStart's constructor eagerly constructs every adaptation engine at startup
# (Model Adaptation, Model Evolution, Goal Management), each of which starts an
# ActivFORMSEngine bound to its own port (9000/9001/9002) and loads a model XML from
# resources/models/ -- so engine startup cost is paid on launch, not on engine selection.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JAVAFX_HOME="${JAVAFX_HOME:-$HOME/tools/javafx-sdk-17.0.15}"

RSP="$ROOT/ResearchServicePlatform"
TAS="$ROOT/TeleAssistanceSystem"
GUI="$ROOT/TAS_gui"

cd "$GUI"
# The atomic opens below is additionally needed here (not in TAS.v1.6): Gson, bundled
# inside ActivFORMSv2.7.jar, reflects into AtomicInteger's private field when
# GoalManager.updateData() serializes engine state to JSON. Without it, each
# ActivFORMSEngine constructor throws mid-init; the exception is swallowed by a
# try/catch in each engine class, so the GUI stays up but every engine is silently
# left with engine == null, ready to NPE the moment it's actually selected/used.
exec java --module-path "$JAVAFX_HOME/lib" --add-modules javafx.controls,javafx.fxml,javafx.swing \
  --add-opens java.base/java.util=ALL-UNNAMED \
  --add-opens java.base/java.lang.reflect=ALL-UNNAMED \
  --add-opens java.base/java.text=ALL-UNNAMED \
  --add-opens java.desktop/java.awt.font=ALL-UNNAMED \
  --add-opens java.base/java.util.concurrent.atomic=ALL-UNNAMED \
  -cp "out:$TAS/out:$RSP/out:$RSP/libs/*:$TAS/libs/*:libs/antlrworks-1.5.2-complete.jar:libs/itext-pdfa-5.5.5.jar:libs/itext-xtra-5.5.5.jar:libs/itextpdf-5.5.5.jar:libs/ActivFORMSv2.7.jar" \
  application.MainGui
