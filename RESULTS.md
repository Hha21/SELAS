# Results

The record of what has been measured, where it lives, and how to regenerate it.
Written so the poster and paper can be assembled from this file alone.

**Status (2026-09-24).** Performance on SWIM's published configuration is
**done** (section 2). The interpretability measurements are being re-run on
those same runs (section 3). Everything in
[Earlier results](#earlier-results-superseded-configuration) comes from a
reduced configuration and is kept for the record, not for the poster.

---

## 1. Setup (fixed)

| | |
|---|---|
| Managed system | SWIM, socket-controlled network, real time |
| Configuration | SWIM's published one, unchanged: **ClarkNet** trace (run index 8), `maxServers = 12`, `initialServers = 3`, `bootDelay = 180 s`, `numberOfBrownoutLevels = 10`, one decision every 60 s, 6300 s per run of which the first 900 s are unscored warm-up (90 scored periods) |
| Seeds | **seed-set 0** for the figure — the seed of SWIM's shipped PLA and Thallium runs, so every controller faces the same random draws; seed-sets 1–2 added for spread |
| Model | `google/gemma-3-27b-it` via vLLM on one H200, temperature 0, chat format |
| Action space | `add_server`, `remove_server`, `no_op`, `set_dimmer {0, 0.25, 0.5, 0.75, 1}` |
| Utility | **SWIM's reported utility**, `periodUtilitySEAMS2017A` from `SWIM/tools/plotResults.R` (the function in Moreno et al., SEAMS 2017), computed by `experiments/controller_comparison/swim_utility.py` |
| Late period | a scored period whose utility is negative, which under this function is exactly a period whose mean response time exceeds 0.75 s |

**The two prompts.** Both give the constraints, the action legend, two worked
exemplars and the current state with a 5-period history. They differ only in
how the objective is stated:

- **Prompt A** (`llm` arm): the utility's strict priority order in words —
  keep the SLA; then serve as much optional content as possible; only once the
  dimmer is at 1, run as few servers as possible.
- **Prompt B** (`formula` arm): the utility function itself with its constants,
  and each period's utility shown in the state and history. The shown values
  are the controller's own estimate from what it observes (it cannot see SWIM's
  recorded vectors mid-run); against SWIM's official per-period figure it agrees
  on breach / no breach in 88 of 89 periods, mean absolute difference 13.

---

## 2. Performance — done

**Figure:** `~/selas-results/published-figure/comparison.png` (and `.pdf`) on CSF.
Four panels over time: servers, dimmer, response time, cumulative utility. All
controllers at seed-set 0.

**Regenerate:** `experiments/controller_comparison/published_figure.sh` on CSF,
once these exist:

| run | produced by | results directory on CSF |
|---|---|---|
| LLM, prompts A and B, seed-sets 0–2 | job 21302436, `submit_comparison.sh --classic --trace clarknet --arms "llm@0 llm@1 llm@2 formula@0 formula@1 formula@2" --tag published-clarknet` | `~/selas-results/published-clarknet-*` |
| do nothing, seed-set 0 | job 21302437, `run_baseline.sbatch` with `SELAS_POLICY=null SELAS_RUN_INDEX=8 SELAS_SEED_SET=0 SELAS_INITIAL_SERVERS=3 SELAS_MAX_SERVERS=12 SELAS_BROWNOUT_LEVELS=10` | `~/selas-results/published-null-*` |
| SWIM's built-in reactive managers, 10 seeds | `sbatch experiments/builtin_baselines/run_builtin.sbatch` (run list pre-committed in `runs.txt`) | `~/selas-results/builtin-20260923-215441` |
| PLA, Thallium | SWIM's shipped results, `SWIM/tools/THALLIUM/{pladapt,thallium}-0.{sca,vec}` | in the repo |

**Numbers already fixed** (SWIM's reported utility, ClarkNet, published configuration):

| controller | utility | late periods | note |
|---|---|---|---|
| Thallium | 4658.65 | 0 | shipped result, seed-set 0; holds 2 servers at dimmer 0.46 for the whole scored run |
| PLA | 4089.09 | 0 | shipped result, seed-set 0; dimmer mostly 0.12–0.24 |
| SWIM `Reactive`, seed-set 0 | −865.28 | 27 | our run; identical to SWIM's shipped reactive result |
| SWIM `Reactive`, seeds 1–10 | −2619 ± 974 | ~30 of 90 | mean ± sample SD |
| SWIM `Reactive2`, seeds 1–10 | −7436 ± 1026 | ~39 of 90 | |

**Results** (runs `published-clarknet-20260924-141546`, `published-null-20260924-141546`):

| controller | SWIM reported utility (SEAMS 2017A) | late periods (of 90) | older utility (ICAC 2016) |
|---|---|---|---|
| **LLM, prompt B**, seeds 0–2 | **10562 ± 754** (11028, 10965, 9693) | 3.3 | 4248 (4465, 4355, 3923) |
| do nothing, seed 0 | 5101 | 1 | 5102 |
| Thallium (shipped) | 4659 | 0 | 4665 |
| PLA (shipped) | 4089 | 0 | 4087 |
| SWIM `Reactive`, seed 0 | −865 | 27 | −5284 |
| SWIM `Reactive`, seeds 1–10 | −2619 ± 974 | 30 | |
| LLM, prompt A, seeds 0–2 | −6018 ± 1151 (−7119, −4822, −6112) | 35 | −8730 |

At seed-set 0: prompt B keeps the dimmer at 1.0 (mean 0.98) and scales up to
4 then 6 servers ahead of load (mean 4.28); prompt A repeatedly drops to one
server and cuts the dimmer, breaching in 38 periods.

**How to state it.** Under SWIM's reported utility, prompt B is well ahead of
the published planners. Part of that gap is that prompt B was *told* this
function, whose server-cost bonus is paid only at dimmer 1; under the older
function it is comparable to them (between PLA and Thallium), and doing nothing
beats every controller. The shipped files do not record which objective PLA and
Thallium were set to optimise, and PLA's low dimmer (0.12–0.24) fits neither
function's revenue term well, so both functions are reported rather than
assuming either is "theirs". The sharpest contrast is A vs B: the same model,
given the same objective as a priority order in words rather than as a
function with per-period feedback, goes from the best controller to the worst.

---

## 3. Interpretability — *to be run on the runs above*

**Regenerate:** once job 21302436 has finished,

```
SELAS_RUN=published-clarknet-<timestamp> SELAS_ARMS="llm-s0 formula-s0" \
    sbatch -A "$CSF_ACCOUNT" experiments/replay/replay_all.sbatch
python3 experiments/spider/spider.py <run>/llm-s0 <run>/formula-s0 \
    --labels "prompt A" "prompt B" -o <run>/spider
```

`replay_all.sbatch` runs, for each arm, the intervention battery (faithfulness),
the counterfactual edits in both modes, and simulatability with three readers,
concurrently against one served model (about 45 minutes).

**The five axes** (all on ACTIVE decisions, 1 = interpretable end):

| axis | measured as | source |
|---|---|---|
| Robustness | 1 − action flip rate when the reasoning is paraphrased | Lanham et al. 2023 |
| Sensitivity | flip rate when the reasoning is removed entirely | Lanham et al. 2023 |
| Mistakes | flip rate when the SLA premise is negated, read against the same prompt with the conclusion already removed | Lanham et al. 2023 |
| Counterfactual | flip rate between opposing telemetry edits (SLA breached vs met, load high vs low, capacity saturated vs idle), reasoning regenerated | Yeo et al. 2024 |
| Simulatability | how much a second model's prediction of the action improves when given the reasoning's premises, rescaled to [0, 1] | Hase et al. 2020 |

Deviations from the source protocol, all declared: the simulator is prompted
rather than fine-tuned; the leakage-adjusted split is replaced by an accuracy
decomposition because the reasoning leaks the answer in ~97% of decisions;
everything is read on ACTIVE decisions because `no_op` survives any
perturbation. Counterfactual edits are exact substitutions into structured
telemetry rather than rewrites by another model.

---

## 4. Validation (for the methods section)

- **Built-in reactive reproduces SWIM's published result exactly.**
  `SWIM_SA -c Reactive -r 8 --seed-set=0` at the published configuration gives
  `utility:last = -5254.019030`, equal to the shipped `-5254.019030358571`.
- **The utility port is exact.** `swim_utility.py` gives the same SEAMS 2017A
  and ICAC 2016 totals as SWIM's own `plotResults.R`
  (`experiments/controller_comparison/swim_utility_reference.R`, R 4.4.2 on CSF)
  on nine files: the three shipped runs, three built-in runs and three runs of
  our controller harness.
- **Six concurrent simulations on 8 cores keep real time.** A reactive run
  reproduced its cumulative utility bit-for-bit against a 16-core run at every
  overlapping timestamp.
- **The prompt matches the simulation.** The pool size is read from SWIM; the
  boot delay is passed in and checked afterwards against the value SWIM
  recorded (`bootDelay check` line in each job log).

---

## 5. Observations about SWIM worth stating

- **The utility function matters.** SWIM's simulator records the ICAC 2016
  function (`utility:last`), which has no server cost; SWIM's reporting uses
  SEAMS 2017A, which adds `10 × (maxServers − servers)` per period, paid only
  when the dimmer is at 1. Under the first, holding the initial state is
  near-optimal because extra servers are free and the dimmer starts at the
  highest level that function scores.
- **Starting state decides a lot.** From 3 servers on ClarkNet a controller that
  barely acts is competitive with the published planners (the no-reasoning LLM
  took `no_op` 102/105 times and scored 5502 in an earlier run); from 1 server,
  doing nothing scores −24641. SWIM's reactive manager is path-dependent: on
  WorldCup it reaches dimmer 1 in 70/91 periods from 3 servers and 16/91 from
  1, because its `spare > 1` guard cannot fire on a single server.
- **Thallium's shipped run never adapts after warm-up**: 91 decisions, 2 servers
  and dimmer 0.46 throughout, and it outscores PLA.

---

## Earlier results (superseded configuration)

Measured on a reduced configuration — 3 servers maximum, 60 s boots, 5 dimmer
levels, starting from 1 server — with the simulator's ICAC 2016 utility and an
earlier prompt. Not comparable with the sections above. Kept because they
motivated the design and because the mechanism findings are expected to carry
over; the poster should use the re-run versions from section 3.

Run `cmp-20260921-163753` (temperature 0.7, 105 decisions, 20 ACTIVE):

- Spider axes: Robustness 0.950, Sensitivity 0.850, Mistakes 0.105,
  Counterfactual 0.657, Simulatability 0.700.
- **The reasoning is the causal channel.** Editing the telemetry with the
  written reasoning held fixed changed the command in 0.3% of decisions;
  regenerating the reasoning from the edited telemetry changed it in 65.7%.
- **Only the conclusion is load-bearing.** Removing the reasoning flips 85% of
  active decisions; negating the SLA premise, with the conclusion removed,
  flips 10.5%.
- **Fields are reported but not acted on.** Echo rate (regenerated reasoning
  reports a substituted value) 91.4%; command changes per field: response time
  94.3%, arrival rate 71.4%, spare capacity 31.4%.
- **The explanation transfers to other readers.** State alone lets a second
  model recover 15% of active decisions; state plus reasoning 85%; premises
  without the conclusion 50%. Simulatability 0.675 (gemma-3-12b), 0.725
  (Qwen2.5-14B), ceiling 0.750 (the controller itself).

Prompting sweep `sweep-20260922-161524` (temperature 0): free-form reasoning is
*less* faithful to its premises than the scaffold (Mistakes 0.077 vs 0.278), so
the conclusion-only finding is not an artefact of the scaffold; without
exemplars the model stops quoting its telemetry (echo 40%) and loses 20% of
utility.

Pilots on the published pool starting from **1** server (ClarkNet, prompt A)
breached in 35–50% of periods (utility −6031, −9223, −7663); the same setup
with the earlier prompt and dimmer capped at 0.9 scored 3184 and 5382. This is
what led to the objective being stated as a formula in prompt B, and to
running from SWIM's published start.

## Where results live on CSF

`~/selas-results/<run-id>/`, one directory per job, each with `runs.json`
(from `collect.py`), per-arm subdirectories holding SWIM's `.sca`/`.vec`, the
controller's `decisions.jsonl`, and logs. Job logs are in
`~/SELAS/experiments/*/logs/`. Figures can be copied off with
`scp <user>@<host>:selas-results/<run-id>/<file>.png .`
