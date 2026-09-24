# SELAS: Self-Explaining LLM-based Adaptive Systems

Research code for studying **interpretability in LLM-based self-adaptive systems**.
An LLM acts as the managing system for a simulated web application, deciding each
minute how to reconfigure it; we then measure how far the reasoning it writes can be
trusted as an explanation of what it did, and examine its activations directly.

Results, with how to regenerate each one, are in **[RESULTS.md](RESULTS.md)**.

## Layout

| Directory | Role | What it is |
|---|---|---|
| [SWIM/](SWIM/) | **managed system** | SWIM (Moreno et al.): a simulated web application with two knobs — server count and a *dimmer*, the fraction of responses carrying optional content. Controlled over TCP. |
| [CONTROLLER/](CONTROLLER/) | **managing system** | A MAPE-K loop with one LLM. Each period it reads SWIM's telemetry, writes its reasoning, and scores the action options; the highest-scoring legal action is executed. |
| [experiments/](experiments/) | **evaluation** | The comparison against SWIM's own managers, and the interpretability measurements on the controller's reasoning. |
| [NLA/](NLA/) | **activation-level explanation** | Natural Language Autoencoders: turn the model's residual-stream activations into natural-language explanations. See [NLA/README.md](NLA/README.md). |
| [POLARIS/](POLARIS/) | *reference only* | LLM-based self-adaptation framework (Pandey et al., 2025). Studied and audited early in the project; not used for any result. |

## The system

```
 SWIM (managed system)  <-- TCP -->  CONTROLLER (managing system)  <-- HTTP -->  LLM server (vLLM)
   ClarkNet trace                     monitor -> reason -> score                  gemma-3-27b-it
   12 servers, 180 s boots            -> execute, every 60 s
```

- **Managed system.** SWIM's socket-controlled network (`SWIM/simulations/swim`),
  run in real time inside an Apptainer image. The paper uses SWIM's published
  configuration: ClarkNet, 12 servers starting from 3, 180 s boot delay, 10 dimmer
  levels.
- **Managing system.** `CONTROLLER/run_controller.py`. The prompt is a system
  message (constraints, objective, action legend), two worked exemplars, and a
  user turn with the current state and recent history. The model writes its
  reasoning; the action is chosen by comparing the probabilities of the action
  letters at the `Action:` position, so every decision is a full distribution
  over the options rather than parsed free text.
- **Baselines.** SWIM's built-in `ReactiveAdaptationManager` and
  `ReactiveAdaptationManager2`, run in SWIM's self-adaptive network
  (`SWIM/simulations/swim_sa`); SWIM's shipped PLA and Thallium results; and a
  controller that never acts.
- **Utility.** SWIM's reported utility, `periodUtilitySEAMS2017A` from
  `SWIM/tools/plotResults.R`, computed from the recorded vectors by
  `experiments/controller_comparison/swim_utility.py` (verified equal to SWIM's R).

## Running

Everything runs on the Manchester CSF3 cluster (Slurm, H200 GPUs, Apptainer).
Account and host details go in `CONTROLLER/csf/local.env` (gitignored); see
[CONTROLLER/csf/README.md](CONTROLLER/csf/README.md) for setup.

| What | Command (from the repo on CSF) |
|---|---|
| LLM controller runs | `experiments/controller_comparison/submit_comparison.sh --classic --trace clarknet --arms "llm@0 formula@0"` |
| Do-nothing run | `SELAS_POLICY=null ... sbatch experiments/controller_comparison/run_baseline.sbatch` |
| SWIM's built-in managers | `sbatch experiments/builtin_baselines/run_builtin.sbatch` |
| Performance figure and table | `experiments/controller_comparison/published_figure.sh` |
| Interpretability replays | `SELAS_RUN=<run> SELAS_ARMS="..." sbatch experiments/replay/replay_all.sbatch` |
| Interpretability figures | `experiments/spider/spider.py`, `experiments/spider/pareto.py` |

Each directory's README explains its part in detail:
[CONTROLLER/](CONTROLLER/README.md),
[controller_comparison](experiments/controller_comparison/README.md),
[counterfactual](experiments/counterfactual/README.md),
[simulatability](experiments/simulatability/README.md).
To serve the NLA locally, `./start_nla.sh` / `./stop_nla.sh`.

Offline tests (no GPU, no simulator): `cd CONTROLLER && python -m pytest tests/`.

## References

- Moreno, G. A. et al. *SWIM: An Exemplar for Evaluation and Comparison of
  Self-Adaptation Approaches for Web Applications.* SEAMS 2018.
- Moreno, G. A. et al. *Comparing Model-Based Predictive Approaches to
  Self-Adaptation: CobRA and PLA.* SEAMS 2017.
- Yeo, W. J. et al. *How Interpretable are Reasoning Explanations from Prompting
  Large Language Models?* 2024.
- Lanham, T. et al. *Measuring Faithfulness in Chain-of-Thought Reasoning.* 2023.
- Hase, P. et al. *Leakage-Adjusted Simulatability.* Findings of EMNLP 2020.
- Pandey, D. et al. *POLARIS.* 2025.
