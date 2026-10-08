# Plan

Read with [RESULTS.md](RESULTS.md), which records every measurement and where it
lives. This file says what the paper argues, what is established, and what is
next. Updated 2026-09-27 (pivot agreed with Harry).

## Where we are (2026-10-07) — read with PAPER.md and RESULTS.md

The paper's framing, decisions and open questions are in **PAPER.md**
(especially "Decisions and proposals of 2026-10-06"); measurements in
**RESULTS.md** (§A is Part A, current). Earlier plan text is in git history.

**Part A (RQ1) -- done (2026-10-07).** Eight CSF models + three OpenRouter
models, with and without the explanation, 10 runs per arm (Llama-70B CSF
finished 23:23); table in RESULTS §A, figure `figures/models/reasoning.{png,pdf}`
(static line 12891.6, do nothing 5101). To rebuild:
`final_table.py $(ls -d results-local/csf/final-*) $(ls -d results-local/fo-*-2026100[56]-* | grep -v fo-static) --json results-local/csf/final_table.json`,
then `reasoning_plot.py results-local/csf/final_table.json -o figures/models/reasoning --nothing 5101 --static 12891.6`.

**Open decision (Harry):** the prompt-decomposition factorial on gemma-3-27b
(objective {none, words 1-2, formula, words+formula} x explanation {yes, no}
x worked examples {2, 0}; 14 new cells) -- PAPER.md.

## Running: the objective ablation (PAPER.md, decision of 2026-10-08)

Arms `cot-noobj` / `direct-noobj` (run_comparison.sbatch), 10 runs each.
- CSF, 8 models: gpuA jobs 22287898-22287929 (4 per model: seeds 0-2, 3-5,
  6-7, 8-9; Llama-70B bf16 on 4 GPUs last), tags `final-<model>`.
- OpenRouter, 3 models: **done** (RESULTS §A2); local chain `results-local/launch/chain-or-20261008.sh`
  plus the round-3 re-run `chain-or-20261008b.sh`
  (resumable, markers `n*-*.done`; log `chain-or-20261008.log`; ~7 h from
  00:33 on 2026-10-08; the laptop must stay on). Result folders are named in
  UTC (`fo-*-20261007-23*` onwards).
- When done: extend `final_table.py` (its arm regex is `(cot|direct)-sN`) to
  the noobj arms, and plot objective x explanation per model.

## Next: the second set of results (interpretability, RQ2-RQ3) on the new design

All on the gemma-3-27b `cot` runs of the final design, staged on CSF as
`~/selas-results/interp-gemma27b-final/cot-s{0..9}` (copies of the decisions;
`SOURCE` names the original run; local copy `results-local/csf/interp-gemma27b-final/`).
Replays need vLLM or transformers on any A100 (`-p gpuA`, no `-A`,
`SELAS_HF_HOME=$HOME/scratch/hf`), not SWIM. Pool every measure with
`experiments/replay/pool_battery.py <dir> -o <json>` (split no-op / action,
run-resampled intervals). Results go in RESULTS §B.

1. **Mediation** `combined` -> `none` -- **done** (job 22284716; RESULTS §B1).
2. **Intervention battery** -- **done** (jobs 22284596/7; RESULTS §B2).
3. **NLA pilot** on the 10 runs -- **done** (job 22285815; RESULTS §B3;
   local copy `results-local/nla/nla-gemma27b-final/`).
4. **Edit and patch** -- **done** (job 22286275; RESULTS §B4, figure
   `figures/nla/patch.{png,pdf}`). Next candidate: the same at P0_turn (before
   any explanation), editing content rather than the letter.

Watchers (background, this session): replay jobs, NLA pilot, edit-patch.

## Local and remote results

- CSF: `~/selas-results/` (all CSF runs; `interp-prompts/` spider figures;
  `mediation_*.json` inside each mediated arm).
- Laptop (gitignored): `results-local/` — OpenRouter and local runs; backed up
  to CSF at `~/selas-results/local-backup/` (without .vec) and
  `~/scratch/selas-results-local/` (full).
- Figures (gitignored, local): `figures/` — `models/`, `prompts-clarknet/`,
  `robustness/`, `interp/`.
- OpenRouter: key in `~/.config/selas/openrouter.env`; ~$2 used of the $50
  limit. OpenRouter providers do not continue a prefilled turn, so use
  `run_local.sh --decide generate` (the letter the model writes, with its
  logprobs, masked as on CSF).

---

# History (before the 2026-09-27 pivot)

## Direction (2026-09-25)

Working abstract (revised 2026-09-27, draft for review — replaces the one
below, which predates the cross-model and rule-3 results):

> LLM-based managing systems are steered by objectives written in natural
> language. We show that a single clause of such an objective can decide
> whether the controller is among the best or the worst. On the SWIM exemplar,
> six LLMs from four families, given the objective as a priority order in
> words, all perform worse than doing nothing — while the same models given no
> objective, or the utility function itself, perform far better (by 7,000–
> 19,000 in SWIM's utility). The cause is one
> rule, "only once the dimmer is at 1.0, run as few servers as you can":
> removing it restores full performance; rewording it, or stating how much a
> late period costs, does not. The models' reasoning names the rule, so the
> failure is visible in the explanation — but visible is not the same as
> causal. We measure how far each configuration's reasoning can be trusted as
> an explanation of its decisions (faithfulness, counterfactual,
> simulatability), and use objective-swap mediation to separate the part of the
> objective's effect that passes through the written reasoning from the part
> that bypasses it. [results pending: RESULTS.md §3, mediation]

Framing notes for the revision: "worse than doing nothing" (5101) holds for
the words runs of all six models (the highest is Llama-3.3-70B at 1310). "Far
better" rather than "best": Llama-4 and Qwen3 stay below doing nothing even
without the words. The gap words → other prompts is 7,300–18,700 per model
(Llama-4 no objective −5544 → 1807; gemma formula −6754 → 11935). The claim is
within-model (what the prompt does to a model), not which model is best.

Previous working abstract (2026-09-25):

> Small changes in how the objective is communicated to an LLM managing system
> swing it from the worst controller to the best, and its reasoning trace does
> not reveal why. We measure how far the trace can be trusted as an explanation
> of the system's decisions (faithfulness, counterfactual, simulatability), show
> that the better-performing configuration's reasoning is the *less* causally
> connected to its decisions, and use activation-level explanations (natural
> language autoencoders) to look for what the trace omits.

Evidence so far (RESULTS.md §2–3): on SWIM's published configuration, prompt A
(objective as a priority order in words) scores −6018 ± 1151 and prompt B
(objective as the utility formula, plus each period's utility shown) scores
10562 ± 754, 3 seeds each. Over all decisions B's decisions track its telemetry
better (counterfactual 0.74 vs 0.48) while its reasoning determines them less
(removing it changes 7% vs 31%).

Framing caution: A and B are not semantically equivalent — the formula carries
magnitudes the words do not — so "the same objective in different forms", not
"equivalent prompts". And A and B differ in two things at once (formula, and
per-period utility feedback); the ablation below separates them.

## Order of work (2026-09-25)

1. **Independent testing — done (2026-09-25).** An independent audit found
   nothing that inflates the performance result. A live integration test on
   CSF (job 21346634) drove SWIM's published configuration through the
   production path with 17 scripted commands: each became exactly one matching
   change in SWIM's own recorded vectors, ~1.2 s after sending, with nothing
   else; illegal targets were masked and not sent; every logged observation
   matched SWIM's recorded state. The same checker found no problems on all six
   published LLM runs. SWIM's own R reproduces 11028.35 for prompt B seed 0.
   (SWIM itself does not guard illegal commands — add at max corrupts counts,
   removing the last server crashes it — so the controller's legality checks
   are what protect runs; they were never bypassed.)

   Defects found, all in the interpretability measures. **All fixed
   2026-09-25 (f983bd9)**; each `test_finding_*` test in
   `experiments/tests/test_audit_interpretability.py` and
   `CONTROLLER/tests/test_audit_offline.py` now asserts the fixed behaviour.
   The A/B interpretability numbers in RESULTS.md §3 were measured before these
   fixes and on the old prompt, so they are superseded once the new cells are
   replayed.
   - **F1 (medium)** `interventions.truncate(r, 3)` keeps the conclusion when a
     field is missing or the conclusion sits under a label outside FIELDS
     (prompt A often writes "Objective:"). No-op on 58/54/45 of 105 decisions
     for prompt A, 1 for B. Inflates A's Simulatability (by up to ~0.05; the
     `e_premises` condition uses it) and restricts A's Mistakes axis to a
     subset. Fixed: the *last* labelled field is the conclusion, whatever its
     label. (Not "the first conclusion-like line": when "Objective:" is
     followed by "Therefore:" it is a premise, restating the goal.)
   - **F2 (low)** `corrupt()` negates the first match anywhere, sometimes a
     line other than the SLA verdict (13 of 630 decisions). Fixed: only the
     SLA field is edited. Also found: "severely breached" was negated to
     "severely met comfortably" on 84 of 630 decisions; fixed.
   - **F3 (low)** replay `legal_ids` come from the recorded masked distribution,
     so a legal option missing from top-k is treated as illegal (5–8 of 105 for
     A). Fixed: `experiments/faithfulness/legality.py` recomputes it from
     the logged observation with the controller's own rule.
   - **F4 (low)** `collect.py`'s `sla_violations_swim` includes the warm-up
     period ending at t=900 (91 periods, not 90); used by
     `builtin_baselines/summarise.py`. Headline late counts are unaffected.
     Fixed.
   - Cosmetic: ReactivePolicy treats zero-throughput RT as 0 (SWIM: NaN, no
     action; never triggered); STEP-mode exemplar letter; a swim.py docstring.

   Audit tooling: `CONTROLLER/tests/test_audit_offline.py`,
   `CONTROLLER/tests/audit_swim_integration.py` (`check --results DIR` verifies
   any run's decisions against its .vec in seconds; `drive-a`/`drive-b` drive a
   live SWIM) and `audit_swim_integration.sbatch`.
2. **Fix the known prompt flaws — done (f983bd9)**, both affecting A and B
   equally:
   - the exemplars describe a 3-server pool ("1 of 3 servers", `max 3`) left
     over from the reduced configuration; the live prompt says 12;
   - the model reads summed utilisation as a fraction ("Utilisation is 1.38,
     which is impossible. It must be a bug in the simulation."). Reword the
     state line so a sum over servers is unambiguous.

   Fixed: exemplars are now data rendered through the live `state_block`
   (pool size, state format and utility line always match the prompt), and
   utilisation is shown as a mean in percent with spare capacity in servers.
   The system prompt now names the reasoning fields, so a prompt with no
   exemplars still asks for them.
3. **Build the prompt procedurally**, from a base upwards, so each component can
   be ablated on its own:

   | component | levels |
   |---|---|
   | base | constraints, action legend, state block (always present) |
   | exemplars | k = 0, 1, 2 |
   | objective | none / priority order in words / utility formula |
   | utility feedback | off / each period's utility in state and history |

   Minimum set: the 2×2 of objective {words, formula} × feedback {off, on}
   at k = 2, three seeds each, which separates the two differences between A
   and B. Extend with k and "no objective" as budget allows. One configuration
   (SWIM published, ClarkNet, seed-sets 0–2), SWIM's reported utility,
   baselines as in RESULTS.md.

   Arms, in `run_comparison.sbatch` (all scaffold, 200 tokens):

   | arm | exemplars | objective | feedback |
   |---|---|---|---|
   | `k0` | 0 | none | off |
   | `k2` | 2 | none | off |
   | `k2-words` (= A) | 2 | words | off |
   | `k2-formula` | 2 | formula | off |
   | `k2-words-fb` | 2 | words | on |
   | `k2-formula-fb` (= B) | 2 | formula | on |

   Seed 0: job 21366743, `submit_comparison.sh --classic
   --trace clarknet --arms "k0@0 k2@0 k2-words@0 k2-formula@0 k2-words-fb@0
   k2-formula-fb@0" --tag prompts-clarknet`. Check every run with
   `CONTROLLER/tests/audit_swim_integration.py check --results DIR`.

   **Done, three seeds (RESULTS.md §2b).** Stating the objective in words is
   worse than not stating it: no objective 11020 ± 390, words −6208 ± 1694,
   formula 11864 ± 342; utility feedback makes no clear difference; without
   exemplars 4038 ± 71. Every run passed the integration check. The model
   applies "run as few servers as you can" literally and thrashes (80 of 105
   decisions are actions).

   **Then robustness (agreed 2026-09-25):** the first claim to establish is
   that the prompt has a distinct effect on utility, and that it holds across
   configurations — pool size, boot delay, and trace (ClarkNet vs WorldCup) —
   before interpreting why. Interpretability (step 5) follows once the effect
   is established.
4. **Consistency**: repeat the decisive cells on a second model
   (Llama-3.3-70B) if the flip holds on gemma. **Across models done
   (RESULTS.md §2c):** the words objective is the worst prompt for every model
   on every seed — gemma (CSF and OpenRouter), gpt-4o-mini, Llama-4-Maverick,
   Qwen3-235B. Llama-3.3-70B on CSF agrees (words 1310 against 9184 / 11227).
   **Rule 3 is the cause (RESULTS.md §2d):** without it gemma recovers fully;
   reworded or given the scale of a late period, it still collapses. Every
   model removes servers while on time far more under the words (§2c).
   Next: the configurations (WorldCup, boot delay, pool size) with no
   objective / words / words-without-rule-3 / formula; then interpretability
   on these runs — does the reasoning say it is following rule 3?
5. **Interpretability** on every cell (replay_all.sbatch + spider), then NLA:
   for the same states, compare what the model represents at the decision
   point under each prompt — does it encode server cost, the breach penalty,
   the boot delay?
6. **Write** the abstract and introduction around the direction above; can
   start in parallel with 3–4, since the framing does not depend on which cell
   wins.
