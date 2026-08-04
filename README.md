# SummerWork

Research setup for studying **LLM-based self-adaptation and interpretability**:
an LLM decides how a running system should adapt, and we read its activations to
explain *why*.

Three pieces, each independently runnable:

| Directory | Role | What it is |
|---|---|---|
| [SWIM/](SWIM/) | **managed system** | Simulated web infrastructure with two knobs — server count and a "dimmer" trading response fidelity for latency. Runs in Docker, controlled over TCP on port 4242. |
| [POLARIS/](POLARIS/) | **managing system** | LLM-based self-adaptation framework (Pandey et al., 2025). Reads SWIM telemetry, reasons about it, and enacts adaptation actions. |
| [NLA/](NLA/) | **interpretability** | Natural Language Autoencoder (Anthropic, 2026). Serves the LLM that POLARIS reasons with, captures its activations, and turns them into natural-language explanations. |

`BSN/` and `TAS/` are other SEAMS exemplars, parked for now — nothing below
involves them. Project background and the longer plan are in
[PROJECT_PLAN.md](PROJECT_PLAN.md).

## How they fit together

```
        ┌────────────────────────── SWIM (Docker) ──────────────────────────┐
        │            simulated servers + dimmer, TCP :4242                  │
        └───────────▲───────────────────────────────────────┬───────────────┘
           telemetry│                                actions│
        ┌───────────┴───────────────────────────────────────▼───────────────┐
        │  POLARIS   Monitor → Kernel → Reasoner → Verifier → Execution     │
        │            components talk over NATS :4222                        │
        └───────────┬───────────────────────────────────▲───────────────────┘
        OpenAI-compat│ /v1/chat/completions   NATS (read-only)│
        ┌───────────▼───────────────────────────────────┴───────────────────┐
        │  NLA server :8000        target model + AV/AR + web UI             │
        │  dashboard bridge :8090  mirrors NATS traffic to the UI            │
        └───────────┬───────────────────────────────────────────────────────┘
                    │ activation traces
                    ▼
                traces/<run_id>/*.npz        one activation per token
```

Two deliberate boundaries:

- **POLARIS ↔ NLA is plain HTTP.** POLARIS calls the NLA server as an ordinary
  OpenAI-compatible LLM endpoint, so it needs no NLA-specific code. This also
  keeps the dependency sets apart: POLARIS's venv has `nats`/`grpc` and no
  `torch`; NLA's has `torch`/`transformers` and no `nats`.
- **Activations move as files, not function calls.** The NLA server writes every
  token's residual-stream activation to `traces/`; explaining them is a separate
  pass. That is not just tidiness — at 12B the target model (~24 GB) and the
  AV/AR pair (~40 GB) do not fit on a 48 GB workstation together, so collection
  and explanation *have* to be separable.

## Getting started

### Prerequisites

- **Docker** (SWIM and NATS run as containers)
- **tmux** (POLARIS runs its 9 components in a tmux session)
- **Python 3.12+**, and a GPU if you want reasonable speed
- The trained AV/AR checkpoint pair — see [NLA/models/README.md](NLA/models/README.md)

### One-time setup

Two virtualenvs, deliberately separate (their dependencies conflict in spirit if
not in fact, and each subproject must stay runnable alone):

```bash
# POLARIS
python3 -m venv POLARIS/.venv
POLARIS/.venv/bin/pip install -r POLARIS/polaris_poc/requirements.txt

# NLA  (torch build is host-specific; never copy this venv between machines)
python3 -m venv NLA/.venv
NLA/.venv/bin/pip install -r NLA/requirements.txt
```

Put the trained checkpoints in `NLA/models/<backbone>/{av,ar}.pt`. For the
0.5B reproduction:

```bash
mkdir -p NLA/models/Qwen2.5-0.5B
rsync -avP <user>@<workstation>:'~/NLA/NLA_reproduce/models/*.pt' NLA/models/Qwen2.5-0.5B/
```

### Run everything

```bash
./start.sh          # NLA server + bridge + SWIM + POLARIS
./stop.sh           # stop all of it
```

Then open:

| | |
|---|---|
| http://localhost:8000/ | **Activation Inspector** — chat with the target model, click any token, read the AV's explanation of its activation |
| http://localhost:8000/architecture.html | **Architecture view** — the POLARIS/SWIM control loop with live component activity, SWIM telemetry, and routing |
| http://localhost:8000/docs | API docs |
| http://localhost:6901/ | SWIM's own noVNC display |
| `tmux attach-session -t polaris-swim` | POLARIS's 9 components, one per window |

Useful flags:

```bash
./start.sh --only nla              # just the NLA server + bridge, no POLARIS/SWIM
./start.sh --only polaris          # just SWIM + POLARIS
./start.sh --device cpu            # force CPU (useful when the GPU is busy)
./start.sh --model Qwen/Qwen2.5-7B # different backbone (needs its own checkpoints)
./stop.sh --rm                     # also delete the SWIM/NATS containers
```

Service logs and pidfiles go to `run/` (gitignored). POLARIS's own component
logs stay in `POLARIS/polaris_poc/logs/`.

### First run notes

- The NLA server downloads model weights on first start (~1 GB for
  Qwen2.5-0.5B) into `NLA/models/hf/`, and takes 30–60 s to load `T`, `AV` and
  `AR` before it answers. `start.sh` waits for it.
- **The 0.5B model cannot actually drive POLARIS.** It is a base model, not
  instruction-tuned, and POLARIS's reasoner expects `TOOL_CALL:` lines and JSON
  actions. Expect no valid tool calls and no parseable decision. That is fine —
  locally this setup verifies *plumbing*: that POLARIS reaches the model, that
  activations are captured, that traces land on disk and can be explained. A
  larger backbone on better hardware is what produces meaningful decisions.
- Nothing in either UI is mocked. If a service is down, the page says so rather
  than showing stale or invented numbers.
- **On a small GPU, watch VRAM.** POLARIS's prompts run to a couple of thousand
  tokens, far longer than anything the UI sends. `T`+`AV`+`AR` are ~2.8 GB
  resident at 0.5B, and a 1400-token call peaks around 3.1 GB — which fits a
  4 GB card, but not with much to spare. If you hit `CUDA out of memory`, run
  the server on CPU (`./start.sh --device cpu`); it is slower but unconstrained.

## Verifying the pieces

```bash
# NLA end to end: hook → AV → AR, with a shuffled-explanation control
NLA/.venv/bin/python NLA/scripts/check_roundtrip.py

# POLARIS ↔ NLA: drives the server with POLARIS's own LLM client, checks traces
NLA/.venv/bin/python NLA/scripts/check_polaris_interface.py --url http://localhost:8000/v1
```

## Running each piece alone

Each subdirectory stands on its own, which is what makes them debuggable:

```bash
SWIM/start_swim.sh                                     # managed system only
POLARIS/polaris_poc/start_polaris_swim_system.sh       # SWIM + POLARIS, no NLA
cd NLA && ./.venv/bin/uvicorn server.main:app --port 8000   # NLA only
cd POLARIS/polaris_poc && ../.venv/bin/python src/scripts/dashboard_bridge.py
```

## Where to read next

- [NLA/README.md](NLA/README.md) — the interpretability method, configuration,
  and moving between machines
- [NLA/server/README.md](NLA/server/README.md) — the HTTP API, traces, and how
  POLARIS attaches
- [POLARIS/README.md](POLARIS/README.md) — the adaptation framework
- [PROJECT_PLAN.md](PROJECT_PLAN.md) — research question, phases, open risks

## References

- Pandey, D. et al. *POLARIS: Is Multi-Agentic Reasoning the Next Wave in
  Engineering Self-Adaptive Systems?* 2025. arXiv:2512.04702
- Anthropic. *Natural Language Autoencoders.* 2026.
- Moreno, G. et al. *SWIM: An Exemplar for Evaluation and Comparison of
  Self-Adaptation Approaches for Web Applications.* SEAMS 2018.
