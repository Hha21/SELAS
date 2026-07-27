# LLM Self-Adaptation & Interpretability in TAS

Summer project working notes. Scope: one exemplar (TAS), one LLM-based
self-adaptation layer inspired by POLARIS, three model-internals
interpretability methods.

## Motivation

LLMs are increasingly proposed as the reasoning core for higher-level
self-adaptation — resolving uncertainty that wasn't anticipated at design
time and pursuing goals more autonomously, in the spirit of the original
Autonomic Computing Initiative. But LLM reasoning is opaque, and
opacity is a much bigger problem in safety-critical domains where a human
has to stay accountable "on the loop" — healthcare being the clearest case.

Explainable AI gives outside insight into a decision. A stronger property
is Self-Explainability (SX): the system explains itself. Beyer, Wisy &
Tomforde (2026) define six levels of SX, from no explainability up through
full explainability of past/present/future/hypothetical behaviour for any
target group. This project asks a narrower, testable version of that:
**does the choice of interpretability method determine which stakeholder
an explanation can actually serve** — i.e. can probing an LLM's own
activations move a self-adaptive healthcare system from SX-ready
(Level 1) toward Target-Specific SX (Level 3)?

## Exemplar: TAS

Tele Assistance System (Weyns & Calinescu, SEAMS 2015). A wearable sensor
and panic button feed a workflow of third-party services — medical
analysis, drug, alarm — that act on the patient directly (change dose,
dispatch an ambulance). The self-adaptation logic sits one level above
that: it doesn't make the clinical call, it decides which concrete
service instance to invoke, retry, or switch to, based on reliability and
cost telemetry. That's the decision point this project targets.

Chosen over BSN (the other SEAMS healthcare exemplar) because its
adaptation decisions are discrete/categorical (retry vs switch vs select),
which maps far more naturally onto token-level interpretability methods
than BSN's continuous control knobs (sampling frequency, gain). It also
already ships predefined uncertainty scenarios (S1-S5) and QoS metrics
that can be reused directly as evaluation cases, and its actuators have
real patient-facing stakes, which matters for the accountability framing.

Known risk: TAS is a decade-old, non-git-tracked distribution — build
health on a modern JDK is unverified. If it proves too brittle, BSN is
the fallback, retargeted at its discrete risk-classification decision
(low/moderate/high) instead of TAS's service-selection decision.

## Planned architecture: POLARIS-style layer over TAS

POLARIS (Pandey et al., 2025) structures adaptation into three layers.
Mapping onto TAS's existing ReSeP platform:

| POLARIS component | Role | TAS mapping |
|---|---|---|
| Metric Collector | gathers telemetry | existing `WorkflowProbe` |
| Execution Adapter | applies actions | existing `WorkflowEffector` |
| Kernel | triages fast vs deliberative path | new: dispatch panic-button events straight to Fast Controller, route everything else to the Reasoner |
| Fast Controller | low-latency fallback policy | deterministic rule, e.g. panic button always → immediate alarm, no LLM in the loop |
| Reasoner | deliberative LLM agent | new: decides retry / switch / select-reliable, replacing the original Retry and Select Reliable baselines |
| Verifier | safety backstop | checks the Reasoner's proposed action against invariants (cost ceiling, no dropped alarm coverage) before it reaches the Effector |
| Knowledge Base | episodic memory | adaptation/QoS logs already produced by TAS |
| World Model | what-if simulation | TAS's existing cost/reliability formulas, reusable as a lightweight predictive model |
| Meta-Learner | reflects on history, updates strategy | new: periodically revises the Reasoner's prompt/thresholds from logged outcomes |

Design decision: the LLM operates only at the adaptation/meta level
(which service, which strategy). The clinical judgement embedded in the
Medical Analysis Service stays a given, out of scope — for both safety
and scope reasons.

## Interpretability methods

Three lenses on the Reasoner's activations, each with a different natural
audience:

- **Tuned logit lens** — cheapest, no training beyond a per-layer affine
  probe. Projects intermediate activations into the output vocabulary.
  Developer/verifier-facing; weak once the content isn't close to the
  output tokens.
- **Sparse autoencoders (SAEs)** — learned dictionary of interpretable
  features. More rigorous, more setup cost (training + human labelling
  of features), still fundamentally developer/verifier-facing.
- **Natural Language Autoencoders (NLA)** — Anthropic, May 2026. An
  activation verbalizer turns an activation into text, an activation
  reconstructor tries to recover the activation from that text alone,
  trained jointly. Most legible to a non-technical stakeholder (clinician,
  auditor), but faithfulness of the explanation isn't guaranteed by
  training — needs to be evaluated, not assumed.

The comparison across all three, on the same decision point, is the core
of the "Target-Specific SX" claim.

## Work plan

- **Phase 0 (now):** get TAS building and running from the installed
  source; understand the ReSeP platform, the workflow specification
  language, and how probes/effectors/adaptation engines currently plug
  in (Retry and Select Reliable via ActivFORMS, per the original paper).
- **Phase 1:** build a thin LLM Reasoner against TAS's existing
  effector interface, reusing the S1-S5 scenarios as test cases.
- **Phase 2:** instrument the Reasoner's forward pass — logit lens
  first, then SAEs, then NLA.
- **Phase 3:** map each method's output onto the SX-levels table and
  compare from a stakeholder perspective (engineer vs on-the-loop
  clinician).

Second exemplar, full stakeholder user study, and Verifier/Meta-Learner
depth are stretch goals, not core deliverables.

## Open risks to track

- TAS build health on a modern JDK is unverified.
- No established SX evaluation methodology exists yet — one will need
  to be defined, not just applied.
- NLA needs either a trained verbalizer/reconstructor pair for the
  chosen Reasoner backbone, or one of Anthropic's released pretrained
  NLAs for a compatible open-weight model — check compatibility before
  committing to a backbone.

## References

- Weyns, D. & Calinescu, R. *Tele Assistance: A Self-Adaptive
  Service-Based System Exemplar.* SEAMS 2015.
- Pandey, D. et al. *POLARIS: Is Multi-Agentic Reasoning the Next Wave
  in Engineering Self-Adaptive Systems?* 2025. arXiv:2512.04702
- Beyer, T., Wisy, S. & Tomforde, S. *Self-Explainability in
  Self-Adaptive and Self-Organising Systems: Status and Research
  Directions.* 2026. arXiv:2606.09568
- Anthropic. *Natural Language Autoencoders.* 2026.
