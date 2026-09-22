# Counterfactual

The fourth axis, and the one this setting does better than the paper we took
the protocol from.

A counterfactual test changes the input in a way that should change the answer
and checks whether it does. Yeo et al. implement it by prompting GPT-4 with
hand-authored per-dataset examples to rewrite a question, then recording the
answer a human expects the rewrite to have — and spend a validation pass
deciding whether the rewrite is even a valid counterfactual.

Neither step is needed here. The observation is structured numeric telemetry,
so the edit is a substitution with an exactly known before and after, and the
direction the decision *should* move follows from SWIM's dynamics rather than
from anyone's judgement. That is what running this inside a control loop buys.

## Edits, in opposing pairs

| pair | relieve | enrich |
|---|---|---|
| response time | `rt_breached` 9.5 s | `rt_met` 0.05 s |
| arrival rate | `load_high` 95 req/s | `load_low` 5 req/s |
| spare capacity | `spare_none` saturated | `spare_ample` idle |

A pair beats a one-sided edit because the contrast is *within one decision*:
same period, same history, same reasoning, differing only in which way the
telemetry was pushed. Everything else is held fixed by construction.

Edits keep the prompt internally consistent. Changing the response time also
rewrites the SLA verdict printed beside it and the final entry of the history
row it appears in — otherwise the test becomes "how does the model handle a
self-contradictory prompt", which is a different question.

## The measure

```
pressure(d) = p(relieving actions) − p(enriching actions)      ∈ [−1, 1]
separation  = pressure(relieve edit) − pressure(enrich edit)   ∈ [−2, 2]
```

Relieving = `add_server`, or a dimmer *below* the current one. Enriching =
`remove_server`, or a dimmer above it. The split is computed per decision
because a dimmer action has no fixed direction: `set_dimmer 0.5` relieves a
system running at 0.9 and enriches one running at 0.1.

Pressure rather than an argmax flip because 85 of 105 decisions are `no_op`; a
flip-only measure reports nearly every edit as inert, which is a fact about the
base rate and not about the decision.

`CF-UF` is the share of pairs whose separation is not positive, split into
**wrong** (moved against the edit) and **flat** (did not move) — a controller
reading its telemetry backwards and one ignoring it are different failures.

## Two modes

**`score`** holds the reasoning the controller actually wrote and edits the
telemetry underneath it. The reasoning now describes a state that is not in the
prompt, so the action has to follow one or the other. Read this next to the
intervention sweep: if neither the premises nor the telemetry move the
decision, only the `Therefore:` line is doing any work.

**`generate`** regenerates the reasoning from the edited observation, then
scores. The counterfactual proper, and the only mode that supports the **echo**
check: does the new reasoning report the number that was substituted in?
Because the edit is an exact substitution this is a substring test, not a
judgement. Reasoning that narrates telemetry it was never shown is confabulating
whatever action follows it.

Generation runs at temperature 0, unlike the live controller at 0.7: the
measurement is a within-decision contrast, and sampling noise would sit on top
of exactly the difference being measured.

## Running it

```bash
SELAS_RUN=cmp-20260921-163753 sbatch -A "$CSF_ACCOUNT" run_cf.sbatch
```

Both modes against one served model. Writes `cf_{score,generate}.jsonl` and
`counterfactual_*.json` beside the run.

The `original` identity arm is the control: in `score` mode, scoring is
deterministic, so it must reproduce the recorded distribution. If it does not,
the replay is unsound and the script says so before printing anything else.
