# CONTROLLER — a minimal LLM controller for SWIM

A self-adaptive controller that drives the [SWIM](../SWIM) exemplar directly,
with an LLM making the adaptation decisions, built to be instrumented with
mechanistic interpretability tooling.

Sits in the same slot `POLARIS/` did — the **managing system** — and replaces it.
The rationale is in [`../LLM_Controller_Plan.md`](../LLM_Controller_Plan.md); the
defects that motivated the move are in
[`../POLARIS_WIRING_AUDIT_2026-09.md`](../POLARIS_WIRING_AUDIT_2026-09.md).

Nothing here depends on NATS, gRPC, tmux, or a plugin loader. The reactive
baseline and the stub backend run on a bare Python 3.12+ interpreter with no
third-party packages at all.

---

## What it does

Once per 60 s evaluation period:

```
 SWIM ──sense──▶ Trajectory ──▶ ContextBuilder ──▶ backend.generate  (reasoning)
                                      │                    │
                                      └────────────────────┴──▶ backend.score
                                                                     │
 SWIM ◀──act─── safety gate ◀── argmax ◀── mask illegal ◀─────────────┘
```

Every period is also evaluated by SWIM's own reactive rule, whichever policy is
driving. That costs nothing, needs no model, and turns one run into ~90 paired
decisions rather than a single aggregate number — the periods where the two
rules **disagree** are the interesting set, and they are identified for free.

### The decision is scored, not generated

The action space is at most eight options, so the controller ends the prompt with
`Action:` and compares the log-probability of each legal single-token
continuation. This is the central design choice:

- parse failure becomes structurally impossible (POLARIS lost a whole run to it:
  1837/3837 unparseable completions, zero adaptations in 90 periods);
- it needs no tool-calling and no chat template, so it works on **base** models —
  which matters, because the released NLA checkpoints are trained on base-model
  activations;
- it yields a full distribution over actions every period, which is the readout
  the interpretability analysis needs.

### The prompt is segmented, and the segmentation is the experiment

| | |
|---|---|
| **A** static prefix | role, constraints, action legend, worked examples. Byte-identical every decision. |
| **B** state | telemetry, rolling window, recent actions and their observed effect. The only part that varies. |
| **C** decision | `Reasoning:` scaffold with named fields ending in a free `Therefore:` line, then `Action:`. |

Because A never varies, any difference in the model's internal state at the end
of B is attributable to the system state and nothing else.

Probe positions come back as character offsets (`Prompt.probes`); mapping them
onto token indices belongs to whatever owns the tokeniser, which is why this
package has no model dependency.

| probe | where | what it is for |
|---|---|---|
| `P0_state_end` | end of segment B | what the model understood *before* generating a reasoning token |
| `P_sla`, `P_capacity`, `P_trend`, `P_therefore` | end of each scaffold line | semantically labelled positions — an explanation here can be checked against what the line is supposed to be about |
| `P_action` | the last position before the action logits | **the** activation that causally determines the decision |

Comparing what can be decoded from `P0_state_end` against `P_action` is the
point of the arrangement: if a probe predicts the action equally well from both,
the reasoning was decorative, and that is a quantitative result about CoT
faithfulness rather than an anecdote.

---

## Running it

Wiring checks, cheapest first. Each needs strictly less than the next.

```bash
# 0. bring SWIM up (separate terminal)
../SWIM/start_swim.sh

# 1. can we talk to SWIM at all?
./run_controller.py --probe

# 2. what does the model actually see?
./run_controller.py --print-prompt

# 3. the oracle — no model involved
./run_controller.py --policy reactive

# 4. the whole loop, no GPU
./run_controller.py --policy llm --backend stub --period 5 --max-periods 10

# 5. against a served model
./run_controller.py --policy llm --backend openai \
    --llm-base-url http://localhost:8000/v1 --llm-model local-nla
```

Useful flags:

```
--dimmer-mode step     restrict the dimmer to ±1 step, matching the reactive
                       baseline's action space (see "Comparability" below)
--reasoning none       state → Action:, a single forward pass, no CoT
--reasoning free       "Let's think step by step" instead of the scaffold
--dry-run              decide and log, never send an action to SWIM
--max-periods N        stop after N decisions
```

Each run writes `runs/<run_id>/decisions.jsonl`, one record per period, with the
observation, the prompt, the reasoning, **both** distributions (masked and
unmasked), the probe offsets, the reactive shadow decision, and what SWIM
replied. `run_id` is stamped on every record.

### Tests

```bash
python -m pytest tests/ -q     # 30 tests, no SWIM, no model, no network
```

They include a fake SWIM that speaks the real line protocol, so the client and
the pipelining are exercised without Docker.

---

## Validation target

Before any LLM number means anything, the harness has to reproduce SWIM's own
reactive baseline.

| config | run | flags | utility |
|---|---|---|---|
| `Reactive` | 6 | `--seed-set=1` | **2647** |
| `Reactive2` | 6 | `--seed-set=1` | **1740** |

Run 6 is ClarkNet with a 60 s boot delay. `--seed-set=1` is essential and is
documented nowhere upstream — OMNeT++ defaults the seed-set to the run number,
and without the flag you get 2250, which looks plausible and is wrong.

`simulations/swim_sa/swim_sa.ini` is parameter-identical to `simulations/swim/swim.ini`
(verified: same traces, iteration order, `sim-time-limit`, `warmup-period`,
`evaluationPeriod`, `numberOfBrownoutLevels`, `dimmerMargin`,
`responseTimeThreshold`, `maxServers`, `initialServers`, service times,
`bootDelay` grid, `maxServiceRate`). It differs only in the network name, the
result directory, the two `[Config Reactive*]` sections, and the absence of
`cSocketRTScheduler` — which is why the baselines complete in seconds while an
externally-controlled run takes 105 minutes. The comparison is like-for-like.

---

## Things about SWIM that are easy to get wrong

All verified against the simulator source, not inferred.

**`set_dimmer` speaks dimmer, not brownout.** `AdaptInterface::cmdSetDimmer`
calls `setBrownout(1 - dimmer)`, and `cmdGetDimmer` returns `1 - brownoutFactor`.
The internal `SetDimmerTactic` uses the same units, so a value sent over TCP
means exactly what it means to SWIM's own controller.

**The dimmer step is 0.25, clamped to [0, 1].**
`ReactiveAdaptationManager::evaluate` uses `dimmerStep = 1.0/(numberOfDimmerLevels-1)`
= 1/4. This is *not* the same grid as `Model::brownoutLevelToFactor`, which maps
the five discrete levels to `{0.1, 0.3, 0.5, 0.7, 0.9}` and is used by the
**utility scorer**, not by the controller. The practical consequence is that
several distinct dimmer values score identically.

**`spareUtilization` is a sum, not a mean.** `SimProbe::getUpdatedObservations`
accumulates `obs.utilization += ...` across servers — commented "get total
utilization" in `HAProxyProbe.cc`. So `spare = activeServers - total_utilization`
reads as "spare server-equivalents". Dividing by the server count first makes
`spare > 1` almost always true and silently breaks the reactive baseline.

**There is no `get_response_time`.** Response time is reported per service class
and must be recombined throughput-weighted:
`(basic_rt*basic_tp + opt_rt*opt_tp) / (basic_tp + opt_tp)`, exactly as SWIM's
own probe does.

**The threshold comparison is strict on both sides.** `if (rt > T) … else if (rt < T) …`,
so a response time exactly on the threshold produces no action at all.

---

## Comparability

The default `--dimmer-mode levels` gives the LLM five absolute dimmer settings —
one per distinguishable utility level — which is a **strictly larger action
space** than the reactive baseline's ±1 step. A difference in outcome would then
be attributable to the action space rather than to the decision rule.

Run both arms: `--dimmer-mode step` is directly comparable to the baseline, and
`levels` shows what the extra freedom buys.

---

## Not done yet

- Activation capture at the probe positions — the offsets are emitted, nothing
  consumes them. That belongs on the model side, in [`../NLA`](../NLA).
- Result collection: nothing copies SWIM's `.sca`/`.vec` out of the container, so
  there is no path from a run to a utility number yet. `stop_swim.sh --rm`
  destroys them.
- Repeats. Run-to-run spread on an unchanged configuration is ~21% (eight runs
  spanning 4423–5576, sd 348), so with n=1 nothing below roughly a 20% effect is
  measurable. Budget ≥5 runs per condition, or shorten `sim-time-limit` while
  iterating.
