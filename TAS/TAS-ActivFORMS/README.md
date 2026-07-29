# TAS-ActivFORMS

A newer variant of the TAS exemplar (see `../TAS.v1.6/README.md` for the baseline)
that replaces the plain Retry/Select-Reliable adaptation logic with **ActivFORMS**
(M. Usman Iftikhar / Danny Weyns): a runtime-verification-based MAPE-K framework
that adapts by checking a live formal (timed-automata) model against temporal-logic
properties, rather than fixed rules. Bundled as `ActivFORMSv2.7.jar` in
`TeleAssistanceSystem/libs` and `TAS_gui/libs`.

## Structure

Same three-module shape as `TAS.v1.6` (`ResearchServicePlatform -> TeleAssistanceSystem
-> TAS_gui`; RSP is byte-identical between the two). What's new:

```
TeleAssistanceSystem/src/activforms/           ActivFORMS integration glue: Probe/Effector
                                                 adapt TAS's own probe/effector interfaces
                                                 to ActivFORMS's channel-based engine, plus
                                                 LoadBalancer/LoadProbe/ModeListener for
                                                 goal-driven mode switching.
TeleAssistanceSystem/src/activforms/engines/   Three adaptation engines (see below),
                                                 registered in tas.configuration.TASStart
                                                 alongside the original "No Adaptation".
TeleAssistanceSystem/src/tas/configuration/    AdaptationEngine/DefaultAdaptationEngine/
                                                 TASStart, moved here from tas.adaptation
                                                 (which now only holds legacy, unused code).
TeleAssistanceSystem/resources/models/         Formal model XML files the engines load
                                                 (model-adaptation.xml, model-evolution.xml,
                                                 regular-mode.xml, critical-mode.xml).
```

Adaptation engines registered in `TASStart` (all four constructed eagerly at GUI
startup, not lazily on selection):

- **No Adaptation** -- `DefaultAdaptationEngine`, unchanged baseline.
- **Model Adaptation** -- `ModelAdaptationEngine`: runs `model-adaptation.xml` against
  live probe/effector events over named channels, checks properties like
  `"Analysis.AdaptationNeeded --> Execution.PlanExecuted"` to decide retry/switch.
- **Model Evolution** -- `ModelEvolutionEngine`: same mechanism, `model-evolution.xml`,
  demonstrating runtime model swapping.
- **Goal Management** -- `GoalManagementEngine`: a goal tree with mode switching --
  a `LoadBalancer` feeds a `serverLoad` variable, and the goal tree swaps between a
  `Regular` model and a `Critical` model when load crosses a threshold.

## Prerequisites

Same as `TAS.v1.6`: JDK 17, JavaFX 17.x SDK (`~/tools/javafx-sdk-17.0.15` by default,
override with `JAVAFX_HOME`).

## Build / run

```
./clean.sh
./build.sh
./run.sh
```

Each ActivFORMS-based engine binds a fixed port at construction (9000/9001/9002) --
if the app doesn't shut down cleanly, the next launch fails with `BindException:
Address already in use`. Run `./reset.sh` to kill any stray `application.MainGui`/
`ActivFORMSv2.7.jar` processes and confirm the ports are free before relaunching.

## Notes

- `ServiceProfileController.java` needed the same fix as `TAS.v1.6`: internal
  `com.sun.javafx.scene.control.skin.TableHeaderRow` swapped for the public
  `javafx.scene.control.skin.TableHeaderRow`.
- `TeleAssistanceSystem/libs` no longer carries its own copies of antlrworks/
  javax.jms-api/xstream/activemq (all present in `TAS.v1.6`) -- `ActivFORMSv2.7.jar`
  replaces them as this module's own dependency. RSP's own `libs/` (which does still
  carry those) must still be pulled onto the runtime classpath for anything
  downstream that calls into RSP code -- same reasoning as `TAS.v1.6`'s README.
- `run.sh` needs five `--add-opens` flags, not `TAS.v1.6`'s four: on top of XStream's
  (`ProfileExecutor`, used identically here), Gson -- bundled inside
  `ActivFORMSv2.7.jar` and used by `GoalManager.updateData()` to serialize engine
  state to JSON -- reflects into `AtomicInteger`'s private field, blocked by JPMS
  since Java 9. Without `--add-opens java.base/java.util.concurrent.atomic=ALL-UNNAMED`,
  each `ActivFORMSEngine` constructor throws mid-init; the exception is silently
  swallowed by a `catch (Exception e)` in each engine class, so the GUI looks fine
  but every engine is left with `engine == null`, ready to NPE once actually used.
- `bin/` and `TAS_gui/build/` are the same stale Eclipse/Ant-NetBeans build output
  as in `TAS.v1.6` -- unrelated to `out/`, which `build.sh`/`clean.sh` manage.
- The GUI's "Open -> open ActivFORMS" menu action (`ApplicationController.java`,
  `openActivFORMS.setOnAction`) launches `ActivFORMSv2.7.jar`'s own bundled JavaFX
  viewer (`javafx.gui.MainApplication`) as a separate process, connecting to the
  already-running engines on `localhost:9000-9002`. The original code ran a bare
  `java -jar ...` with no JavaFX wiring (fails immediately with `NoClassDefFoundError`
  on a JDK that doesn't bundle JavaFX) and used `Runtime.exec(String)`, which never
  reads the child process's output -- so the crash was completely invisible. Fixed to
  build the same `--module-path`/`--add-modules` flags `run.sh` uses (reading
  `JAVAFX_HOME`, same default as the scripts) and to use
  `new ProcessBuilder(...).inheritIO().start()` so a future crash actually surfaces.
- **Fixed**: the ActivFORMS viewer (`javafx.gui.MainApplication`, launched by the
  action above) used to become unresponsive ("... Is Not Responding") within a
  minute or two of a live session, sometimes preceded by a
  `java.net.SocketException: Connection reset` in `GoalManager.connectionLoop()`.
  Root cause, found by decompiling `ActivFORMSv2.7.jar`'s `ActivFORMSEngine` class
  (Fernflower, since its own classes are Java 24-targeted -- needed a JDK 21+ `java`
  to run the decompiler, e.g. the one bundled with VS Code's Java extension):
  `TickerTask.run()` calls `updateGlobalDataToClients()` -- a full Gson JSON
  serialization + broadcast of the entire model state to every connected viewer --
  on every tick, and the tick period is set directly, in literal milliseconds, by
  `engine.setRealTimeUnit(...)`. All three engines called this with `1`, i.e. a
  full state broadcast roughly every millisecond (~1000/sec) -- far beyond what
  any viewer UI or socket client can keep up with. This is TAS's *own* source
  (`ModelAdaptationEngine`/`ModelEvolutionEngine`/`GoalManagementEngine`), not
  inside the compiled jar, so it was fixable: changed to `1000` (1 tick/sec) in
  all three. Note this is a real timing-fidelity tradeoff, not a purely cosmetic
  setting -- it also slows how fast the model's real-time clocks advance relative
  to the configured service response times, which is coupled to when the model
  decides adaptation is needed.
- The `Gdk-WARNING: XSetErrorHandler() called with a GDK error trap pushed`
  console message seen during the old hang is a native GTK/Glass warning from
  inside `ActivFORMSv2.7.jar`'s compiled GUI code (no source available to check)
  -- likely just a symptom of the flood above rather than a separate issue, not
  fully confirmed either way. If a hung instance still turns up, `kill -9` (or the
  desktop's "Force Quit") is needed to clear it -- plain `kill`/SIGTERM isn't
  always honored by these JavaFX/GTK processes, matching what killed
  `application.MainGui` unreliably during development too.
- **Fixed**: `tas.services.log.Log`'s `logData` (a JavaFX `ObservableList` backing the
  main GUI's log panel) grew without limit -- every `addLog()` call appended and
  nothing ever trimmed it, and `readFromFile()` re-read the *entire* persisted log
  file back into it on every startup, so it also grew across sessions, not just
  within one. Capped at `MAX_ENTRIES = 2000` in-memory entries (oldest dropped
  first); the on-disk log file is untouched and still keeps full history, only the
  in-memory/GUI-visible list is bounded now. This alone did not fix long runs
  crashing, see below.
- **Fixed**: `AssistanceServiceCostProbe.workflowEnded()` -- called once per
  workflow step -- opened a *brand new* `FileWriter` on `results/result.csv`
  (open, write, close) every single time, instead of reusing one persistent
  writer. For a 10,000-step run that's 10,000 blocking file-open/close cycles on
  the same thread driving the workflow loop; this, not just the log growth above,
  is the confirmed cause of long runs slowing down and eventually crashing (backend
  loop genuinely finishes -- "finish executing workflow!!!" appears in the console
  -- while the GUI is still catching up on a huge backlog, then the whole process
  needs a force-kill). Fixed to open the writer once (in the constructor and again
  in `reset()`, matching `Log`'s pattern) and `flush()` rather than reopen per step.
  `AssistanceServiceDelayProbe` has the identical anti-pattern but is currently
  commented out in `TASStart` (never registered) -- not touched, but would need
  the same fix if ever re-enabled. `TAS_gui/src/application/log/Log.java` is an
  unrelated, unused duplicate of the real `Log` class (nothing imports it) with
  the same unbounded-growth bug -- also left alone since it's dead code.
- **Fixed**: even after the two fixes above, a full-length run still stalled right
  at the very end -- the backend loop genuinely finished all its steps, but the
  GUI stayed stuck just short of 100%. Cause: `ChartController` (9 read-loops
  across its `generateCharts`/`generateAvgCharts` methods) and
  `TableViewController` (`fillReliabilityDate`/`fillCostData`/`fillPerformanceData`)
  each independently re-opened and fully re-parsed `results/result.csv` --
  roughly 11 full read-and-parse passes over the same file in total, by the end
  of a long run likely tens of thousands of lines (one line per step, plus one
  more per individual service call within that step). All of this ran
  synchronously inside one `Platform.runLater` block on the JavaFX Application
  Thread, right at the moment a run completes or is stopped -- exactly the
  "Not Responding" freeze seen at ~99% progress. Fixed by reading the file once
  (`ApplicationController.readResultLines()`, `Files.readAllLines`) and changing
  `generateCharts`/`generateAvgCharts`/`fillReliabilityDate`/`fillCostData`/
  `fillPerformanceData` to accept the already-read `List<String>` instead of a
  file path, reusing it across all ~11 call sites. Still runs on the FX thread
  (a deliberate choice over a larger background-thread refactor, given the I/O
  reduction alone was expected to be enough).
- **Fixed**: it wasn't enough -- a 10,000-step run still stalled at ~99%. The
  actual dominant cost turned out to be JavaFX scene-graph node creation, not
  file I/O: `generateReliabilityChart` (and the 3 other raw per-invocation
  charts, `generateCostChart`/`generateInvCostChart`/`generatePerformanceChart`)
  create one JavaFX node per *raw* invocation -- `generateReliabilityChart`'s is
  a `Rectangle` with an active property binding. For a 10,000-step run (~20-30k
  CSV lines, roughly 2-3 per step) that's tens of thousands of live scene-graph
  nodes built synchronously on the FX thread. `generateAvgCharts`'s 4 charts are
  unaffected -- already bucketed by Invocation Slice, so bounded regardless of
  maxSteps -- and so are the 3 table-filling methods (they aggregate into a
  small per-service map, only ever adding a handful of final rows). Fixed by
  skipping the 4 raw per-invocation charts (not the Avg charts, not the tables)
  when `maxSteps > RAW_CHART_MAX_STEPS` (2000, in `ChartController`) -- those
  4 tabs stay empty for very long runs, everything else still populates.
  **Currently disabled** (`ENABLE_RAW_CHART_LIMIT = false`) at user request, to
  see the full raw charts again; flip it back to `true` if a long run freezes
  the GUI.
- Long-running profiles are *not* throttled to real time: `SimClock`
  (`service/utility/SimClock.java`) is a purely logical clock (`time += value`, no
  relation to wall-clock time), and the one place that would add a real delay
  (`MessagingService.java`'s `Thread.sleep(...)`) is commented out in the active
  code path. So a "step" (one loop iteration in `TASStart.executeWorkflow()`,
  one simulated patient interaction -- vital-signs reading or panic-button press,
  chosen per the profile's configured probabilities) runs about as fast as the CPU
  allows, not at a pace matching the configured response-time values.
