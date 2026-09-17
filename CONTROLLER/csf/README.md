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

## Your login details are not in this repository

Everything here refers to `$CSF_USER`. Set it locally; `csf/local.env` is
gitignored:

```bash
echo 'export CSF_USER=<your-csf-username>' > csf/local.env
source csf/local.env
```

Inside a job, Slurm already sets `$USER` to the right thing, so the job script
needs no configuration at all.

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
    $CSF_USER@csf3.itservices.manchester.ac.uk
```

## Procedure

```bash
# 1. laptop: open the multiplexed master (needs your password + DUO)
ssh -M -S ~/.ssh/csf3-long.sock -o ControlPersist=12h -fN \
    $CSF_USER@csf3.itservices.manchester.ac.uk

# 2. survey what CSF already has (read-only)
ssh -S ~/.ssh/csf3-long.sock $CSF_USER@csf3.itservices.manchester.ac.uk \
    'bash -s' < recon.sh

# 3. submit the server job
ssh -S ~/.ssh/csf3-long.sock $CSF_USER@... 'cd ~/selas && sbatch csf/serve_llm.sbatch'

# 4. wait for the endpoint file, then read the node name
ssh -S ~/.ssh/csf3-long.sock $CSF_USER@... 'cat ~/h200-scratch/endpoints/latest.json'

# 5. open the tunnel to that compute node (leave running)
ssh -L 8000:<node>:8000 $CSF_USER@csf3.itservices.manchester.ac.uk

# 6. laptop: SWIM, then the controller
../../SWIM/start_swim.sh
../run_controller.py --policy llm --backend openai \
    --llm-base-url http://localhost:8000/v1 --llm-model csf-llm
```

## Resource arithmetic

Two target models, and the GPU count follows from the weights at bf16:

| model | weights | GPUs | NLA layer |
|---|---|---|---|
| `google/gemma-3-27b-it` *(default)* | ~54 GB | `-G 1` -- comfortable on a 141 GB H200 | 41 |
| `meta-llama/Llama-3.3-70B-Instruct` | ~141 GB | `-G 2` -- one H200 exactly, nothing left for KV cache | 53 |

Gemma is the default because its licence is click-through and usually granted
immediately, while Meta's approval can take a while. Both are served the same
way, and the controller does not care which is behind the endpoint. To switch:

```bash
SELAS_MODEL=meta-llama/Llama-3.3-70B-Instruct sbatch -G 2 -c 16 csf/serve_llm.sbatch
```

Command-line flags override `#SBATCH` and must precede the script filename.

| | surveyed 2026-09-16 |
|---|---|
| partition | `gpuH_short` (≤1 day) or `gpuH` (≤4 days, batch only) |
| account | see below -- set `CSF_ACCOUNT` |
| cores | `-n 1 -c 8` per GPU (partition maximum). `-c` not `-n`: vLLM is one process |
| host RAM | 24 GB/core → 192 GB at `-c 8` (nodes have 1.5 TB) |
| nodes | node820-823, 8×H200 each |
| python | `module load apps/binapps/anaconda3/2024.10` → 3.12.7 |
| vLLM | 0.19.1 already in user site; torch 2.10.0 cu128, `sm_90` present |
| weights | `HF_HOME=~/h200-scratch/hf` (1.0 TB volume, 946 GB free) |

### Check which account reaches the H200s -- do not assume

`gpuH`/`gpuH_short` restrict `AllowAccounts` to a specific set, and the account
named in the CSF documentation was not one of ours at all. Of our four Slurm
associations exactly one is accepted on `gpuH*`, and that one is in turn refused
on `gpuA`/`gpuL` with `AssocGrpGRES`. The pairing is rigid: the right account
reaches the H200s with a same-day queue estimate, while the others land on
`gpuA`/`gpuL` days out.

Find yours without submitting anything -- `--test-only` reports where a job
*would* land:

```bash
sacctmgr -nP show assoc user=$USER format=Account,Partition,QOS
for acct in $(sacctmgr -nP show assoc user=$USER format=Account); do
  for part in gpuH_short gpuA gpuL; do
    echo -n "$acct $part: "
    sbatch --test-only -p $part -A $acct -G 1 -n 1 -c 8 -t 0-01 --wrap=true 2>&1 | head -1
  done
done
```

Put the winner in `csf/local.env` as `CSF_ACCOUNT`; `csf/submit.sh` passes it.

## The anaconda interpreter needs one package upgraded

vLLM's first run died three minutes in, before loading any weights:

```
vllm -> transformers.generation.candidate_generator -> from sklearn.metrics import roc_curve
ValueError: numpy.dtype size changed... Expected 96 from C header, got 88 from PyObject
```

`numpy` 2.2.6 sits in the user site and wins; anaconda's `scikit-learn` 1.5.1 is
built against numpy 1.x and cannot load against it. The fix is one package,
installed into the user site so it shadows the module version:

```bash
pip install --user --upgrade scikit-learn        # 1.5.1 (anaconda) -> 1.9.1 (user site)
```

Verify by importing what actually failed, not just sklearn:

```bash
python -c "import vllm.entrypoints.openai.api_server; print('ok')"
```

`bottleneck` still reports the same numpy-1 incompatibility, but that path is
caught internally and the import completes, so it needs nothing.

Worth knowing generally: the user site shadows the anaconda module for every
package, so anything anaconda ships compiled against numpy 1.x will break the
moment it meets the user-site numpy. Upgrade the offender in the user site
rather than downgrading numpy, which vLLM and torch depend on.

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
