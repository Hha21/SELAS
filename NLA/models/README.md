# models/

Everything model-shaped lives here. The contents are gitignored (large and
machine-local); this README is the only tracked file.

```
models/
├── README.md
├── hf/                     # HF_HOME -- HuggingFace downloads (blobs + snapshots)
├── Qwen2.5-0.5B/           # one subdirectory per backbone
│   ├── av.pt               #   trained Activation Verbalizer
│   └── ar.pt               #   trained Activation Reconstructor
└── gemma-3-12b-it/         # (later)
    ├── av.pt
    └── ar.pt
```

The subdirectory name is the last path segment of `NLA_MODEL_ID`, so
`Qwen/Qwen2.5-0.5B` resolves to `models/Qwen2.5-0.5B/`. `src/config.py` derives
`AV_CHECKPOINT` / `AR_CHECKPOINT` from it — nothing needs to be repointed by
hand when the backbone changes.

Keeping the pairs in per-backbone directories rather than a flat `models/av.pt`
matters once there is more than one backbone: a mismatched pair still loads and
still produces FVE numbers, they are just quietly wrong.

`hf/` is set as `HF_HOME` so downloads land inside the project instead of
`~/.cache/huggingface`. It keeps its own internal layout (`models--Qwen--Qwen2.5-0.5B/…`)
and dedups blobs across backbones, so it is deliberately not split per model.

## Getting the checkpoints

These are gitignored, so they move between machines with `rsync`, not `git`:

```bash
# from the local dev box, pull the trained 0.5B pair off the workstation
rsync -avP harry@mingfei-workstation-76:'~/NLA/NLA_reproduce/models/*.pt' \
    ~/PHD/SummerWork/NLA/models/Qwen2.5-0.5B/
```

`-P` is `--partial --progress`, so a dropped ssh connection resumes rather than
restarting. The remote glob is quoted so the *remote* shell expands it.

`hf/` does not need copying — HuggingFace re-downloads on demand. Only copy it
to a machine with no internet access on its compute nodes (likely the CSF).
