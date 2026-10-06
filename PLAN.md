# Plan

Read with [RESULTS.md](RESULTS.md), which records every measurement and where it
lives. This file says what the paper argues, what is established, and what is
next. Updated 2026-09-27 (pivot agreed with Harry).

## Running now (2026-10-06) — Part A to 10 runs per arm

Seed-sets 0-4 of every model are in (RESULTS §A). Now:

**CSF, gpuA**: seed-sets 5-9 for all eight models, cot and direct, two jobs
each (Llama-3.3-70B bf16 on 4 A100s): 22067525/30 gemma-27b, 32/34
gemma-12b, 39/41 gemma-4b, 58/61 Qwen-14B, 65/69 Qwen-32B, 71/76 Qwen-7B,
78/82 Llama-8B, 83/87 Llama-70B. Results `~/selas-results/final-<model>-*`
(directories now unique per job).

**Laptop, OpenRouter**: three models at 10 runs per arm, as on CSF --
gpt-4o-mini@OpenAI (0-9), gpt-4o@OpenAI (3-9; 0-2 exist), DeepSeek-V3@GMICloud
(0-9 afresh: the earlier 0-2 used the old illegal-letter handling, moved to
`results-local/superseded/`) -- plus the static reference (`static@0`: dimmer
1.0, 4 servers, hold). Script `results-local/launch/chain-or-20261006.sh`,
log `chain-or-20261006.log`; ~10 h in five batches. **Resumable**: finished
batches leave `results-local/launch/markers/<batch>.done`; after an
interruption move the cut batch's result directories aside and re-run the
script.

Since 2026-10-06 the generate mode refuses an illegal letter once and asks
again when the provider returns no probabilities (notes `reasked`).

**When they finish:** re-run `final_table.py` over `results-local/csf/final-*`
and `results-local/fo-*` (not `superseded/`); the plot: rows = models x arm,
dots = runs, dashed line = static.

## The story

**Superseded 2026-09-28 by [PAPER.md](PAPER.md)**: the paper's framing
(faithfulness and completeness of the trace; RQ1–RQ3), draft abstract,
contributions and open decisions. The 2026-09-27 version is kept below for the
record.

**SELAS: an LLM as a self-explaining managing system.** Three parts:

1. **Proof of concept, and its robustness.** An LLM (gemma-3-27b) runs SWIM
   as its managing system and is competitive under SWIM's reported utility.
   How the objective is stated matters little: no objective, the priority
   order without rule 3, and the utility formula are statistically
   indistinguishable for gemma (RESULTS §2d statistics). The one exception is
   a single over-applied clause, rule 3 ("only once the dimmer is at 1.0, run
   as few servers as you can"), which collapses every model tested; it is a
   case study, not the headline (a reviewer can fairly read it as "told to
   minimise servers, it did"). The choice of model matters far more than the
   prompt (gemma ~11–12k; Llama-4 and Qwen3 below doing nothing).
2. **Self-explanation: can the reasoning be trusted as an explanation?**
   Behavioural measures on gemma (RESULTS §3): over the decisions where the
   controller acts, its action depends heavily on its reasoning (sensitivity
   0.70–0.88), is robust to paraphrase, and tracks its telemetry
   (counterfactual 0.81–0.88). Mediation (§3a): the objective's effect passes
   through the written reasoning (direct path 2–20% of flips). The rule-3
   failure is diagnosable from the trace: all 43 on-time removals cite
   reducing servers.
3. **Mechanistic interpretability (next).** What does the model represent at
   the decision point that the trace does not say? Released NLA checkpoint
   pair for gemma-3-27b-it at layer 41 (`kitft/nla-gemma3-27b-L41-{av,ar}`,
   listed in `NLA/src/config.py`; also Llama-3.3-70B L53).

Working abstract: to be rewritten around the three parts above; the draft
further down (rule 3 as headline) is superseded by this pivot.

## Status

**Part 1 — established.** Six models, four families, 3–4 seeds on the
published configuration (§2b–2c); rule 3 isolated on three setups (§2d);
two more configurations for gemma, 3 seeds (§2e); baselines: do nothing,
SWIM reactive (10 seeds), PLA and Thallium (shipped, one run each, objective
unknown), random (10 seeds). Every run passes the integration check; the
laptop and CSF are the same simulation (§2c). Caveats to state, not fix: PLA
and Thallium are single shipped runs; gemma's lead over them is SWIM's
cost bonus at dimmer 1 (§2).

Running (CSF, submitted 2026-09-27 ~02:30, vLLM scoring like the main gemma
results): gemma in the two extra configurations, four prompts (k2, k2-words,
k2-words-no3, k2-formula) x seed-sets 0–3 — jobs 21419243–5 (ClarkNet boot
60 s, tag `rb-cn60`) and 21419247–9 (WorldCup boot 180 s, tag `rb-wc180`),
results `~/selas-results/rb-{cn60,wc180}-*`. They replace the 3-seed
OpenRouter numbers in §2e as the primary figures for those configurations
(and settle WorldCup, where 3 seeds spread widely). Each job runs the
integration check itself; check it reads bootDelay 60 for cn60.

**Robustness replication — done 2026-09-28** (RESULTS §2e, CSF
replication): all 32 A100 runs pass; words worst on every seed in both
configurations, rule 3 removed restores it, WorldCup now separates. H200
twins: cn60 jobs 21419243/4 done and 21419245 running (a full H200 ClarkNet-60
set for a hardware comparison); wc180 21419247 running, 21419248/9 pending
(keep or cancel -- asked 2026-09-28). The H200 pilot twin was cancelled.

**Part 2 — established; small gaps.** Battery re-measured on the fixed code
(§3, 15 runs, both pools); mediation (§3a, 7 runs, figure
`figures/interp/mediation.pdf`); the trace-names-the-cause count (§2d).
Present the active-decision pool as primary and state the no_op base rate up
front. Possible addition: per-seed spread on the spider axes.

**Part 3 — first iteration done (2026-09-28), RESULTS §3b.** The released
pair reproduces its published example on our pipeline; explanations are
faithful at the reasoning fields (fve_nrm 0.67–0.75), less at the action cue
(0.46), not at the end of the telemetry (0.15); the action kind is linearly
readable before any reasoning (0.84 vs 0.77 from telemetry alone); the
explanations name the chosen letter in 85–101/105 decisions; no SLA-risk
content at the rule-3 removals. Code: `experiments/nla/` (pilot.py,
analyse_pilot.py, run_pilot.sbatch; on gpuA set SELAS_HF_HOME=$HOME/scratch/hf).

## Next

1. **Collect the robustness jobs** (above): tables per configuration with
   paired intervals (as in §2d), update §2e, replace the figures.
2. **NLA as new axes of the interpretability score** (the "completeness"
   aspect behavioural tests cannot reach; motivation and table in
   `LaTeX_Poster/poster_claims.md`, "Outlook"): run the pilot over all 16 runs
   (4 prompts x 4 seed-sets, one gpuA job); axes per decision, all/active,
   each with a shuffled-pairing control and reported with fve_nrm --
   Agreement (explanation at the action cue names the chosen action; pilot
   283/315), Consistency (explanation vs trace at each field; LLM judge),
   Completeness (decision-relevant content the trace lacks; LLM judge),
   Pre-commitment (action readable at P0_turn beyond telemetry + prompt);
   add them to the spider figure. Stretch: patch the P0_turn activation from a
   removal into an on-time no-op state and see whether the action follows.
3. **Write** the abstract and introduction around the three parts.
4. **Poster** (due ~2026-09-29): `LaTeX_Poster/feedback.md` lists the changes
   (three passages now wrong; new results and figure paths). Parts 1–2 go on
   the poster; part 3 as work in progress.

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
