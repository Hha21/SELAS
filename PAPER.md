# Paper framing — SELAS: Self-Explaining LLM-based Adaptive Systems

The central framing of the SEAMS paper, agreed 2026-09-28. [PLAN.md](PLAN.md)
tracks the work and [RESULTS.md](RESULTS.md) the evidence; this file says what
the paper argues. Section numbers (§) point into RESULTS.md.

## The idea in one paragraph

As adaptive systems become more autonomous, their stakeholders need them to
explain their behaviour: automatically, and targeted to what the stakeholder
needs. An LLM managing system produces a natural-language reasoning trace
before every decision, so it comes with a built-in self-explanation. How good
an explanation is it? We ask two things of it. **Faithfulness:** does the
trace reflect what actually drives the decision? **Completeness:** does it
contain everything that drives it? The second has an inherent limit: every
token compresses the model's internal state (at each position, a
5,376-dimensional vector at each of 62 layers) into one symbol out of 262k,
at most about 18 bits. So even a faithful trace cannot carry everything the
model computes. Natural-language autoencoders (NLA) offer a way to read that
state, before the bottleneck, as text. The paper is about the
interpretability of an LLM managing system: how far its own trace explains its
behaviour, and whether NLA can explain what the trace leaves out.

Wording: "interpretability" and "self-explanation", not "trust".

## Research questions

**RQ1 — Can an LLM act as the managing system, and how robustly?** Being
re-run as a fresh, consistent set (decided 2026-10-05; see "Part A, final
design" below). An LLM managing SWIM is already established, so RQ1 only
needs to place ours: across model families and sizes, with and without
reasoning, against baselines. The bullets below are the earlier results; the
prompt ablations and rule 3 are no longer part of RQ1.

*Earlier results (superseded by the final design):*
- gemma-3-27b in a MAPE-K loop around SWIM (published configuration) is far
  above doing nothing, random actions and SWIM's reactive managers (§2, §2c).
- Robust across three SWIM configurations, four seed-sets each (§2e), and
  across five models from four families, of which the three capable ones beat
  doing nothing (§2c).
- How the objective is written barely matters (no objective ≈ utility formula
  ≈ the priority rules without rule 3; paired intervals all include zero) —
  except an incomplete plain-language rule ("only once the dimmer is at 1.0,
  run as few servers as you can", missing "while within the SLA"), which every
  model follows literally and short-sightedly, ending below doing nothing
  (§2b–2d). A caution about objective specification, not the headline.
- Caveat to state: the LLM's lead over the published planners is SWIM's
  server-cost bonus at dimmer 1.0 (§2).

**RQ2 — Is the reasoning trace a faithful explanation?** Done.
- Where the system acts, the decision depends on the trace: interventions on
  the reasoning change 62–88% of active decisions (§3).
- The objective acts through the trace: swapping it with the reasoning held
  fixed moves 2–20% of the decisions that change; letting the model re-reason
  moves 72–98% (mediation, §3a).
- **Where the system does nothing, the state is a sufficient explanation:**
  no-ops are recovered from the telemetry alone (93%) and rarely depend on
  the reasoning. The trace explains action and describes inaction; this points
  to targeted explanation (explain actions; for inaction, the state suffices).
- The trace exposes the misspecified objective: in all 43 on-time removals
  under rule 3 it names reducing servers as the reason (§2d). A stakeholder
  reading it could catch the problem.

**RQ3 — Is the trace complete, and can the model's internal state fill the
gap?** In progress.
- Incompleteness in time: a server removal is readable from the activations
  where the model's turn opens, before any reasoning is written (linear
  read-out 0.79), while the telemetry and prompt give 0.00 (§3b). The decision
  is represented before it is verbalised. Preliminary (14 removals, one seed
  per prompt).
- NLA reads the pre-bottleneck state as text. The released pair for
  gemma-3-27b works on our pipeline (reproduces its published example), and at
  the action cue its explanation names the action the model then takes in
  283/315 decisions (§3b).
- Before NLA can fill the gap, it must meet the same standard as the trace.
  Two tests:
  1. *Centred reconstruction* (done): our activations are narrowly
     distributed, so the published reconstruction score is dominated by what
     all SELAS decisions share (the average SELAS activation beats it at 5 of
     7 positions). With that removed, the explanations carry what is specific
     to each decision: centred cosine 0.27–0.70 against ~0 for shuffled
     explanations; an explanation picks out its own decision first of 315 in
     65–70% of cases at the Trend/Therefore lines (chance 0.3%); and the
     action read from the reconstructions — from the words — recovers 57% of
     removals before any reasoning is written (telemetry + prompt: 0%) (§3b).
  2. *Edit and patch* (done 2026-10-08, §B4): at the action cue, swap the
     letter the NLA explanation names, reconstruct, move the activation by the
     difference. The choice moves to the edited option in 89% / 54% of no-op /
     action decisions at 0.19·|h| and 99.9% / 80% at 0.37·|h| -- matching or
     beating the supervised class-mean direction, against ≤ 2% for a random
     direction of the same norm. At the natural strength (keep what the words
     do not carry, swap what they do) the edited option gains ~5.5 nats but
     rarely wins (fve ≈ 0.47 there). The NLA explanation is causally faithful
     at the point of decision; earlier positions are the next test.
- Either outcome is reportable: a working read-and-write interface to the
  pre-bottleneck state, or an honest limit of current NLA on a narrow domain.

## Draft abstract (2026-10-08)

Built on Harry's Overleaf draft (its first five sentences kept, "agential" →
"agentic"), with the final-design results (RESULTS §A-§B). The Part 2 sentence, once in
[brackets] as a prediction, is now measured (§B5, 2026-10-10). About
400 words; trim to the venue's limit.

> Modern software systems are expected to operate and maintain goals
> continuously under ever-increasing uncertainty. The rise of LLM-enabled
> agentic reasoning is triggering fresh interest in how machine-learning can
> be used to support the adaptive capabilities of such systems. As systems
> become increasingly autonomous in their decision-making, interpretability
> becomes a first-order concern: stakeholders must be able to understand and
> govern how a system adapts. Yet the chain-of-thought traces produced by LLM
> reasoners, whilst plausible, carry no guarantee of faithfully reflecting the
> model's decision-making process. We instantiate an LLM-based managing system
> on the SWIM exemplar environment with reasoning elicited from the model
> before acting, and compare eleven models from four families with and
> without it: eliciting reasoning changes how often the system acts more than
> how well it performs, and stating the objective widens rather than narrows
> the differences between models. Following this, we present a multi-faceted
> investigation of the interpretability of the elicited reasoning traces. The
> reasoning is causally faithful where the system acts: removing it changes
> 60\% of active decisions and substituting another period's reasoning
> changes all of them, and both the objective and the observed telemetry
> influence the decision almost entirely through what the model writes.
> Decisions to do nothing, however, are fixed by the observed state: they
> survive the removal of the reasoning (1--9\% change) and are predictable
> from the state alone, so for inaction the reasoning is a post-hoc
> rationalisation. Since every generated token compresses the model's
> internal state, we then read that state directly with natural-language
> autoencoders (NLA), which translate activations into text and back. The
> decision is partly represented before any reasoning is written, and NLA
> explanations at the point of decision are causally faithful: editing the
> action they name and writing the change back moves the model's choice to
> the edited action in 89\% of no-op and 53\% of active decisions, at least
> as reliably as a supervised steering direction, while a random direction of
> the same size moves fewer than 1\%. The same holds for a managing system
> that writes no reasoning at all, giving it a self-explanation it otherwise
> lacks: the NLA explanation names the action taken in 94\% of decisions, and
> editing it moves 88\% of no-op and 80\% of active decisions, where the
> supervised direction moves only 9\% of no-ops. We argue that self-explaining adaptive systems should direct
> written reasoning at actions, and complement it with activation-level
> explanations for what the text leaves out.

Where each claim comes from: models and the objective's spread, §A and §A2; 60% / all / 1-9%, §B2
faithfulness; objective through the reasoning, §B1 (92% of changes); telemetry
through the reasoning, §B2 counterfactual (0-13% with the reasoning held vs
73-100% regenerated); predictable from the state, §B2 simulatability
(96-99%); represented before the reasoning, §B3 (dimmer changes 82% vs
57-59% from telemetry); edit and patch, §B4 (patch 0.19·|h|, the edits the
class-mean direction also covers; random 0.0% / 0.9%); without reasoning,
§B5 (names the chosen letter in 987/1050, all 27 actions; patch 0.29·|h|,
same matched edits; class-mean 9.4% of no-ops; random 0.0%).

## Contributions (draft)

1. An LLM managing system for SWIM with an integration check, evaluated under
   SWIM's own utility across configurations, seeds and five models.
2. Evidence that objective phrasing matters little, and a documented failure
   mode: literal, short-sighted application of an incomplete rule.
3. A behavioural protocol for trace faithfulness in adaptive systems
   (interventions, counterfactual telemetry, objective-swap mediation), and the
   finding that traces explain actions but only describe inaction.
4. A first test of natural-language autoencoders as a complement to the trace
   for the part it cannot carry.

## Part A, final design (decided 2026-10-05)

One environment, one prompt, fresh runs, five seed-sets per cell.

- **Environment:** SWIM's published configuration (ClarkNet, 12 servers from
  3, 180 s boot, 10 dimmer levels, 60 s periods, 105 min, first 15 min
  unscored), SEAMS 2017A utility.
- **Prompt (`combined`):** rules 1–2 of the words objective, then the utility
  function with its constants; each period's utility in the telemetry; two
  worked examples. Without rule 3, words and formula scored the same, so both
  are given.
- **Reasoning, on vs off:** arms `cot` (scaffolded reasoning, 200 tokens, then
  the action letter) and `direct` (the model's turn opens at "Action:"; one
  forward pass). Paired by seed within each job. RQ2 predicts the result:
  if no-ops are fixed by the state and actions carried by the reasoning,
  removing it should leave no-ops largely intact and change actions.
- **Families and sizes**, one decision method for all (vLLM, scored letter):
  gemma-3 4B / 12B / 27B; Qwen2.5 7B / 14B / 32B; Llama-3.1-8B (needs the
  Meta licence accepted on the HF account) and Llama-3.3-70B (FP8, 2 GPUs).
  All open weights, so the interpretability analyses can follow on any of
  them (NLA pairs exist for gemma-3 12B/27B, Qwen2.5-7B, Llama-3.3-70B).
- **Baselines:** do nothing; random legal actions (10 seeds); SWIM's built-in
  Reactive and Reactive2 (10 seeds) — existing runs, same environment, valid
  as they are. PLA and Thallium: SWIM's shipped runs only (one each). Their
  result files confirm they ran in exactly this environment (maxServers 12,
  initialServers 3, bootDelay 180, 10 brownout levels, ClarkNet, seed-set 0,
  `ProactiveAdaptationManager`); they choose 2–3 servers with a low dimmer.
  Since 2026-10-08 they **can** be re-run (`experiments/swim_planners/`): the
  shipped runs are Experiment 2 of Stevens & Bagheri, ICSE 2020; their PLA is
  Stevens's port of PLA-SDP into SWIM (not Moreno et al.'s), planning for its
  own utility (0.4 cost + 0.1 dimmer + 0.5 response time), not SEAMS 2017A.
  PLA reproduces the shipped run decision for decision (4089.09); Thallium
  does too, but only with a trimmed relation reconstructed by search (the
  original was never published). Both are deterministic on this trace (they
  read only the arrival rate), so seed-sets 1-10 give 4089.09 ± 0 and
  4658.65 ± 0: report them as reference lines, with their planning utility
  stated, not as distributions.
- **Rule 3** leaves RQ1. It stays only as a planted, known cause in RQ2 (the
  trace names it; mediation shows its effect passes through the trace).

Status: gemma-27B submitted (gpuA jobs 22001439/40, tag `final-gemma27b`);
the other models' weights are being copied/downloaded to `~/scratch/hf`.

## Decisions and proposals of 2026-10-06 (read this first after a compaction)

- **Rule 3 is dropped from the paper** (an artefact of one plain-language
  rule; not pursued further).
- ~~Terminology: "explanation", not "reasoning".~~ Superseded 2026-10-08:
  **"reasoning" for the trace, "self-explanation" for its role.** What the
  arms compare is prompted chain-of-thought (the "think step by step" kind;
  the term of the method's source paper and the CoT-faithfulness literature):
  arms "with reasoning" / "without reasoning". Whether that reasoning works as
  the system's self-explanation is the paper's question, hence the title; for
  no-ops it is a post-hoc rationalisation. State once, early, that this is
  prompted reasoning from instruction-tuned models (the deployable design, and
  the one NLA pairs exist for); reasoning-trained ("thinking") models stay out
  of scope -- RL-trained, unstructured, often hidden traces, no NLA pair;
  limitation / future work.
- **Part A figure:** `experiments/controller_comparison/reasoning_plot.py`
  on `results-local/csf/final_table.json` (from `final_table.py`) ->
  `figures/models/reasoning.{png,pdf}`; rows = models, dots = runs, bars =
  means; reference lines = SWIM's PLA (4089.09) and Thallium (4658.65), re-run
  and validated (RESULTS §C), replacing do nothing / static (2026-10-08). All 11 models
  complete at 10 runs per arm (2026-10-07).
- **Proposed prompt decomposition (to confirm with Harry):** fixed parts --
  role and constraints, action legend, telemetry (including each period's
  utility), live state; varied components -- objective {none, words (rules
  1-2), formula, words + formula = the canonical prompt}, explanation {yes,
  no}, worked examples {2, 0}. A diagram in the paper shows the parts. Run the
  full factorial on gemma-3-27b only (its two canonical cells exist, 10 runs
  each); the model comparison stays on the canonical prompt.
- Part A with 10 runs per arm: only Qwen-14B (+6047 [5119, 6976]) and
  Llama-8B (−3022 [−4015, −2029]) show a significant explanation effect; the
  capable models lean slightly negative, not significant; the robust effect
  is behavioural (asking for an explanation makes models act more, all but
  gemma-4B).

## Decision of 2026-10-08: the prompt ablation is objective x explanation

Replaces the proposed decomposition above. Two factors, across all 11 models,
10 runs per arm, worked examples held at 2 (the deployed prompt):

| | with explanation | without explanation |
|---|---|---|
| objective stated (block + utility lines) | `cot` (Part A) | `direct` (Part A) |
| no objective (neither) | `cot-noobj` | `direct-noobj` |

- "No objective" removes the objective block *and* every utility line
  (telemetry and worked examples): `--objective none`, no `--utility-feedback`.
- The worked examples are not neutral: they show two sensible actions, and
  example 2's explanation says "raise the dimmer before giving up a server",
  so with examples "no objective" means "not stated", not "unknown". Without
  examples and objective gemma-27B kept the dimmer near 0.14 (4,038; §2b
  `k0`, older prompt). State this; examples are part of the fixed prompt.
- The explanation can be asked for without examples (the system prompt names
  the fields; the letter is read after our own "Action:"), but examples are
  not varied: no claim about them is made.
- Each row keeps its decision method (CSF rows on CSF, OpenRouter rows on
  OpenRouter), so the objective comparison is not confounded with the method.
  Not everything moves to OpenRouter: Qwen2.5 14B/32B are not served there,
  provider precision is not ours, the interpretability work needs our own
  weights and the scored letter, and local runs need the laptop (105 min real
  time per run).

## Open decisions

- Title: keep "SELAS: Self-Explaining LLM-based Adaptive Systems"?
- RQ3 scope for this paper: the centred check and the edit-and-patch test at
  the action cue only. Future work: domain adaptation of NLA (LoRA/RL, with a
  reward referenced to the domain's own mean), the full set of NLA axes beside
  the behavioural ones, patching before the reasoning, other models.
- ~~Whether the rule-3 result sits in RQ1~~ — decided 2026-10-05: not in
  RQ1; kept only as the planted cause in RQ2.
- Framing: empirical study with a light protocol (faithfulness → completeness
  → elicitation), rather than a framework; a framework claim would need a
  second LLM managing system or exemplar.
