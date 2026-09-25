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

1. **Independent testing** (in progress). A sub-agent tests the code and the
   integration with SWIM against a written brief; findings are verified before
   anything is believed or fixed. No new GPU runs until this is clean.
2. **Fix the known prompt flaws**, both affecting A and B equally:
   - the exemplars describe a 3-server pool ("1 of 3 servers", `max 3`) left
     over from the reduced configuration; the live prompt says 12;
   - the model reads summed utilisation as a fraction ("Utilisation is 1.38,
     which is impossible. It must be a bug in the simulation."). Reword the
     state line so a sum over servers is unambiguous.
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
4. **Consistency**: repeat the decisive cells on a second model
   (Llama-3.3-70B) if the flip holds on gemma.
5. **Interpretability** on every cell (replay_all.sbatch + spider), then NLA:
   for the same states, compare what the model represents at the decision
   point under each prompt — does it encode server cost, the breach penalty,
   the boot delay?
6. **Write** the abstract and introduction around the direction above; can
   start in parallel with 3–4, since the framing does not depend on which cell
   wins.
