# TAS.v1.6

Tele Assistance System exemplar (Weyns & Calinescu, SEAMS 2015). Three Eclipse
projects, originally built/run via Eclipse; `build.sh`/`run.sh`/`clean.sh` here
replicate that build by hand with plain `javac`/`java`.

## Structure

```
ResearchServicePlatform/   Generic self-adaptive service platform (RSP): service
                            registry, workflow DSL + interpreter, adaptation
                            probes/effectors. No dependencies on the other two.
TeleAssistanceSystem/      TAS domain instance built on RSP: the concrete
                            services (alarm, drug, medical, assistance, ...),
                            the adaptation strategies, and the workflow script
                            wiring them together. No GUI, no main().
TAS_gui/                   JavaFX front end. Depends on TeleAssistanceSystem
                            (which depends on RSP). Holds the runnable entry
                            point (application.MainGui) and the dashboard.
```

Dependency order: `ResearchServicePlatform -> TeleAssistanceSystem -> TAS_gui`.

## Prerequisites

- JDK 17 (`javac -version`)
- JavaFX 17.x SDK (not bundled with the JDK since Java 11) — expected at
  `~/tools/javafx-sdk-17.0.15` by default, override with the `JAVAFX_HOME`
  env var if installed elsewhere. Must match the JDK's class-file version:
  newer JavaFX SDKs target newer JDKs and `javac` will refuse to read them.

## Build / run

```
./clean.sh   # remove build output (needed after renaming/deleting a .java file --
             #  javac doesn't clean up stale .class files on its own)
./build.sh   # compile all three modules in dependency order
./run.sh     # launch the GUI (must run via this script: working directory
             #  and JavaFX module-path both matter, see comments in run.sh)
```

## Notes

- `ServiceProfileController.java` originally imported the internal
  `com.sun.javafx.scene.control.skin.TableHeaderRow`, inaccessible from
  outside its module on JavaFX 11+. Fixed to the public equivalent
  `javafx.scene.control.skin.TableHeaderRow` (moved package in JavaFX 9,
  same class) — the only source change needed to get this building.
- `bin/` directories under each module are stale precompiled output from
  whenever this was last built in Eclipse — unrelated to `out/`, which is
  what `build.sh`/`clean.sh` produce/remove.
- TAS_gui's own `libs/` doesn't have everything it needs at runtime: GUI code
  calls into RSP/TeleAssistanceSystem classes (e.g. `ProfileExecutor`'s
  XStream-based profile loading, used by the Inspect/Edit Profile action) that
  pull in *those* modules' own libraries. Eclipse's project references don't
  propagate a dependency's library jars downstream, so `build.sh`/`run.sh`
  pull in RSP's and TeleAssistanceSystem's full `libs/` for TAS_gui too.
- Runtime needs four `--add-opens` flags (see `run.sh`): XStream 1.5.0
  reflectively `setAccessible()`s several private JDK-internal fields when
  its constructor registers built-in converters, which JPMS blocks by default
  since Java 9. Found by trial-and-error against the Inspect/Edit Profile
  action specifically — a different XStream code path in the app could
  surface a `InaccessibleObjectException` for a package not yet in that list.
