# BSN

Self-Adaptive Body Sensor Network (SA-BSN) exemplar (Gil, Caldas, Rodrigues,
da Silva, Rodrigues & Pelliccione, SEAMS 2021) -- a ROS-based healthcare
exemplar: six vital-sign sensors feed a Central Hub that classifies patient
risk (low/moderate/high), with a proportional controller adapting sensor
sampling rate / hub processing rate to hold a reliability or battery-cost
setpoint under injected uncertainty.

Chosen as the fallback exemplar to TAS (see `../PROJECT_PLAN.md`) -- BSN's
adaptation decision is a continuous control knob (sampling frequency, gain)
rather than TAS's discrete retry/switch/select, and would be retargeted at
its discrete risk-classification decision instead if used.

## Recommended Reference

```
@INPROCEEDINGS{bsn,
  author={Gil, Eric Bernd and Caldas, Ricardo and Rodrigues, Arthur and da Silva, Gabriel Levi Gomes and Rodrigues, Genaína Nunes and Pelliccione, Patrizio},
  booktitle={2021 International Symposium on Software Engineering for Adaptive and Self-Managing Systems (SEAMS)},
  title={Body Sensor Network: A Self-Adaptive System Exemplar in the Healthcare Domain},
  year={2021},
  pages={224-230},
  doi={10.1109/SEAMS51251.2021.00037}}
```

The paper PDF is IEEE copyrighted (not ours to redistribute) and is
gitignored -- cite via the DOI above instead.

## Structure

```
bsn/    Vendored copy of https://github.com/lesunb/bsn (upstream .git history
         stripped -- we don't track their history, and expect to modify this
         directly). Own build output (bsn/devel, bsn/build) is gitignored via
         bsn/.gitignore, vendored as-is from upstream.
run_bsn_docker.sh   Headless Docker runner (see below) -- not part of upstream.
```

## Prerequisites

Upstream requires Ubuntu 18.04 + ROS Melodic. Rather than that or their
VirtualBox VM, we build their `bsn/Dockerfile.dev` (a plain
`ros:melodic-ros-core-bionic` image with rosdep/rosmon/catkin deps) and run
the exemplar inside a disposable container -- only Docker itself is needed
on the host.

## Build / run

```
./run_bsn_docker.sh [duration_seconds] [launch_file]
```

- `duration_seconds` defaults to 300 (upstream `run.sh`'s default).
- `launch_file` defaults to `bsn_full.launch` (includes the uncertainty
  injector, matching what upstream `run.sh` actually launches); pass
  `bsn.launch` to run without fault injection.

This builds the dev image, bind-mounts `bsn/` into the container at
`/workspaces/bsn` (so `catkin_make` build output and logs land back on the
host, incrementally cached across runs), runs `rosdep install` +
`catkin_make`, then `roscore` + `mon launch <launch_file>` (rosmon, not
upstream `run.sh`'s per-node `gnome-terminal` windows, which don't exist in
a headless container) for the given duration before sending SIGINT and
letting the container exit. `--rm` ensures the container is removed on
exit either way (including on Ctrl-C).

Logs land in `bsn/src/sa-bsn/knowledge_repository/resource/logs`, analyzed via
`bsn/src/sa-bsn/simulation/analyzer/analyzer.py` -- run from the host (not the
container), using the top-level venv (`../requirements.txt`; matplotlib +
numpy is all it actually imports, despite `Dockerfile.dev` also installing
pandas, which nothing in this repo uses). The script only resolves its log
paths relative to its own directory, so it must be run from there, matching
upstream's README:

```
source ../../../.venv/bin/activate   # or: /path/to/SummerWork/.venv/bin/python analyzer.py ...
cd bsn/src/sa-bsn/simulation/analyzer
python3 analyzer.py <logID> reliability False 0.9
```

## Notes

- `src/Analyzer.py`'s `run()` ends with a bare `plt.show()`, which is a no-op
  under Docker/CI's headless `Agg` backend (`UserWarning: FigureCanvasAgg is
  non-interactive`) -- there's simply nothing to show. Patched to also
  `fig.savefig(...)` into `simulation/analyzer/plots/<formula>_<logID>.png`
  (gitignored, same "ignore everything except .gitignore" pattern as
  `knowledge_repository/resource/logs/`) beforehand, so headless runs still
  produce a viewable result; `plt.show()` itself is left in place for when a
  display is available. The save uses `import os as _os` -- `run()` already
  has a local variable named `os` (short for "overshoot"), which shadows a
  plain `import os` for the rest of that function.
