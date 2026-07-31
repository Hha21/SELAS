# POLARIS + NLA Dashboard — Plan for New Repo

> Goal: extend POLARIS with Natural Language Autoencoder (NLA) interpretability of
> the agentic reasoner, plus a dashboard that visualises agent activity and lets
> you click into reasoning tokens to see NLA explanations. Build on the
> sa4s-serc/POLARIS refactor, run locally on a 4090 workstation.

---

## 1. Repo bootstrap

```bash
# On the workstation
git clone https://github.com/sa4s-serc/POLARIS.git polaris-nla
cd polaris-nla
git remote rename origin upstream            # keep their main as upstream
gh repo create Hha21/polaris-nla --private --source=. --push
# or manually:
#   git remote add origin git@github.com:Hha21/polaris-nla.git
#   git push -u origin main
git checkout -b nla-integration
```

Rationale: clone-then-rename-origin keeps you on the refactor's `polaris` branch
and lets you `git fetch upstream` later for their fixes. Don't fork in the GitHub
UI — you said you want a *new* repo, not a public fork.

---

## 2. Workstation environment (RTX 4090, 24 GB)

- CUDA 12.x + recent NVIDIA driver (≥550)
- Python env via `uv` (faster than conda for this):
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  uv venv --python 3.11
  source .venv/bin/activate
  uv pip install -r requirements.txt
  ```
- Inference stacks:
  - **vLLM** for serving Qwen as POLARIS's reasoner (OpenAI-compatible endpoint)
  - **SGLang** for the NLA AV (this is what `nla_inference.py` uses)
  - Pick one base model: **Qwen 2.5-7B-Instruct** is the smallest with an NLA — runs comfortably in BF16 on a 4090.
- Docker for SWIM + NATS (same as the reproduction here)

---

## 3. Swap agentic reasoner: Gemini → local Qwen 2.5-7B

sa4s-serc already has provider abstraction, so this is a config change, not a code change:

1. Serve Qwen via vLLM:
   ```bash
   vllm serve Qwen/Qwen2.5-7B-Instruct \
     --host 0.0.0.0 --port 8000 \
     --max-model-len 8192 \
     --dtype bfloat16
   ```
2. Point POLARIS config at it (the field name will be `provider: openai_compatible` or similar — confirm in their config schema):
   ```yaml
   llm:
     provider: "openai_compatible"
     api_base: "http://localhost:8000/v1"
     model_name: "Qwen/Qwen2.5-7B-Instruct"
   ```
3. **Sanity run**: trigger one SWIM cycle, confirm Qwen returns the expected JSON-ish action.
   Latency must be < the 60s evaluation period — vLLM on a 4090 should hit ~5–15s for ~1k-token responses.

---

## 4. NLA setup (standalone first)

Before wiring NLA into POLARIS, get it working end-to-end on toy data:

1. Clone the NLA repo alongside:
   ```bash
   git clone https://github.com/kitft/natural_language_autoencoders.git ../nla
   ```
2. Download the matched checkpoints for Qwen:
   - `kitft/nla-qwen2.5-7b-L20-av` (Activation Verbalizer)
   - `kitft/nla-qwen2.5-7b-L20-ar` (Activation Reconstructor — for QA only)
   - `L20` = layer 20 of the residual stream. Stick with this so explanations match the AV's training.
3. Run their `nla_inference.py` on a parquet of activation vectors you grab manually from Qwen for one prompt.
4. Verify: AV produces a plausible English description; AR reconstructs the vector with low MSE.

---

## 5. Capture activations from POLARIS's reasoner

Now wire activations out of Qwen during a POLARIS run. Two options:

- **Option A — hook vLLM**: vLLM does not expose hidden states by default. You can run a small monkey-patched fork or use the lower-level engine API to dump layer-20 residual stream per-token to disk.
- **Option B — bypass vLLM for this**: serve Qwen with raw `transformers` + a forward hook on layer 20. Lower throughput but easier; fine if POLARIS calls the reasoner ≤ once per 60 s.

For the poster I'd take Option B — fewer moving parts, and the throughput is irrelevant at one call per minute. Write a tiny FastAPI wrapper around Qwen that:
- Accepts a prompt
- Runs generation
- Returns `{response_text, tokens, activations_path}` where `activations_path` points to an npz/parquet on disk

Then point POLARIS's `openai_compatible` provider at this wrapper (mimic the chat-completions response shape).

---

## 6. NLA explanations as a background worker

Don't block POLARIS waiting on AV inference. Architecture:

```
Qwen wrapper ──writes──► /activations/<run_id>/<step_id>.parquet
                           │
                           ▼
            NLA worker (SGLang serving AV) ──writes──► /explanations/<run_id>/<step_id>.json
```

The worker:
- Watches the activations directory
- For each new file, calls the AV on each token's vector
- Writes `{tokens: [...], explanations: [...], reconstruction_mse: [...]}` to JSON

This decouples explanation latency from reasoner latency.

---

## 7. Dashboard (the poster artifact)

```
┌─────────────────────────────────────────────────────────────┐
│  POLARIS                                  [run: nla-001]    │
├─────────────────────────────────────────────────────────────┤
│       Monitor               Verification                    │
│           ╲                    ╱                            │
│       Digital Twin → [ KERNEL ] → Execution                 │
│           ╱                    ╲                            │
│       Agentic Reasoner       Meta-Learner                   │
└─────────────────────────────────────────────────────────────┘
```

**Stack**: Vite + React + Tailwind + shadcn/ui (pretty fast, polished look).

**Layout**:
- Central kernel node, 6 agents arranged radially. Edges showing data flow.
- Each agent has a status light (idle/working/error) driven by recent log activity.

**Interaction**:
- Click agent → right-hand side panel slides out
- Tabs (depend on agent type):
  - `Activity` — recent log lines (all agents)
  - `Reasoning` — prompt + response with tokens as clickable chips (LLM agents only)
  - `NLA` — per-token explanations from the AV (LLM agents only)
- Click a token chip in `Reasoning` → `NLA` tab updates with that token's explanation, reconstruction MSE, top-k nearest concepts

**Backend**:
- Tiny FastAPI server (`dashboard/server.py`)
- Endpoints:
  - `GET /agents` — list agents + status
  - `GET /agents/{id}/log?since=...` — log tail (read POLARIS log files or NATS subscribe)
  - `GET /reasoning/{step_id}` — prompt + response + token list
  - `GET /nla/{step_id}` — full explanation payload for a reasoning step
- SSE or websocket for live updates if you have time

**Data source v1**: tail the JSONL log files POLARIS already writes. Don't bother with a NATS subscriber unless v1 ships and you have spare hours.

---

## 8. Build order (least surprise → most reward)

1. Get sa4s-serc/POLARIS running on workstation with their default Ollama-backed local model. **Don't touch anything else yet.** Confirm a full SWIM cycle completes.
2. Swap to Qwen 2.5-7B via vLLM. Re-run SWIM. Compare scaling decisions to the Gemini reproduction in this repo as a sanity check.
3. Standalone NLA on toy activations.
4. Qwen wrapper that dumps layer-20 activations per call.
5. NLA worker that turns activations → explanations.
6. Dashboard frontend with **mocked** JSON (build the UI without the backend so visual iteration is fast).
7. Dashboard backend that reads the real log/explanation files.
8. End-to-end run for the poster screenshot/video.

---

## 9. Poster story

Two-plot comparison:

| | gemini-2.5-flash (this repo) | Qwen 2.5-7B + NLA (new) |
|---|---|---|
| Total utility | 3303 | TBD |
| % late | 1.0% | TBD |
| Interpretability | none | per-token NLA |

Plus a dashboard screenshot showing the agentic reasoner panel mid-reasoning, with one token expanded to its NLA explanation. Narrative: *"reproduced POLARIS as published, then made the reasoning legible by swapping in an interpretable model with NLA."*

---

## 10. Risks worth pre-mortem'ing

- **Qwen latency under load**: 4090 + vLLM should comfortably do ~50 tok/s for 7B BF16, i.e. ~5–10 s per reasoner call. Fine. If you quantise (AWQ/GPTQ Int4) it's faster but the NLA checkpoints were trained on the full-precision base — quantisation may degrade explanation quality. **Don't quantise the reasoner; use BF16.**
- **VRAM budget**: Qwen 2.5-7B BF16 ≈ 14 GB. AV is also Qwen-7B-based ≈ another 14 GB. Both at once won't fit on a 4090. Either (a) swap between them, (b) run AV on CPU (slow but fine for offline worker), or (c) run AV via SGLang on the same GPU after the reasoner finishes the step.
- **POLARIS log schema**: confirm what sa4s-serc actually emits before designing the dashboard's data layer. Add structured-log fields if needed; their refactor should be hospitable to this.
- **Reproducibility**: when you swap the reasoner model, you *will* see different scaling decisions. Run multiple seeds and report median, not a single run.

---

## 11. Files you'll likely add/touch

```
polaris-nla/
├── plugins/llm_qwen_local.py          # new provider for the FastAPI Qwen wrapper
├── interpretability/
│   ├── qwen_server.py                  # FastAPI Qwen wrapper, dumps activations
│   ├── nla_worker.py                   # consumes activations, calls AV
│   └── README.md
├── dashboard/
│   ├── frontend/                       # Vite + React app
│   ├── server.py                       # FastAPI backend
│   └── README.md
└── config/swim_qwen_nla.yaml           # POLARIS config pointing at local Qwen
```
