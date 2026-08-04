# NLA server

FastAPI server that holds the target model `T`, the Verbalizer `AV` and the
Reconstructor `AR` resident, and does three jobs:

1. **Serves the LLM that POLARIS reasons with** — an OpenAI-compatible
   `/v1/chat/completions` endpoint, so POLARIS talks to it as an ordinary
   provider and needs no NLA-specific code.
2. **Captures activation traces** — every token of every call, written to
   `traces/<run_id>/` for offline explanation.
3. **Serves the web UI** — the Activation Inspector and the architecture view.

## Run

Usually via [`../../start.sh`](../../start.sh). Standalone:

```bash
cd NLA
./.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
```

Requires the checkpoint pair at `models/<backbone>/{av,ar}.pt` — see
[../models/README.md](../models/README.md). Startup takes 30–60 s while the
three models load; `GET /api/health` reports `"status": "ok"` when ready.

Over SSH, forward the one port:

```bash
ssh -L 8000:localhost:8000 <user>@<host>
```

## Configuration

All from the environment, resolved in [`../src/config.py`](../src/config.py):

| Variable | Default | Effect |
|---|---|---|
| `NLA_MODEL_ID` | `Qwen/Qwen2.5-0.5B` | backbone for `T`/`AV`/`AR` |
| `NLA_PROBE_LAYER` | per-backbone lookup | layer the hook reads |
| `NLA_DEVICE` | `cuda` if present | `cpu`, or `auto` to shard across GPUs |
| `NLA_DTYPE` | `auto` | bf16 where natively supported, else fp16 |
| `NLA_MAX_NEW_TOKENS` | `256` | hard cap on generation length |
| `NLA_TRACE_DIR` | `../../traces` | where traces are written |
| `NLA_RUN_ID` | timestamp | groups one run's traces |
| `NLA_CAPTURE` | `1` | `0` disables trace capture |
| `POLARIS_BRIDGE_URL` | `http://127.0.0.1:8090` | dashboard bridge to proxy |

`NLA_MAX_NEW_TOKENS` matters more than it looks: POLARIS's SWIM config asks for
`max_tokens: 4096`, and a base model with no EOS discipline will generate all of
it. The server caps rather than honouring that.

## API

### `GET /api/health`

Reports the live configuration — backbone, probe layer, `d_model`, dtype,
device, both checkpoint paths, the FVE baseline, and trace status. Worth
checking: a mismatched AV/AR pair or a wrong probe layer still produces fluent,
confident-looking prose, so the values actually in use need to be visible.

### `POST /v1/chat/completions`

OpenAI-compatible. This is what POLARIS calls.

```bash
curl -s localhost:8000/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "messages": [{"role": "user", "content": "response_time=912ms. Next action?"}],
  "max_tokens": 64, "temperature": 0.3
}'
```

Accepts `messages`, `temperature`, `max_tokens`, `top_p`, `model`; returns
`choices[0].message.content` and a `usage` block. `stream: true` is rejected
with a 400. There is no `tools` support and none is needed — POLARIS parses
tool calls out of the response text (`TOOL_CALL:` / `PARAMETERS:` lines).

### `POST /api/chat`

The UI's richer variant: same generation, but also returns `token_ids`,
`tokens`, `is_special` and `assistant_token_start`, so the frontend can render
and click individual tokens.

### `POST /api/analyze`

Explain one token's activation. Body takes `token_ids` (preferred — no
tokenisation round-trip) or `text`, plus `position` (negative counts from the
end). Returns the AV's `explanation`, the AR `reconstruction` cosine, and
per-sample `fve` (`null` unless `activations/dataset` is present to supply the
corpus-mean baseline).

### `POST /api/tokenize`

`{"text": "..."}` → `{"tokens": [...]}`.

### `GET /api/polaris/state`

Proxies POLARIS's [dashboard bridge](../../POLARIS/polaris_poc/src/scripts/dashboard_bridge.py)
so the frontend stays same-origin (one SSH tunnel, no CORS). Returns
`connected: false` with the reason when the bridge is not running — never stale
or invented values.

Auto-generated docs: <http://localhost:8000/docs>.

## Traces

Every `/v1/chat/completions` call writes:

```
traces/<run_id>/
    req-00001.npz     float16 activations, shape (seq, d_model)
    req-00001.json    messages, completion, tokens, usage, config
```

One activation per token, prompt and completion alike, at the probe layer.

Three design points worth knowing:

**Captured in one pass after generation.** Attention is causal, so position *i*
depends only on tokens 0…*i* — forwarding the whole sequence once and reading
every position gives numerically the same vectors as forwarding each prefix
separately (verified: cosine ≥ 0.999998), at O(n) rather than O(n²) cost.
Capturing *during* generation would avoid the extra pass but silently misses the
final token's activation, since nothing is ever fed after the last sampled token
— and that is usually the most interesting one, being the end of the decision.

**The forward skips the LM head.** `_run_body()` calls the decoder stack
directly rather than the full causal LM. The logits tensor is `seq × vocab`,
~300 KB per token at Qwen2.5's 151936 vocab — 600 MB for a 2000-token POLARIS
prompt, purely to be discarded. Computing it is what put a 4 GB card into CUDA
OOM.

**Writes never fail a call.** Trace capture is wrapped so an error there cannot
take down the LLM request POLARIS is blocking on; failures surface through
`/api/health` instead.

Read a trace back with `server.traces.load_trace()`, which returns the metadata
plus activations as a float32 `(seq, d)` array. Explaining a trace needs only
`AV` and `AR`, not the target model — which is what makes collection and
explanation separable across machines, and is required at 12B where the target
(~24 GB) and the AV/AR pair (~40 GB) do not fit on 48 GB together.

## Checks

```bash
# T → AV → AR round trip, with a shuffled-explanation control
./.venv/bin/python scripts/check_roundtrip.py

# POLARIS's own LLM client against this server, plus trace verification
./.venv/bin/python scripts/check_polaris_interface.py --url http://localhost:8000/v1
```
