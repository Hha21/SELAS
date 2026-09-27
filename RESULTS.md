# Results

The record of what has been measured, where it lives, and how to regenerate it.
Written so the poster and paper can be assembled from this file alone.

**Status (2026-09-26).** Performance of prompts A and B (section 2), the
prompt built up one component at a time (section 2b, three seeds) and the same
three prompts across four more models (section 2c, three seeds each) on SWIM's
published configuration are **done**. The interpretability numbers (section 3)
were measured before the audit fixes and the prompt fixes and are to be
re-measured; use them as placeholders. Figures are in
`~/selas-results/published-figure/`,
`~/selas-results/published-clarknet-20260924-141546/` and
`~/selas-results/prompts-clarknet-*` on CSF, with local copies under
`figures/` (gitignored). Everything in
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

**Where the scores come from.** SWIM's reported utility split into its three
parts (`swim_utility.utility(...)["components"]`; the parts sum exactly to the
total):

| controller | total | revenue | cost bonus | penalty | periods at dimmer 1 | late | mean servers |
|---|---|---|---|---|---|---|---|
| prompt B, seed 0 | 11028 | 5402 | 6562 | −936 | 85/90 | 3 | 4.28 |
| prompt B, seed 1 | 10965 | 5281 | 6611 | −926 | 80/90 | 3 | 3.87 |
| prompt B, seed 2 | 9693 | 5161 | 5771 | −1240 | 78/90 | 4 | 4.80 |
| do nothing | 5101 | 5398 | 0 | −297 | 0/90 | 1 | 3.00 |
| Thallium | 4659 | 4659 | 0 | 0 | 0/90 | 0 | 2.00 |
| PLA | 4089 | 4089 | 0 | 0 | 0/90 | 0 | 2.80 |
| SWIM reactive | −865 | 3727 | 4420 | −9012 | 47/90 | 27 | 2.71 |
| prompt A, seed 0 | −7119 | 2975 | 2779 | −12873 | 30/90 | 38 | 2.60 |

On revenue alone prompt B equals doing nothing and slightly exceeds the
planners. Its whole lead is the cost bonus, `10 × (12 − servers)` per period,
paid only at dimmer 1 — which PLA, Thallium and doing nothing never reach, and
which SWIM's reactive manager collects and then loses to breaches. A planner
aiming at this function could exceed prompt B (dimmer 1 on ~2.8 servers without
breaching would be ~14,000), so the result is **not** "the LLM beats the
planners"; it is that the LLM, told the function, finds the strategy it rewards
and holds it with few breaches, and told the same objective in words, does not.

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
Section 2b separates the two differences: it is the words that break it.

---

## 2b. What in the prompt matters — done (2026-09-26)

The prompt built up one component at a time, on the fixed base (exemplars
rendered for the 12-server pool, utilisation shown as a mean, reasoning fields
named in the system prompt; PLAN.md step 2). Configuration as in section 1,
seed-sets 0–2, SWIM's reported utility. All arms: scaffolded reasoning, 200
tokens, temperature 0.

**Figure:** `figures/prompts-clarknet/ladder_utility.pdf` — utility per
configuration, one dot per seed, baselines as lines. Behaviour over time for
seed 0 (servers, dimmer, response time, cumulative utility):
`figures/prompts-clarknet-s0/ladder_s0.pdf`.

| arm | exemplars | objective | feedback | utility, mean ± SD (seeds 0, 1, 2) | late periods | mean servers | mean dimmer | actions of 105 |
|---|---|---|---|---|---|---|---|---|
| `k0` | 0 | none | off | 4038 ± 71 (4021, 3977, 4116) | 0, 0, 0 | 3.29 | 0.14 | 29, 34, 29 |
| `k2` | 2 | none | off | 11020 ± 390 (10605, 11378, 11078) | 2, 2, 2 | 3.99 | 0.92 | 19, 10, 13 |
| `k2-words` (= A) | 2 | words | off | **−6208 ± 1694** (−4364, −7695, −6563) | 27, 34, 33 | 2.31 | 0.70 | 80, 82, 80 |
| `k2-formula` | 2 | formula | off | **11864 ± 342** (11862, 11522, 12207) | 1, 1, 2 | 3.98 | 0.98 | 15, 16, 16 |
| `k2-words-fb` | 2 | words | on | −7699 ± 1088 (−6867, −8930, −7301) | 33, 39, 35 | 2.31 | 0.72 | 81, 85, 73 |
| `k2-formula-fb` (= B) | 2 | formula | on | 11397 ± 970 (10926, 12512, 10752) | 3, 1, 2 | 3.77 | 0.96 | 11, 9, 9 |

Baselines as in section 2: do nothing 5101, Thallium 4659, PLA 4089, SWIM
reactive −865.

**What it shows.**

1. **Stating the objective in words is worse than not stating it.** Every
   seed of both words arms is below −4300; every seed of every other arm with
   exemplars is above 10,500. Words against no objective: −17,228.
2. **Mechanism** (from the reasoning, seed 0): the model applies the third
   priority literally — "now that the dimmer is at its maximum, we should try
   to reduce the number of servers" — removing servers even at 71% utilisation
   and 55 req/s, breaching, adding them back, and repeating: 80 of 105
   decisions are actions, against 9–19 for the other exemplar arms. Mean pool
   2.3 servers, below the 3 it started with.
3. **The formula helps a little over no objective:** +844, higher on every
   seed (by seed: +1257, +144, +1129).
4. **Showing each period's utility makes no clear difference** (formula −467,
   words −1491; both within the seed spread).
5. **Exemplars matter:** without them the model keeps the dimmer near 0.14 —
   never late, but below doing nothing (4038 vs 5101).
6. **Consistent with section 2:** `k2-words` reproduces prompt A (−6208 vs
   −6018) and `k2-formula-fb` prompt B (11397 vs 10562) on the fixed prompt.

**How to state it.** Told the objective as a priority order in words, the
controller scores below doing nothing, below SWIM's reactive manager and below
every other prompt; told nothing about the objective, or told it as the
utility function, it scores more than twice what doing nothing does. (SWIM's
second reactive manager, −7436 ± 1026, is the one controller in section 2
below the words prompt.) The words are
not wrong — they are the order SWIM's utility encodes — but without magnitudes
"run as few servers as you can" outweighs the SLA it is conditioned on.

**Validation.** Every run passed the integration check, run by the job itself
(`integration_check.json` in each run directory): each command sent became
exactly one change of the right value in SWIM's vectors, no change lacks a
command, and each observation matches SWIM's recorded state.

**Provenance and regeneration.**

| seed-set | job | command (in `experiments/controller_comparison/`) | results on CSF |
|---|---|---|---|
| 0 | 21366743 | `submit_comparison.sh --classic --trace clarknet --arms "k0@0 k2@0 k2-words@0 k2-formula@0 k2-words-fb@0 k2-formula-fb@0" --tag prompts-clarknet` | `~/selas-results/prompts-clarknet-20260925-220652` |
| 1 | 21387073 | the same with `@1`, `--tag prompts-clarknet-s1` | `~/selas-results/prompts-clarknet-s1-20260926-130655` |
| 2 | 21387074 | the same with `@2`, `--tag prompts-clarknet-s2` | `~/selas-results/prompts-clarknet-s2-20260926-130657` |

Jobs 21384049/21384050 (an earlier attempt at seeds 1–2) shared ports on one
node and cross-wired their runs; they are set aside in
`~/selas-results/invalid-port-collision/` and must not be used.

```
python experiments/controller_comparison/ladder_plot.py \
    <the three runs.json> -o figures/prompts-clarknet/ladder_utility \
    --arm "k0=no examples, no objective" --arm "k2=2 examples, no objective" \
    --arm "k2-words=+ objective in words (A)" --arm "k2-formula=+ objective as utility formula" \
    --arm "k2-words-fb=+ words + utility feedback" --arm "k2-formula-fb=+ formula + utility feedback (B)" \
    --reference "do nothing=5101" --reference "Thallium=4659" --reference "PLA=4089" \
    --reference "SWIM reactive=-865" \
    --title "Utility by prompt: SWIM ClarkNet, published configuration, 3 seeds"
```

---

## 2c. Across models — done (2026-09-26)

Is the words collapse a quirk of gemma-3-27b? The three prompts that carry it
— `k2` (no objective), `k2-words`, `k2-formula` — on four models through
OpenRouter, seed-sets 0–2 each, same configuration as section 1.

**Figure:** `figures/models/models_utility.pdf` — one row per prompt, one colour
per model, a dot per seed; CSF gemma (section 2b) included for reference.

| model (provider) | no objective | **objective in words** | utility formula |
|---|---|---|---|
| gemma-3-27b, CSF vLLM (section 2b + seed 3) | 11281 ± 612 (n=4) | **−6754 ± 1762** | 11935 ± 313 |
| Llama-3.3-70B-Instruct FP8, CSF vLLM | 9184 ± 3547 (12524, 11620, 4886, 7705) | **1310 ± 1781** (1303, 289, 3818, −170) | 11227 ± 2515 (13257, 11546, 12500, 7604) |
| gemma-3-27b (Parasail) | 10229 ± 2152 (12177, 10591, 7919) | **−6674 ± 845** (−6262, −6113, −7646) | 11472 ± 187 (11651, 11487, 11277) |
| gpt-4o-mini (OpenAI) | 6570 ± 1265 (7280, 7321, 5110) | **−5234 ± 493** (−4908, −4992, −5801) | 9083 ± 612 (9120, 8454, 9677) |
| Llama-4-Maverick (Parasail) | 1807 ± 1290 (3144, 570, 1708) | **−5544 ± 768** (−5532, −6318, −4782) | 1771 ± 3980 (2118, −2371, 5566) |
| Qwen3-235B-A22B-Instruct-2507 (GMICloud) | 1982 ± 1942 (1023, 4217, 706) | **−6323 ± 743** (−6946, −6522, −5501) | 3256 ± 1973 (5229, 3256, 1283) |

Late periods of 90 (seeds 0, 1, 2), and mean servers:

| model | no objective | words | formula |
|---|---|---|---|
| gemma-3-27b (OR) | 1, 2, 1 — 3.67 | **32, 30, 34 — 2.31** | 2, 2, 3 — 3.98 |
| gpt-4o-mini | 2, 0, 4 — 4.32 | **37, 38, 39 — 2.82** | 1, 0, 1 — 4.17 |
| Llama-4-Maverick | 8, 17, 13 — 2.48 | **37, 34, 34 — 2.60** | 17, 21, 8 — 2.70 |
| Qwen3-235B | 20, 15, 23 — 2.70 | **38, 38, 36 — 2.53** | 16, 19, 22 — 2.81 |

**What it shows.**

1. **The objective in words is the worst prompt for every model, on every
   seed**, and never close: for each model the best words run is below the
   worst run of either other prompt. Words runs are late in 30–39 of 90
   periods for every OpenRouter model and 20–27 for Llama-3.3-70B (0–2 for its
   other prompts); Llama-3.3-70B is the one model whose words runs stay
   positive (1310), still ~8000 below its other two prompts.
2. **Not a gemma quirk, and not an infrastructure one:** gemma through
   OpenRouter reproduces gemma on CSF within the seed spread (10229 / −6674 /
   11472 against 11020 / −6208 / 11864).
3. **The same mechanism in every model: removing servers while on time, then
   breaching.** Server removals made while the SLA was met, and the share
   followed by a breach within three periods (all three seeds, scored window):

   | model | no objective | words | formula |
   |---|---|---|---|
   | gemma-3-27b (OR) | 1 (0%) | **31 (97%)** | 8 (0%) |
   | gpt-4o-mini | 3 (0%) | **51 (82%)** | 15 (13%) |
   | Llama-4-Maverick | 23 (48%) | **39 (87%)** | 22 (59%) |
   | Qwen3-235B | 25 (60%) | **35 (83%)** | 32 (56%) |

   gemma and gpt-4o-mini also run smaller pools under the words (2.3 and 2.8
   servers against 3.7–4.3); Llama-4 and Qwen3 add the servers back, so their
   mean pool barely moves, but each removal costs the 180 s boot in late
   periods. Qwen3, words, seed 0, period 39: "response time exploded after
   removing a server (period 37) while dimmer was set to 1.0". (The breach
   share is partly the words runs' higher base rate of late periods; the
   removal counts are the direct evidence.)
4. **Formula against no objective depends on the model:** +1243 (gemma OR),
   +2513 (gpt-4o-mini), about 0 (Llama-4), +1274 (Qwen3), with large spread for
   the weaker two. The robust contrast is words against either of the others.
5. **Model competence differs a lot:** Llama-4 and Qwen3 score below doing
   nothing even without an objective. The claim is about the prompt's effect
   within a model, not about which model controls best.

**How decisions are made here, and why it differs from CSF.** CSF reads the
letter's probability by prefilling the assistant turn with the model's
reasoning and "Action:" and having vLLM *continue* it. No OpenRouter provider
continues a prefilled turn (prefilled "The capital of France is Pa", every one
answered "The capital of…", none "ris"; gemma, Llama 3.3/4, Qwen3 on three
providers, gpt-4o-mini). So here (`--decide generate`) the model writes its
reasoning and "Action: <letter>" itself, and the top-20 logprobs *at the token
where it writes the letter* give the distribution over letters — the same
position the CSF call reads, produced by the model. The decision renormalises
over the legal letters and takes the most likely, as on CSF. Every one of the
36 decisions logs says `generate+logprobs`; no decision fell back to the
reactive rule; illegal first choices (masked to the best legal letter) were
0–18 per run, most for gpt-4o-mini (33–41 per words run: it names "set the
dimmer to 0.5" while at 0.5). Providers pinned per model; temperature 0;
reasoning capped at 200 tokens (+24 for the action line).

Two earlier seed-0 passes used other decision rules and agree on the ordering
(words lowest for every model): reading the first token of a fresh reply after
the reasoning — gemma 7845 / −4403 / 9253, gpt-4o-mini 4977 / −7430 / 8064,
Llama-4 7907 / −3211 / 5031 (Qwen3 unusable: its fresh reply restarts the
reasoning); and the written letter without logprobs — gemma 11171 / 74 / 11466,
gpt-4o-mini 7620 / −3252 / 7964, Llama-4 1284 / −3842 / 6580, Qwen3 4890 /
−2626 / −538. (No objective / words / formula.)

**Validation.** SWIM ran locally from the `gabrielmoreno/swim` Docker image
(the image CSF's `swim.sif` was built from; its `swim.ini` equals the
repository's) with the published configuration. Doing nothing locally scores
5101.2 with 1 late period, as on CSF (5101, 1). All 36 runs pass the
integration check (commands ↔ recorded changes, observations ↔ recorded
state); the checker now dates observations net of each decision's latency
(the clock offset is 0.92–0.96 s on every local run).

**Provenance.** On the laptop, gitignored: `results-local/gl-gemma27b-20260926-191134`,
`gl-gpt4omini-20260926-191219`, `gl-llama4-maverick-20260926-191304`,
`gl-qwen3-235b-20260926-191349` (each with `runs.json`, per-run decisions,
SWIM vectors and `integration_check.json`); validation run
`results-local/local-null-20260926-163341`. Produced by

```
experiments/controller_comparison/run_local.sh --model <model> --provider <provider> \
    --decide generate --arms "k2@0 k2-words@0 k2-formula@0 k2@1 k2-words@1 k2-formula@1 k2@2 k2-words@2 k2-formula@2" \
    --tag gl-<name> --port-base <port>
```

with the OpenRouter key in `~/.config/selas/openrouter.env`. Figure:
`experiments/controller_comparison/models_plot.py` (command in its docstring).

**Random baseline** (uniform over the legal options, the same action space;
`--policy random`, seeded by the seed-set), seed-sets 0–9: 2931, 5046, −15705,
−1703, −352, −3097, 4842, 5278, 118, 3191 — **mean 55 ± 6278, median 1524**
(late periods 5, 1, 52, 17, 13, 20, 0, 0, 12, 5). Its spread is the random walk
of the server count: seed 2 drifted to 1.7 servers on average. The words runs
of five of the six models (means −5234 to −6754) are below both the random
mean and median; Llama-3.3-70B's (1310) is near the random median. All ten
pass the integration check; seeds 3–9 in
`results-local/local-random-s3to9-20260926-225032`. CSF runs: jobs 21392112–4,
`~/selas-results/published-random-s{0,1,2}-20260926-161650`.

**Local and CSF are the same simulation.** The random runs made on CSF and on
the laptop took the identical 105-action sequence for each seed, and their
utilities agree to 0.05 in thousands (2930.85 / 2930.80, 5045.73 / 5045.66,
−15704.67 / −15704.69) — the remainder is sub-second timing of when commands
land.

**CSF provenance:** Llama-3.3-70B jobs 21392438 (seeds 0–1) and 21392444
(seeds 2–3), `~/selas-results/llama70b-prompts-s{01,23}-20260926-*`; gemma
seed 3 in job 21392449, `~/selas-results/words-apart-s2-main-s3-20260926-162446`.
All 24 runs pass the integration check (21392444 was marked FAILED only because
the checker then on CSF could not date a run with no dimmer change; the current
one passes it).

---

## 2d. Which part of the words breaks it — done (2026-09-27)

The objective in words has three rules; the variants change one thing each
(`controller/context.py`, arms `k2-words-*`). gemma-3-27b on CSF (vLLM
scoring), seed-sets 0–2, published configuration.

**Figure:** `figures/prompts-clarknet/words_apart.pdf`.

| prompt | utility (seeds 0, 1, 2) | late periods | mean servers |
|---|---|---|---|
| no objective (`k2`, n=4) | 11281 ± 612 | 2, 2, 2, 1 | 3.9 |
| words, rules 1–3 (`k2-words`, n=4) | **−6754 ± 1762** | 27, 34, 33, 36 | 2.3 |
| same rules reworded (`k2-words-para`) | −4863 ± 2318 (−2878, −4299, −7410) | 27, 30, 38 | 2.53 |
| rules 1–3 + a line of scale (`k2-words-scaled`) | −6426 ± 1293 (−6078, −5342, −7857) | 33, 32, 36 | 2.49 |
| **rules 1–2 only (`k2-words-no3`)** | **11783 ± 620** (11902, 11112, 12335) | 2, 2, 1 | 3.67 |
| utility formula (`k2-formula`, n=4) | 11935 ± 313 | 1, 1, 2, 1 | 4.0 |

**What it shows.** Rule 3 — "only once the dimmer is at 1.0, run as few
servers as you can" — is the whole effect: removing it restores the
controller to the formula's level (11783 against 11935). It is not the
phrasing (reworded, it still collapses) and not missing magnitudes (told that a
late period costs as much as 40 periods of an extra server, it collapses just
the same). The model is not short of the information; it acts on the
instruction.

The words variants were run on CSF, jobs 21392445 (seeds 0–1) and 21392449
(seed 2), `~/selas-results/words-apart-*-20260926-*`; all pass the integration
check. The same variants are running locally on gemma and gpt-4o-mini through
OpenRouter (`results-local/wv-*`).

---

## 3a. Does the objective act through the reasoning? (mediation) — done (2026-09-27)

`experiments/mediation/`. For every recorded decision, only the objective in
the system prompt is swapped — rule 3 removed from a words run, or added to a
run that never had it — with the state fixed, and four distributions are
scored (vLLM continuation, gemma-3-27b):

- **orig** — the recorded prompt and reasoning (control)
- **direct** — swapped objective, the ORIGINAL reasoning kept
- **total** — swapped objective, reasoning regenerated under it (greedy, 200 tokens)
- **reason** — original objective, the regenerated reasoning

Control reproduces the recorded decision in 99–100% of decisions.
Distributions are masked to the legal actions as the controller does.

| run | decisions total changes | of those, direct changes the same way | reason does | TV from orig: direct / total / reason | P(remove): orig → direct → total |
|---|---|---|---|---|---|
| words s0, rule 3 removed | 51 / 105 | 8% | 76% | 0.12 / 0.50 / 0.46 | 0.11 → 0.13 → 0.00 |
| words s1 | 53 | 17% | 72% | 0.15 / 0.51 / 0.45 | 0.13 → 0.13 → 0.00 |
| words s2 | 58 | 16% | 81% | 0.15 / 0.55 / 0.49 | 0.15 → 0.15 → 0.00 |
| words s3 | 60 | 20% | 80% | 0.16 / 0.56 / 0.51 | 0.14 → 0.14 → 0.01 |
| no-rule-3 s0, rule 3 added | 84 | 2% | 98% | 0.04 / 0.81 / 0.79 | 0.02 → 0.02 → 0.79 |
| no-rule-3 s1 | 87 | 3% | 98% | 0.04 / 0.83 / 0.81 | 0.01 → 0.01 → 0.75 |
| no-rule-3 s2 | 97 | 2% | 97% | 0.03 / 0.92 / 0.90 | 0.00 → 0.00 → 0.87 |

**What it shows.** The objective's effect on the decision passes almost
entirely through the written reasoning. Held to its original reasoning, the
model keeps every recorded removal after rule 3 is deleted (P(remove) over the
removal decisions stays 1.0; it drops to 0 only when the reasoning is
regenerated), and adding rule 3 barely moves a decision (2–3% of the flips,
TV 0.03–0.04) unless the model re-reasons — when it would remove a server in
75–87% of periods. The rule changes what the model writes; the decision
follows what it wrote. For this failure the trace is not only visible but
causal. (The residual direct path is larger for words → no rule 3, 8–20% of
flips, than the reverse, 2–3%.)

Caveat: single-step, at recorded states; the closed-loop consequence is the
utility result of section 2d.

**Provenance:** job 21402011 (`experiments/mediation/run_mediation.sbatch`,
specs in PLAN.md), outputs `~/selas-results/<run>/<arm>/mediation_<to>.jsonl`
and `.json` for `k2-words-s{0,1,2,3}` (priority → priority-no3) and
`k2-words-no3-s{0,1,2}` (priority-no3 → priority).

---

## 3. Interpretability — re-measured on the fixed code (preliminary, 2026-09-27)

The full battery (`replay_all.sbatch`, audit fixes F1–F4 in) on the section 2b
runs, gemma-3-27b, over all decisions, seed-sets 0–2 (jobs 21401939–41;
`~/selas-results/interp-prompts/spider_prelim.{png,json}`, local copy
`figures/interp/`). The runs without rule 3 and seed 3 are in jobs 21401942–3.

| axis | no objective | **words** | formula |
|---|---|---|---|
| Robustness (paraphrase leaves it) | 0.994 | 0.937 | 0.981 |
| Sensitivity (ablating the reasoning moves it) | 0.114 | **0.483** | 0.130 |
| Mistakes (corrupted premise, conclusion dropped) | 0.102 | **0.222** | 0.054 |
| Counterfactual (flip rate under paired telemetry edits) | 0.851 | **0.596** | 0.877 |
| Simulatability | 0.391 | **0.541** | 0.437 |
| *shuffled reasoning moves it (ceiling)* | *0.197* | ***0.676*** | *0.238* |

The words controller's decisions depend on its reasoning far more, and track
its telemetry less, than either well-performing configuration's — consistent
with the mediation (§3a): its reasoning is what carries the rule to the
decision. Caution before interpreting: the good configurations choose no_op in
~75% of periods and the words one acts in ~80%, so more of its decisions can
move; the active-decisions pool (`--pool ACTIVE`) is the check.

The earlier A/B numbers below were measured before the fixes and on the old
prompt; they are superseded by the table above.

**Regenerate** (on CSF, after the performance runs exist):

```
SELAS_RUN=published-clarknet-20260924-141546 \
SELAS_ARMS="llm-s0 llm-s1 llm-s2 formula-s0 formula-s1 formula-s2" \
    sbatch -A "$CSF_ACCOUNT" experiments/replay/replay_all.sbatch
experiments/spider/interpretability_figures.sh
```

`replay_all.sbatch` replays every recorded decision of each run offline — the
exact prompt the model saw, its reasoning, its distribution over actions —
under edits, against the same served model, with no simulator: the
intervention battery (faithfulness), the counterfactual edits in both modes,
and simulatability with three reader models. All six runs concurrently.

`interpretability_figures.sh` then writes, into the run directory:

- `spider.png` — one polygon per prompt, each axis the mean over its three
  seeds, over **all decisions** (primary: holding still is a decision too);
- `spider_active.png` — the same over active decisions only (does the
  reasoning drive the action when the controller acts?);
- `pareto.png` — SWIM's reported utility against the interpretability
  aggregate, one point per run, with do nothing, SWIM's reactive manager, PLA
  and Thallium as reference lines.

**Results** (replay job 21311247; each value the mean over seed-sets 0–2):

| axis | all decisions: A | all decisions: B | active only: A | active only: B |
|---|---|---|---|---|
| Robustness | 0.949 | 0.981 | 0.917 | 0.821 |
| Sensitivity | 0.314 | **0.073** | 0.442 | **0.637** |
| Mistakes | 0.097 | 0.032 | 0.141 | 0.231 |
| Counterfactual | 0.477 | **0.740** | 0.477 | **0.740** |
| Simulatability | 0.622 | 0.487 | 0.632 | 0.596 |
| *control: original (expect 0)* | 0.003 | 0.000 | 0.005 | 0.000 |
| *control: shuffled (ceiling)* | 0.581 | **0.194** | 0.814 | 1.000 |

Per-seed values are printed by `interpretability_figures.sh`; spread across
seeds is small (e.g. B's Counterfactual 0.746 / 0.737 / 0.737). Counterfactual
is computed over all decisions in both views. Interpretability aggregate (the
Pareto x-axis): A 0.61–0.64, B 0.58–0.59.

**Reading it.**

- *Prompt B's decisions track its telemetry far better* (Counterfactual 0.74 vs
  0.48): pushed towards overload and then away from it, B sends a different
  command three times in four.
- *But over all decisions, B's written reasoning barely determines what it
  does.* Removing it changes 7% of B's decisions (A: 31%), negating its SLA
  premise 3% (A: 10%), and even substituting another period's reasoning
  entirely changes only 19% (A: 58%). B's many holds are driven by the state,
  including the utility figures it is shown, whatever its text says. A second
  model predicts B's action from its reasoning less well (0.49 vs 0.62).
- *When B does act, its reasoning matters more than A's* (Sensitivity 0.64 vs
  0.44; Mistakes 0.23 vs 0.14): the reasoning carries B's changes, not its
  holds.
- So the better controller is the one whose chain of thought is less of an
  account of its behaviour overall. That is the gap an activation-level
  explanation is meant to close, and the motivation for the NLA component.

Caveats: the all-decision axes are bounded by the shuffled ceiling, which is
only 0.19 for B, so B's low Sensitivity is partly that its decisions hardly
move under any change to the text; three seeds per prompt; one model and one
configuration. The aggregate difference between A and B is small (~0.04) next
to the utility difference, so the Pareto plot shows two clusters rather than a
trade-off curve.

**The five axes** (1 = interpretable end):

| axis | measured as | source |
|---|---|---|
| Robustness | 1 − action flip rate when the reasoning is paraphrased | Lanham et al. 2023 |
| Sensitivity | flip rate when the reasoning is removed entirely | Lanham et al. 2023 |
| Mistakes | flip rate when the SLA premise is negated, read against the same prompt with the conclusion already removed | Lanham et al. 2023 |
| Counterfactual | flip rate between opposing telemetry edits (SLA breached vs met, load high vs low, capacity saturated vs idle), reasoning regenerated | Yeo et al. 2024 |
| Simulatability | how much a second model's prediction of the action improves when given the reasoning's premises, rescaled to [0, 1] | Hase et al. 2020 |

Deviations from the source protocol, all declared: the simulator is prompted
rather than fine-tuned; the leakage-adjusted split is replaced by an accuracy
decomposition because the reasoning leaks the answer in ~97% of decisions.
Most decisions are `no_op`, which is stable under almost any edit, so the
all-decisions axes partly measure how stable the choice to hold is; the
active-only figure separates that out. Counterfactual edits are exact substitutions into structured
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
- **Cross-network check: externally driven controllers pay a one-period
  handicap after each scale-up.** Our Python port of SWIM's reactive rule, run
  over the socket at the published configuration and seed-set 0 (job 21319753,
  `~/selas-results/published-reactiveport-*`), scores −3280 against the
  built-in manager's −865 (SWIM reported utility; −6128 vs −5284 on the older
  function; 29 vs 27 late periods). The rule is the same; the difference is
  timing. Commands sent over the real-time socket land ~1.07 s after the period
  boundary, so a server booting in exactly 180 s comes online ~1 s after the
  boundary three periods later, and the controller's read at that boundary
  still sees it booting. Every decision gated on spare capacity (raising the
  dimmer, removing a server) therefore lands one period later than SWIM's
  zero-latency built-in manager, while server additions, which respond to
  response time directly, line up. This applies to every socket-driven
  controller, including the LLM (a few seconds of latency), and to none of the
  built-in managers, PLA or Thallium. Comparisons across the two networks are
  therefore conservative for the LLM, not flattering.
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
