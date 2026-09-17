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

## Working over the connection

`ssh host 'cmd'` starts a **new non-interactive shell every time**. ControlMaster
multiplexes the TCP transport, not a shell session, so there is no long-lived
shell on the far side holding state: a `module load` done by one command is gone
by the next. Every remote command therefore re-establishes its own environment,
which is what `selas-env.sh` is for:

```bash
ssh csf3 'source ~/selas-env.sh && python -c "import vllm; print(vllm.__version__)"'
```

Putting those lines in `~/.bashrc` instead would apply them to every command run
on CSF, including unrelated work; module loads in `.bashrc` are a well-known
source of confusing breakage.

**Reopening the master.** `ControlPersist` expiry leaves the socket *file*
behind, and ssh then refuses to reuse it with
`ControlSocket ... already exists, disabling multiplexing` -- it silently falls
back to an ordinary connection that nothing else can share. Always clear it
first:

```bash
rm -f ~/.ssh/csf3-long.sock
ssh -M -S ~/.ssh/csf3-long.sock -o ControlPersist=12h -fN \
    t95317ha@csf3.itservices.manchester.ac.uk
```

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

`meta-llama/Llama-3.3-70B-Instruct` at bf16 is ~141 GB of weights -- one H200
exactly, with nothing left for KV cache, so **two GPUs** is the minimum sane
allocation.

| | surveyed 2026-09-16 |
|---|---|
| partition | `gpuH_short` (≤1 day) or `gpuH` (≤4 days, batch only) |
| account | **`gpu-cdt-dmcs`** |
| GPUs | `-G 2` → 282 GB VRAM |
| cores | `-n 1 -c 16` (≤8/GPU). `-c` not `-n`: vLLM is one process |
| host RAM | 24 GB/core → 384 GB (nodes have 1.5 TB) |
| nodes | node820-823, 8×H200 each |
| python | `module load apps/binapps/anaconda3/2024.10` → 3.12.7 |
| vLLM | 0.19.1 already in user site; torch 2.10.0 cu128, `sm_90` present |
| weights | `HF_HOME=~/h200-scratch/hf` (1.0 TB volume, 946 GB free) |

### The account is not the one in the CSF docs

`gpuH`/`gpuH_short` list `AllowAccounts=gpu-h200,gpu-support-sysadmin,siteadmin`.
Of our four associations (`sk01`, `gpu-free`, `gpu-cdt-dmcs`, `gpu-sk01`) only
**`gpu-cdt-dmcs`** is accepted there; `gpu-h200-fse-pgdr` from the CSF
documentation is not one of ours at all. Verified with `sbatch --test-only`,
which reports where a job *would* land without submitting anything:

| account | partition | estimate |
|---|---|---|
| `gpu-cdt-dmcs` | `gpuH_short` | same day |
| `gpu-free` | `gpuL` | +2 days |
| `gpu-free` | `gpuA` | +4 days |
| `sk01` | `gpuA` | +10 days |

`gpu-cdt-dmcs` is refused on `gpuA`/`gpuL` with `AssocGrpGRES`, and the other
three are refused on `gpuH*`. So the pairing is fixed: H200 via `gpu-cdt-dmcs`,
or wait days.

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
