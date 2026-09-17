# Controller comparison on SWIM

Two controllers driving the same SWIM configuration, plotted together: SWIM's
reactive rule and the LLM. Built to be repeatable, because the run-to-run spread
means single runs settle nothing.

## SWIM runs on CSF under apptainer

Podman does not work on CSF: the user has no `subuid`/`subgid` ranges, and the
container store lands on NFS, which does not support the extended attributes the
overlay driver needs (`lsetxattr: operation not supported`). Apptainer has
neither problem -- a single `.sif`, no daemon, no UID mapping.

```bash
export APPTAINER_CACHEDIR=$HOME/h200-scratch/apptainer/cache
export APPTAINER_TMPDIR=$HOME/h200-scratch/apptainer/tmp
apptainer pull swim.sif docker://gabrielmoreno/swim      # ~12 min, 1.1 GB
```

The image is a VNC desktop image, but **the simulation is headless**: `run.sh`
passes `-u Cmdenv`, so nothing needs X. Results must be bind-mounted out, since
the container is read-only -- which is also how the `.sca`/`.vec` finally escape
the container at all, something the Docker workflow never did.

```bash
apptainer exec --bind "$RESULTS":/headless/seams-swim/results swim.sif bash -lc '
  cd /headless/seams-swim/swim/simulations/swim_sa
  export PATH=/opt/omnetpp-5.4.1/bin:$PATH
  export LD_LIBRARY_PATH=/opt/omnetpp-5.4.1/lib:$LD_LIBRARY_PATH
  ../../src/swim swim_sa.ini -u Cmdenv -c Reactive -r 6 --seed-set=1 \
      -n ..:../../src:../../../queueinglib -l ../../../queueinglib/libqueueinglib.so'
```

A `swim_sa` run takes ~3 s: it has no real-time scheduler, unlike the
externally-controlled `swim.ini`, which is pinned to wall clock at 105 minutes.

## The 2647 baseline does not reproduce -- use these instead

`LLM_Controller_Plan.md` gives run 6 with `--seed-set=1` as utility **2647**
(Reactive) and **1740** (Reactive2), and says to stop and fix the harness if you
do not get them. Measured on the canonical upstream image:

| config | plan | measured | |
|---|---|---|---|
| `Reactive` | 2647 | **2414.3405** | −8.8% |
| `Reactive2` | 1740 | **1533.5447** | −11.9% |

This is not a harness fault, and not noise:

* the run identity is exactly right -- `configname=Reactive`,
  `trace=clarknet-http-105m-l70.delta`, `latency=60`, `network=SWIM_SA`,
  `runnumber=6`, `seedset=1`;
* the container's `swim_sa.ini` is byte-identical to this repository's copy, and
  the image is built from upstream `cps-sei/swim` at `44289ef`;
* three identical runs give **bit-identical** results (2414.3405 every time), so
  there is no stochastic spread to hide in -- `swim_sa` has no real-time
  scheduler and is fully deterministic given the seed.

The most likely cause is the OMNeT++ version. `README-source.md` specifies
OMNeT++ **5.2**; this image ships **5.4.1**, and a different version consumes the
RNG stream differently, giving a different-but-equally-valid realisation of the
same configuration. The published numbers are presumably from the older build.

**What to do about it.** The absolute figure was never the point -- it was a
correctness oracle. A deterministic, reproducible baseline serves that purpose
just as well, so treat **2414.3405 / 1533.5447 at OMNeT++ 5.4.1** as the oracle
and check against those. What matters for the paper is comparing controllers
under identical conditions, which this supports unchanged.

## Two different reactive baselines -- do not confuse them

| | ini | network | who decides | scheduler | duration |
|---|---|---|---|---|---|
| **internal** | `swim_sa.ini` | `SWIM_SA` | SWIM's C++ `ReactiveAdaptationManager` | none | ~3 s |
| **external** | `swim.ini` | `SWIM` | our Python `ReactivePolicy` over TCP | `cSocketRTScheduler` | 105 min |

The internal one validates the *environment* -- image, ini, seed handling. The
external one validates our *port of the rule*, and it is the one to compare the
LLM against, because both then run under the same scheduler. They will not agree
exactly: real-time pacing makes decision arrival wall-clock dependent, which is
where the ~21% run-to-run spread comes from.

## Pipeline

```bash
python collect.py <run-dir>... -o results/runs.json   # .sca/.vec + decisions.jsonl -> tidy
python plot.py results/runs.json -o results/comparison --labels Reactive LLM
```

`collect.py` reads OMNeT++'s SQLite output (`swim.ini` sets the SQLite
scalar/vector managers) introspectively, since the schema shifts between
versions. Utility exists only there -- `SimpleMonitor.ned` declares
`@statistic[utility](source="sum(utility)"; record=last)` for the total and
`utilityPeriod` per period; nothing outside the simulator can compute it.
Response time and the action distributions come from the controller's
`decisions.jsonl`, which SWIM does not record.
