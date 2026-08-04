# NLA

A from-scratch reproduction of the [Natural Language Autoencoder](https://transformer-circuits.pub/2026/nla/) (Anthropic, 2026) pipeline,
now being repurposed as one of three interpretability lenses in the wider
[SummerWork](../PROJECT_PLAN.md) project.

Reference code: [kitft/natural_language_autoencoders](https://github.com/kitft/natural_language_autoencoders).
See [METHOD_PIPELINE.md](METHOD_PIPELINE.md) for a stage-by-stage walkthrough with
implementation notes and divergences from the paper, and [REPRODUCE_LOG.md](REPRODUCE_LOG.md)
for the issues found while reproducing it.

## What this is for

The parent project asks whether the choice of interpretability method determines
which *stakeholder* an explanation can serve — specifically, whether probing an
LLM's activations can move a self-adaptive system from being merely
explainable-in-principle toward explanations a non-technical stakeholder (a
clinician, an auditor) can actually act on.

The LLM in question is the reasoning core of a self-adaptation layer: it decides
how a managed system should adapt (which service to call, which knob to turn) in
response to runtime telemetry. Three lenses get pointed at the same decision —
tuned logit lens, sparse autoencoders, and this. NLA is the one whose output is
plain prose rather than features needing expert labelling, which is exactly why
it is the interesting case and also why its *faithfulness* has to be measured
rather than assumed.

Concretely, this repo supplies:

- **the activation hook** — `src/data.py` captures the residual stream at the
  probe layer, which is how runtime traces get collected from the reasoning
  model during an adaptation run;
- **the AV/AR pair** — turns one of those activations into a natural-language
  explanation and scores how much of the activation that explanation actually
  recovers (FVE);
- **the demo server** — `server/` holds the model resident and exposes
  tokenise/analyse over HTTP, so the adaptation layer can talk to it without
  sharing a Python environment.

The reproduction ran on Qwen2.5-0.5B (the paper uses 7B) to fit the GPU budget,
reaching e2e FVE **0.594** against the paper's ≈0.75. That model is now the
*plumbing* target: small enough to exercise the whole loop on a 4 GB laptop GPU,
while the real runs use a larger backbone with a released checkpoint pair. See
[Configuration and moving between machines](#configuration-and-moving-between-machines).

---

## Quick start

```bash
# 1. Create environment (per machine -- .venv is gitignored, see below)
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# If the default PyPI wheel picks the wrong CUDA, install torch first from the
# matching index (replace cu121 with your version: nvcc --version), then rerun
# the line above:
#   pip install torch --index-url https://download.pytorch.org/whl/cu121

# 2. Verify GPU
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# A C compiler is expected (sudo apt install build-essential). torch >= 2.13
# dispatches some ops to triton, which JIT-compiles a C shim on first use --
# without one, every forward pass fails. src/compat.py detects this and falls
# back to eager, but installing the compiler is the real fix.

# 3. Run stages in order
python scripts/phase00_load_model.py          # sanity check

./scripts/run_generate_data.sh                # Stage 0: extract 100K activations

export DEEPSEEK_API_KEY=sk-...
./scripts/run_generate_summaries.sh           # Stage 1: generate explanations

./scripts/run_ar_pretraining.sh               # Stage 2: AR warm-start

./scripts/run_av_warmstart.sh                 # Stage 3: AV warm-start

./scripts/run_grpo.sh                         # Stage 4: GRPO joint training
```

Model weights (~1 GB for Qwen2.5-0.5B) are downloaded automatically from HuggingFace on first run.

---

## Configuration and moving between machines

Nothing in the codebase hardcodes a model, layer, or dtype — everything that varies
per machine or per backbone lives in [src/config.py](src/config.py) and is
environment-overridable:

| Variable | Default | Notes |
|---|---|---|
| `NLA_MODEL_ID` | `Qwen/Qwen2.5-0.5B` | HuggingFace repo of the target model `T` |
| `NLA_PROBE_LAYER` | looked up in `PROBE_LAYERS` | the layer is a property of the released AV/AR, not a free choice |
| `NLA_DTYPE` | `auto` | `auto` picks bf16 where supported, else fp16 (Turing has no native bf16) |
| `NLA_DEVICE` | `cuda` if available | `auto` shards across all visible GPUs — needed for a 12B target on 2× 24 GB |

The three target machines:

| | Hardware | Typical use |
|---|---|---|
| local dev box | GTX 1650 Ti, 4 GB, Turing (sm_75) | plumbing only — Qwen2.5-0.5B in fp16 |
| workstation | 2× RTX 4090, 24 GB each, Ada | run the target model, collect runtime traces |
| CSF | 4× H200, 141 GB each, Hopper | NLA training at scale |

**Porting between them is `git pull` + a fresh `.venv`, never a copy of the tree.**
The venv is deliberately gitignored: the torch build is tied to the host's CUDA
version and GPU architecture, so a copied one will not work.

The large artifacts (`activations/`, `checkpoints/`, `models/`) are gitignored too
and move separately with `rsync` — resumable, so a dropped ssh connection costs
nothing:

```bash
# pull the trained 0.5B checkpoint pair down from the workstation
mkdir -p models/Qwen2.5-0.5B
rsync -avP harry@mingfei-workstation-76:'~/NLA/NLA_reproduce/models/*.pt' \
    models/Qwen2.5-0.5B/
```

`-P` is `--partial --progress`: re-running the same command resumes rather than
restarting. Add `-z` if the link is slow (`.pt` files are already fairly dense,
so it usually is not worth the CPU).

HuggingFace downloads go to `models/hf` (set as `HF_HOME` by `src/config.py`),
so they stay inside the project rather than `~/.cache`. See
[models/README.md](models/README.md) for the layout.

Backbones with a released NLA checkpoint pair
([kitft/nla-models](https://huggingface.co/collections/kitft/nla-models)) are
listed with their probe layers in `PROBE_LAYERS` in `src/config.py`.

---

## Serving POLARIS

The server does more than host the demo: it is the LLM backend POLARIS reasons
with. It exposes an OpenAI-compatible `/v1/chat/completions`, so POLARIS calls
it as an ordinary provider with no NLA-specific code, and every call is captured
as an activation trace.

```
POLARIS reasoner ──HTTP /v1/chat/completions──> NLA server ──> traces/<run_id>/
```

That HTTP boundary is deliberate: POLARIS's virtualenv keeps `nats`/`grpc` and
no `torch`, this one keeps `torch`/`transformers` and no `nats`, and each stays
installable and runnable alone. Traces then move as *files* rather than function
calls, because at 12B the target model (~24 GB) and the AV/AR pair (~40 GB) do
not fit on a 48 GB workstation together — collection and explanation have to be
separable passes.

Full details, endpoints and trace format: [server/README.md](server/README.md).
To run the whole setup (SWIM + POLARIS + this server) use
[`../start.sh`](../start.sh).

Verify the interface end to end — this drives the server using POLARIS's *own*
LLM client, then checks a trace was written with one activation per token:

```bash
./.venv/bin/python scripts/check_polaris_interface.py --url http://localhost:8000/v1
```

---

## Demo (web UI)

Two pages, served by the same process.

**Activation Inspector** (`/`) — three columns:

1. **Chat** (left) — type a message, the target model generates with the chosen
   sampling settings. "New chat" resets the conversation.
2. **Model context** (middle) — every token the target model actually sees, with
   the chat template applied. Special tokens (`<|im_start|>`, …) are highlighted.
   Clicking a token selects it and faintly shades everything before it (the
   activation at token *i* depends on tokens 0…*i*).
3. **Inspector** (right) — the AV's explanation of the selected token's
   activation, plus:
   - **Reconstruction (cosine)** — angle between AR's prediction and the
     sqrt-d-normalised activation. Bounded [−1, 1], higher is better.
   - **Per-sample FVE** — 1 − ‖a − â‖² / ‖a − ā‖², with ā the corpus-mean
     activation (needs `activations/dataset`; reported as `n/a` otherwise).
     Same definition as the corpus FVE in [REPRODUCE_LOG.md](REPRODUCE_LOG.md).

   A **Config** tab shows the backbone, probe layer and checkpoint paths in use.
   Worth checking — a mismatched AV/AR pair still produces confident-looking
   prose.

**Architecture** (`/architecture.html`) — the POLARIS/SWIM control loop, showing
where this fits as a Reasoner tool. With POLARIS's dashboard bridge running it
also shows live component activity, SWIM telemetry and routing; without it, the
page says so and stays structural.

Nothing in either page is mocked. When a service is down the UI reports that
rather than showing stale or invented numbers.

```bash
# Once: copy your best GRPO checkpoints into this backbone's models/ subdirectory
mkdir -p models/Qwen2.5-0.5B
cp checkpoints/grpo_av_step1000.pt models/Qwen2.5-0.5B/av.pt
cp checkpoints/grpo_ar_step1000.pt models/Qwen2.5-0.5B/ar.pt

# Run the server (binds 0.0.0.0:8000 so it's reachable over SSH/LAN)
./.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/` in a browser. The first request takes a few seconds while the
models load; `GET /api/health` confirms `"status": "ok"`.

**Running on a remote machine over SSH?** Forward the port from your laptop:

```bash
ssh -L 8000:localhost:8000 your-user@<linux-box-host>
```

Then `http://localhost:8000` in your local browser reaches the remote server. See
[server/README.md](server/README.md) for the JSON API.

> **Note.** The target model is **base** Qwen2.5-0.5B (not Instruct), because the AV/AR were
> trained on base-model activations. Chat-template generation will work but produce incoherent
> responses — the demo is for inspecting *activations*, not for chatting.

---

## Directory structure

```
NLA_reproduce/
├── README.md
├── METHOD_PIPELINE.md            # detailed stage-by-stage pipeline documentation
├── REPRODUCE_LOG.md              # issues found and fixed during reproduction
├── requirements.txt
├── src/                          # shared library
│   ├── config.py                 #   MODEL_ID, PROBE_LAYER, DEVICE, DTYPE, paths, AR/AV prompts
│   ├── compat.py                 #   environment workarounds applied at import
│   ├── model.py                  #   load_target(), load_tokenizer(), decoder_stack()
│   ├── data.py                   #   activation extraction, ActivationDataset
│   ├── ar.py                     #   Reconstructor: text → â ∈ ℝ⁸⁹⁶
│   ├── av.py                     #   Verbalizer: h_l → text (㊗ injection, full 24-layer)
│   └── train.py                  #   train_ar(), train_av(), train_grpo(), eval_e2e_fve(), fve()
├── scripts/                      # entry points — run via shell scripts
│   ├── phase00_load_model.py     #   verify GPU and model load
│   ├── check_roundtrip.py        #   end-to-end T→AV→AR check, with baselines
│   ├── check_polaris_interface.py#   POLARIS's own LLM client against this server
│   ├── generate_data.py          #   Stage 0: build (text, activation) dataset (shard-safe)
│   ├── generate_summaries.py     #   Stage 1: LLM explanation generation
│   ├── train_ar_baseline.py      #   Stage 2: AR warm-start
│   ├── train_warmstart.py        #   Stage 3: AV warm-start
│   ├── train_grpo.py             #   Stage 4: joint GRPO training
│   ├── eval_fve_compare.py       #   compare e2e FVE between two checkpoint pairs
│   ├── run_generate_data.sh      #   Stage 0 runner (100K)
│   ├── run_generate_rl_data.sh   #   Stage 0 runner (1M, for RL; shard-safe, crash-resumable)
│   ├── run_generate_summaries.sh #   Stage 1 runner
│   ├── run_ar_pretraining.sh     #   Stage 2 runner
│   ├── run_av_warmstart.sh       #   Stage 3 runner
│   └── run_grpo.sh               #   Stage 4 runner
├── activations/                  # datasets — gitignored
│   ├── dataset/                  #   100K (text, activation) pairs + summaries
│   └── rl_dataset/               #   1M activation-only pairs for GRPO (in progress)
├── checkpoints/                  # raw training outputs — gitignored
│   ├── ar_baseline.pt            #   AR after Stage 2 warm-start (FVE 0.47)
│   ├── av_warmstart.pt           #   AV after Stage 3 warm-start (best val_loss epoch)
│   ├── grpo_av_step1000.pt       #   AV after 1000 GRPO steps — best result (FVE 0.594)
│   └── grpo_ar_step1000.pt       #   AR after 1000 GRPO steps — best result
├── models/                       # HF downloads + served checkpoints — gitignored
│   ├── hf/                       #   HF_HOME (HuggingFace cache)
│   └── Qwen2.5-0.5B/             #   one subdirectory per backbone
│       ├── av.pt                 #     copy of grpo_av_step1000.pt
│       └── ar.pt                 #     copy of grpo_ar_step1000.pt
├── server/                       # FastAPI server
│   ├── main.py                   #   routes: /api/*, /v1/chat/completions
│   ├── inference.py              #   NLAInference: chat, analyze, activations_for
│   ├── traces.py                 #   TraceWriter / load_trace
│   └── README.md
└── frontend/                     # static client — no build tools
    ├── index.html                #   Activation Inspector
    ├── app.js
    ├── architecture.html         #   POLARIS/SWIM control loop view
    ├── architecture.js
    ├── architecture.css
    └── styles.css
```

Traces are written outside this directory, to `../traces/<run_id>/` — they are
the shared artifact of a POLARIS run and this pipeline, owned by neither.

---

## Key design choices

**Why Qwen2.5-0.5B?** The paper uses 7B, which requires ~84GB for full-model SFT — beyond the 48GB available (2× RTX 4090). The 0.5B model fits comfortably and the pipeline is otherwise identical. It remains the plumbing target: at ~1.8 GB for `T`+`AV`+`AR` resident it exercises the whole loop on a 4 GB card, so wiring can be debugged locally before anything is run on the workstation.

**Backbone choice for the real runs.** Only backbones with a released AV/AR pair are candidates, since training a fresh one at scale is a separate project. Of those, Qwen2.5-7B is the only one where the target *and* both halves of the NLA fit resident on 2× 24 GB (14 + 16 + 10 ≈ 40 GB); Gemma-3-12B (24 + 24 + 16 ≈ 64 GB) does not, and forces the staged flow — run `T` to collect activations, then load AV/AR separately to explain them. That staging is the reason activation traces are written to disk rather than explained in-process.

**Why DeepSeek V4-Flash for explanations?** The paper uses Claude Opus 4.5; the reference codebase uses Claude Haiku. DeepSeek V4-Flash is cost-equivalent to Haiku (~$4/100K explanations vs ~$75 for Opus) and follows structured prompts reliably.

**Why truncate AR to layer 16?** The AR needs to output the raw residual stream at the probe layer. Truncating the base transformer to layers 0..16 and replacing the final norm with `nn.Identity()` makes `last_hidden_state` the exact quantity the forward hook captured — no further mapping needed.

**FVE gap vs paper (0.594 vs 0.75):** The gap is primarily model capacity — a 0.5B residual stream at layer 16 encodes less recoverable information than a 7B stream at layer 20, and the AV/AR have less generative capacity. Description quality (2–3 features vs paper's 4–5) is a secondary factor. See REPRODUCE_LOG.md for the full analysis.
