# Running the controller against a model hosted on CSF3

## Topology

```
  laptop                                    CSF3
  ──────                                    ────
  SWIM (docker :4242) ◀──TCP──┐
                              │        login node ──── gpuH compute node
  run_controller.py ──────────┤                             vLLM :8000
        │                     │                                  ▲
        └── HTTP :8000 ───────┴──── ssh -L 8000:<node>:8000 ──────┘
```

**One forward tunnel, no reverse tunnel.** The controller is a *client* to both
sides: it opens TCP to SWIM on localhost and HTTP to the model through the
tunnel. Nothing on CSF ever needs to reach back. (POLARIS needed a reverse
tunnel only because the NLA server pushed to its dashboard bridge; CONTROLLER has
no such component.)

The model runs on a Slurm-allocated **compute** node, not the login node, so the
tunnel forwards through the login node to that node by name.

## Why SWIM stays on the laptop for now

SWIM ships only as a Docker image (`gabrielmoreno/swim`) running a VNC desktop
plus OMNeT++ 5.4.1. HPC sites do not run Docker; `recon.sh` checks whether
Apptainer is available, which could run the image, and building OMNeT++ 5.4.1
from source on CSF is possible but a project in itself.

For a single run it buys nothing. The controller makes **one HTTP call per 60 s
period** — a few kB against a 60 s budget — so tunnel latency is irrelevant.

The real argument for moving SWIM onto CSF is *unattended repeats*: a run is 105
minutes of wall clock (`cSocketRTScheduler` pins the simulation to real time),
and ≥5 runs per condition means the laptop must stay awake and connected for
most of a day. Worth solving before the repeat campaign, not before the first
run.

## Procedure

```bash
# 1. laptop: open the multiplexed master (needs your password + DUO)
ssh -M -S ~/.ssh/csf3-long.sock -o ControlPersist=12h -fN \
    t95317ha@csf3.itservices.manchester.ac.uk

# 2. survey what CSF already has (read-only)
ssh -S ~/.ssh/csf3-long.sock t95317ha@csf3.itservices.manchester.ac.uk \
    'bash -s' < recon.sh

# 3. submit the server job
ssh -S ~/.ssh/csf3-long.sock t95317ha@... 'cd ~/selas && sbatch csf/serve_llm.sbatch'

# 4. wait for the endpoint file, then read the node name
ssh -S ~/.ssh/csf3-long.sock t95317ha@... 'cat ~/h200-scratch/endpoints/latest.json'

# 5. open the tunnel to that compute node (leave running)
ssh -L 8000:<node>:8000 t95317ha@csf3.itservices.manchester.ac.uk

# 6. laptop: SWIM, then the controller
../../SWIM/start_swim.sh
../run_controller.py --policy llm --backend openai \
    --llm-base-url http://localhost:8000/v1 --llm-model csf-llm
```

## Resource arithmetic

`meta-llama/Llama-3.3-70B-*` at bf16 is ~141 GB of weights — one H200 exactly,
with nothing left for KV cache, so **two GPUs** is the minimum sane allocation.

| | |
|---|---|
| partition | `gpuH_short` (≤1 day, batch + interactive) or `gpuH` (≤4 days, batch only) |
| account | `gpu-h200-fse-pgdr` — **required**, job is rejected without `-A` |
| GPUs | `-G 2` → 282 GB VRAM |
| cores | `-n 1 -c 16` (≤8 cores/GPU). `-c` not `-n`: vLLM is one process |
| host RAM | 24 GB/core → 384 GB |
| limits | 4 GPUs and 4 running jobs per user on `gpu-h200-fse*` |

Weights belong on `~/h200-scratch` (1 TB quota, H200 nodes + login nodes only).
**No backup and no recovery there** — it is scratch, not storage.

## Which checkpoint (settled)

Every released kitft NLA is fine-tuned from an **instruction-tuned** checkpoint.
Verified 2026-09-16 against the `base_model` field of each model card:

| NLA pair | base model | layer |
|---|---|---|
| `kitft/Llama-3.3-70B-NLA-L53-{av,ar}` | `meta-llama/Llama-3.3-70B-Instruct` | 53 |
| `kitft/nla-gemma3-27b-L41-{av,ar}` | `google/gemma-3-27b-it` | 41 |
| `kitft/nla-gemma3-12b-L32-{av,ar}` | `google/gemma-3-12b-it` | 32 |
| `kitft/nla-qwen2.5-7b-L20-{av,ar}` | `Qwen/Qwen2.5-7B-Instruct` | 20 |

So `meta-llama/Llama-3.3-70B-Instruct` is what to download, and it is the same
checkpoint the interpretability layer will need later — one 141 GB download, not
two. `NLA/src/config.py` previously keyed three of these on the *base* ids
(`-pt`, and bare `Llama-3.3-70B`); corrected in the same commit as this note.
