# POLARIS Reproducibility Work Log

**Paper:** POLARIS: Proactive Optimization & Learning Architecture for Resilient Intelligent Systems (SEAMS 2025)  
**Repo:** https://github.com/prakhar479/POLARIS

---

## 11/06/26

### Getting the system running

**Prerequisites:**
- Docker Desktop running (on WSL, must be started from Windows side)
- Python venv at `.venv/` — activate before running anything
- Gemini API key set as `GEMINI_API_KEY` env var

**Steps to start a run:**

1. Start the SWIM Docker container (if not already running):
   ```bash
   docker run -d --name swim -p 4242:4242 -p 5901:5901 -p 6901:6901 gabrielmoreno/swim
   ```

2. Start the NATS message broker:
   ```bash
   docker run -d --name polaris-nats -p 4222:4222 nats:latest
   ```

3. Start the SWIM OMNeT++ simulation inside the container (must be done manually — the container only auto-starts a VNC desktop, not the simulation itself):
   ```bash
   docker exec -d swim bash -c "cd /headless/seams-swim/swim/simulations/swim && PATH=/opt/omnetpp-5.4.1/bin:\$PATH LD_LIBRARY_PATH=/opt/omnetpp-5.4.1/lib:\$LD_LIBRARY_PATH ./run.sh sim 0"
   ```

4. Start all POLARIS components via the startup script:
   ```bash
   cd polaris_poc
   ./start_polaris_swim_system.sh
   ```
   This creates a tmux session (`polaris-swim`) with one window per component. Attach with:
   ```bash
   tmux attach-session -t polaris-swim
   ```

**Installed missing dependencies (not in original requirements):**
```bash
pip install google-generativeai filterpy
```

---

### Issues encountered

**`gemini-2.0-flash` no longer available (404 NOT_FOUND)**

The paper's codebase uses `gemini-2.0-flash` for the agentic reasoner. As of June 2026, Google has removed this model:

```
404 NOT_FOUND: This model models/gemini-2.0-flash is no longer available.
Please update your code to use a newer model.
```

**Fix:** The model string `"gemini-2.0-flash"` was hardcoded in 4 source files as default parameter values, as well as in the config. All updated to `"gemini-2.5-flash"`:

- `polaris_poc/src/config/agentic_reasoner_config.yaml`
- `polaris_poc/src/polaris/agents/agentic_reasoner.py`
- `polaris_poc/src/polaris/agents/agentic_reasoner_switch.py`
- `polaris_poc/src/polaris/agents/llm_reasoner_gemini.py`
- `polaris_poc/src/polaris/agents/meta_learner_llm.py`

---

## 12/06/26

### Meta-learner SDK migration (`google.generativeai` → `google.genai`)

The meta-learner was failing on every cycle with `400 API_KEY_INVALID`. Two compounding bugs:

1. **Hardcoded placeholder key**: `meta_learner_llm.py` line 87 set `self.api_key = "YOUR API KEY"`, ignoring the passed parameter and the `GEMINI_API_KEY` environment variable entirely.
2. **Deprecated SDK**: The file imported `google.generativeai` (old SDK, no longer maintained), which uses a gRPC transport that no longer authenticates correctly. The rest of the codebase uses `google.genai` (new SDK, REST-based), which works fine with the same key.

**Fix** — minimal changes to `meta_learner_llm.py`:
- Imports: `import google.generativeai as genai` → `import google.genai as genai`
- Key: `self.api_key = "YOUR API KEY"` → `self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")`
- Client init: `genai.configure(...); genai.GenerativeModel(...)` → `genai.Client(api_key=...)`
- API call: `client.generate_content_async(...)` → `client.aio.models.generate_content(model=..., config=GenerateContentConfig(...))`
- Exception type: `google.api_core.exceptions.GoogleAPIError` → `genai.errors.ClientError`

### Startup script now manages Docker containers

`start_polaris_swim_system.sh` previously required the SWIM and NATS Docker containers to be started manually before running. Updated to handle this automatically:

- Before creating any tmux windows, the script checks whether `polaris-nats` and `swim` containers exist and are running, starting or creating them as needed.
- After starting the SWIM container, waits 8s for the VNC desktop to initialise, then launches the OMNeT++ simulation via `docker exec` and waits for port 4242 to open.
- The NATS tmux window now shows `docker logs -f polaris-nats` rather than attempting a conflicting `docker run`.

**To run a full experiment (updated):**
```bash
export GEMINI_API_KEY="your-key"
cd polaris_poc
./start_polaris_swim_system.sh
```

---

## 13/06/26

### First reproduction run complete

Run label: `SWIM_agentic_flash25_repro1` (gemini-2.5-flash, full POLARIS configuration).

Results copied from the Docker container:
```bash
docker cp swim:/headless/seams-swim/results/SWIM/sim-0.sca polaris_poc/results_swim/results/SWIM_agentic_flash25_repro1/
docker cp swim:/headless/seams-swim/results/SWIM/sim-0.vec polaris_poc/results_swim/results/SWIM_agentic_flash25_repro1/
```

**Key results (evaluation window 900s–6300s):**

| Metric | Value |
|---|---|
| Total utility | 3303 |
| % late responses | 1.0% |
| Avg servers allocated | 3.00 |

The system kept all 3 servers active throughout the run (initialServers=3 = maxServers=3 in this config, so no scaling decisions were taken). One brief SLA violation event occurred around t=4900s where the dimmer was reduced and a response-time spike appeared, but the system recovered quickly.

### Reproduction plot

A 5-panel black/white figure was generated to match Figure 4 of the paper:

```bash
python reproduce/plot_repro.py
# Output: reproduce/repro1_5panel.pdf  and  reproduce/repro1_5panel.png
```

Script: `reproduce/plot_repro.py`  
Output: `reproduce/repro1_5panel.{pdf,png}`

Panels (shared time axis 900s–6300s):
1. requests/s — ClarkNet workload trace, ramps from ~10 to ~60 req/s
2. servers — solid=active, dashed=allocated (both constant at 3)
3. dimmer — stays at 1.0, brief dip to ~0.6 around t=4900s
4. resp. time (s) — well below 0.75s threshold except one spike
5. cum. utility — monotonically increasing, final value ≈ 3303

**Note on pandas:** `pandas` was not in the original requirements. Install if missing:
```bash
pip install pandas
```
