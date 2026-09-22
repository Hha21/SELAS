# Simulatability

The third axis of the interpretability score: does the reasoning let *someone
else* predict what the controller did?

Faithfulness (`../faithfulness`) asks whether the reasoning caused the action.
Simulatability asks whether it communicates it. A reasoning trace can be
perfectly causal and still useless to a reader, and the intervention sweep
already showed the reverse is possible here too -- negating the SLA premise
moved nothing, so whatever the premises are doing, they are not carrying the
decision.

## The score

Hase et al.'s leakage-adjusted simulatability, as used by Yeo et al. A
simulator predicts the controller's action under three inputs:

| condition | final user turn | final assistant turn |
|---|---|---|
| `xe` | telemetry | reasoning |
| `x`  | telemetry | *(removed)* |
| `e`  | *withheld* | reasoning |
| `e_premises` | *withheld* | reasoning minus `Therefore:` |

`acc(xe) - acc(x)` is what the explanation buys. `e` exists because an
explanation that states its own conclusion inflates that difference without
explaining anything, so the difference is computed separately on the decisions
where `e` alone sufficed (leaking) and where it did not, and the two halves are
averaged.

`e_premises` is ours. Our reasoning ends in a line that names the action in
words, so `e` is expected to leak nearly everywhere, which would collapse the
split that the adjustment depends on. Dropping that line separates *the
explanation states the answer* from *the explanation contains what is needed to
derive it*.

## Two departures from the original

**No gold label.** There is no correct action for a period, only the one the
controller took, so the simulator's target is the controller's decision. That
is what simulatability means here and it removes the need for ground truth.

**No trained simulator.** Theirs is a T5 fine-tuned on explanation-answer
pairs. Ours is a frozen, smaller instruct model from the same family, prompted
with the exemplars the controller saw. Training on 105 decisions of which 91 are
`no_op` would learn the base rate; and the scoring call is one the controller
already makes. The cost is that a weak simulator depresses every arm at once,
which is why per-condition accuracies are printed next to the difference and why
the job also runs the controller's own model as a ceiling.

## Reading the output

Three numbers before the score itself:

- **majority rate** -- most periods are `no_op`, so an accuracy below this line
  is worse than not reading the prompt at all.
- **the ACTIVE split** -- a decision to do nothing survives any edit, so the
  pooled figure reports the base rate of inaction. Same reason the intervention
  sweep needed it.
- **n_nonleaking** -- if it is tiny, `LAS_0` rests on almost nothing and the
  mean of the two halves is not stable. The script says so.

`las` is in [-1, 1]; `las_normalised` maps it to [0, 1] for the spider plot.

## Running it

```bash
# on CSF, against a recorded run under ~/selas-results
SELAS_RUN=cmp-20260921-163753 sbatch -A "$CSF_ACCOUNT" run_sim.sbatch

# locally, no GPU needed
python3 test_conditions.py
```

Writes `simulated_{student,ceiling}.jsonl` and `simulatability_*.json` beside
the run.
