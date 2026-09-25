# Plan

Agreed with supervisor, 2026-09-25. Read with [RESULTS.md](RESULTS.md), which
records everything measured so far.

## Direction

Working abstract:

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

## Order of work

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

   First pass, one seed: job 21366743, `submit_comparison.sh --classic
   --trace clarknet --arms "k0@0 k2@0 k2-words@0 k2-formula@0 k2-words-fb@0
   k2-formula-fb@0" --tag prompts-clarknet`. Check every run with
   `CONTROLLER/tests/audit_swim_integration.py check --results DIR`.

   **Then robustness (agreed 2026-09-25):** the first claim to establish is
   that the prompt has a distinct effect on utility, and that it holds across
   configurations — pool size, boot delay, and trace (ClarkNet vs WorldCup) —
   before interpreting why. Interpretability (step 5) follows once the effect
   is established.
4. **Consistency**: repeat the decisive cells on a second model
   (Llama-3.3-70B) if the flip holds on gemma.
5. **Interpretability** on every cell (replay_all.sbatch + spider), then NLA:
   for the same states, compare what the model represents at the decision
   point under each prompt — does it encode server cost, the breach penalty,
   the boot delay?
6. **Write** the abstract and introduction around the direction above; can
   start in parallel with 3–4, since the framing does not depend on which cell
   wins.
