"""
Central configuration for the NLA pipeline.

Everything that varies per machine or per backbone is read from the environment
so the same checkout runs unchanged on all three targets:

  local dev box   GTX 1650 Ti, 4GB, Turing (sm_75)  -> Qwen2.5-0.5B, fp16
  workstation     2x RTX 4090, 24GB each, Ada       -> 7B/12B backbone, bf16
  CSF             4x H200, 141GB each, Hopper       -> NLA training at scale

Overrides:

  NLA_MODEL_ID     HuggingFace repo of the target model T
  NLA_PROBE_LAYER  residual-stream layer to hook (see PROBE_LAYERS below)
  NLA_DTYPE        auto | bfloat16 | float16 | float32   (auto = best available)
  NLA_DEVICE       cuda | cuda:1 | cpu | auto            (auto = shard over GPUs)
  NLA_TRACE_DIR    where runtime activation traces are written
  NLA_RUN_ID       groups traces from one run into a subdirectory
  NLA_CAPTURE      full | text | off   (default full; text omits the .npz)

Nothing else in the codebase hardcodes a model, layer, or dtype -- src/model.py,
src/av.py, src/ar.py, src/data.py and server/inference.py all import from here.
"""

import os
import sys
import warnings
from pathlib import Path

# HF_HOME must be set before huggingface_hub is first imported -- it reads the
# env var into module-level constants at import time, so setting it afterwards
# is silently ignored and downloads land in ~/.cache/huggingface instead.
# Every entry point must therefore import src.config before any HF library.
_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = Path(os.getenv("NLA_MODELS_DIR", _ROOT / "models"))

if "huggingface_hub" in sys.modules and "HF_HOME" not in os.environ:
    warnings.warn(
        "huggingface_hub was imported before src.config, so HF_HOME could not "
        f"be pointed at {MODELS_DIR / 'hf'}; downloads will go to the default "
        "cache. Move the `from src.config import ...` line above the "
        "transformers/datasets imports in this entry point.",
        RuntimeWarning, stacklevel=2,
    )

os.environ.setdefault("HF_HOME", str(MODELS_DIR / "hf"))

import torch

from src.compat import disable_triton_ops_without_compiler

# Must run before any model forward pass; see src/compat.py for why.
disable_triton_ops_without_compiler()

# Probe layers for the backbones with a released NLA checkpoint pair
# (huggingface.co/collections/kitft/nla-models). The probe layer is a property
# of the released AV/AR, not a free choice -- getting it wrong silently poisons
# every downstream number, so it is looked up rather than remembered.
# WITHOUT EXCEPTION these are the *instruction-tuned* checkpoints. Every
# released kitft NLA is fine-tuned from an Instruct/-it model, so the AV has
# only ever seen Instruct activations; the corresponding base model is a
# different network whose residual stream the AV would misread while still
# returning fluent, confident explanations. The base ids are deliberately absent
# rather than aliased -- an entry here would let one silently inherit a layer.
# Verified 2026-09-16 against the `base_model` field of each model card.
PROBE_LAYERS = {
    "Qwen/Qwen2.5-0.5B":   16,   # ours, 24 layers, trained locally on 2x 4090
    "Qwen/Qwen2.5-7B-Instruct":   20,  # kitft/nla-qwen2.5-7b-L20-{av,ar}
    "google/gemma-3-12b-it":      32,  # kitft/nla-gemma3-12b-L32-{av,ar}
    "google/gemma-3-27b-it":      41,  # kitft/nla-gemma3-27b-L41-{av,ar}
    "meta-llama/Llama-3.3-70B-Instruct": 53,  # kitft/Llama-3.3-70B-NLA-L53-{av,ar}
}

MODEL_ID = os.getenv("NLA_MODEL_ID", "Qwen/Qwen2.5-0.5B")

# Default to the known-good layer for this backbone; explicit env var always wins.
PROBE_LAYER = int(os.getenv("NLA_PROBE_LAYER", PROBE_LAYERS.get(MODEL_ID, -1)))
if PROBE_LAYER < 0:
    raise ValueError(
        f"No default probe layer known for {MODEL_ID!r}. "
        f"Set NLA_PROBE_LAYER explicitly, or add an entry to PROBE_LAYERS."
    )


def _resolve_device(spec: str | None) -> str:
    if spec:
        return spec
    return "cuda" if torch.cuda.is_available() else "cpu"


def _resolve_dtype(spec: str | None, device: str) -> torch.dtype:
    """Pick the widest dtype the *selected device* supports natively.

    Keyed on `device` rather than on torch.cuda.is_available(): forcing
    NLA_DEVICE=cpu on a CUDA box must give fp32, not the fp16 the GPU would
    have wanted -- half precision on CPU is unsupported for many ops and
    silently slow for the rest.

    bf16 needs compute capability >= 8.0 (Ampere). Deliberately NOT using
    torch.cuda.is_bf16_supported(): it counts emulation and returns True on the
    local Turing card (sm_75), which would hand back bf16 that silently runs
    emulated and slow rather than falling back to fp16.
    """
    if spec and spec != "auto":
        return getattr(torch, spec)
    if device == "cpu" or not torch.cuda.is_available():
        return torch.float32
    return torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16


# "auto" shards a model too large for one card across all visible GPUs
# (needed for a 12B target on 2x 24GB); a plain "cuda" keeps it on one.
DEVICE = _resolve_device(os.getenv("NLA_DEVICE"))
DTYPE  = _resolve_dtype(os.getenv("NLA_DTYPE"), DEVICE)

# DEVICE is an accelerate *device_map*, so "auto" is meaningful to
# from_pretrained -- it shards a model too big for one card across all of them.
# It is not a torch device: torch.load, Tensor.to and torch.tensor all reject it
# ("don't know how to restore data location ... tagged with auto"). TORCH_DEVICE
# is the concrete device for placing tensors. Under a sharded model, inputs go
# to the first shard, which accelerate puts on cuda:0.
TORCH_DEVICE = (
    ("cuda" if torch.cuda.is_available() else "cpu") if DEVICE == "auto" else DEVICE
)

# Trained AV/AR checkpoint pair for *this* backbone. One subdirectory per model
# (models/Qwen2.5-0.5B/, models/gemma-3-12b-it/, ...) so several can coexist --
# a single flat models/av.pt silently serves the wrong pair once there is more
# than one backbone in play, which the FVE numbers would not make obvious.
CHECKPOINT_DIR = MODELS_DIR / MODEL_ID.split("/")[-1]
AV_CHECKPOINT  = CHECKPOINT_DIR / "av.pt"
AR_CHECKPOINT  = CHECKPOINT_DIR / "ar.pt"

# Two checkpoint formats have to coexist. Our own training writes a .pt state
# dict that is applied on top of a freshly built model; the *published* pairs are
# complete fine-tuned HF models (sharded safetensors) that are loaded directly.
# A local .pt always wins, so the locally-trained 0.5B pair keeps working exactly
# as before and only backbones without one fall through to the hub.
CHECKPOINT_REPOS = {
    "Qwen/Qwen2.5-7B-Instruct": ("kitft/nla-qwen2.5-7b-L20-av",
                                 "kitft/nla-qwen2.5-7b-L20-ar"),
}
_repos  = CHECKPOINT_REPOS.get(MODEL_ID, (None, None))
AV_REPO = os.getenv("NLA_AV_REPO") or _repos[0]
AR_REPO = os.getenv("NLA_AR_REPO") or _repos[1]


def _checkpoint_source(pt_path, repo):
    """('pt', Path) if a local state dict exists, else ('hub', repo_id), else (None, None)."""
    if pt_path.is_file():
        return ("pt", pt_path)
    if repo:
        return ("hub", repo)
    return (None, None)


AV_SOURCE = _checkpoint_source(AV_CHECKPOINT, AV_REPO)
AR_SOURCE = _checkpoint_source(AR_CHECKPOINT, AR_REPO)

# Runtime activation traces. Defaults to <repo>/../traces -- deliberately
# outside NLA/, because a trace is the shared artifact of a POLARIS run and the
# NLA pipeline, owned by neither. Gitignored at the SummerWork level.
TRACE_DIR      = Path(os.getenv("NLA_TRACE_DIR", _ROOT.parent / "traces"))
RUN_ID         = os.getenv("NLA_RUN_ID", "")   # blank -> writer picks a timestamp
# NLA_CAPTURE has three settings, not two:
#
#   full | 1   text + activations   (default)
#   text       text only, no .npz
#   off  | 0   nothing
#
# "text" exists because activations are *derived* data, not observations. The
# sidecar records token_ids, so a forward pass over exactly those ids reproduces
# the same residual stream -- no sampling is involved, the tokens are already
# chosen. At 0.5B the .npz is ~37x the JSON and at 7B nearer 150x, so a run kept
# for later NLA training is enormously cheaper as text that is re-expanded once,
# on demand, at whatever layer and positions that training actually wants.
_CAPTURE = os.getenv("NLA_CAPTURE", "full").strip().lower()
if _CAPTURE in ("0", "false", "no", "off"):
    CAPTURE_TRACES, CAPTURE_ACTIVATIONS = False, False
elif _CAPTURE in ("text", "json", "text-only"):
    CAPTURE_TRACES, CAPTURE_ACTIVATIONS = True, False
elif _CAPTURE in ("1", "true", "yes", "full", "on"):
    CAPTURE_TRACES, CAPTURE_ACTIVATIONS = True, True
else:
    raise ValueError(
        f"NLA_CAPTURE={_CAPTURE!r} not understood (expected full|text|off)"
    )

# AR prompt from the paper (Appendix: Prompting the activation reconstructor).
# AR always receives: AR_PREFIX + z + AR_SUFFIX, and the last-token hidden state
# at layer PROBE_LAYER (the position of the final ">" of <summary>) is fed to the head.
AR_PREFIX = "Summary of the following text: <text>"
AR_SUFFIX = "</text> <summary>"

# AV soft-token injection (reference: design.md + stage3_build.py).
# ㊗ is a rare Unicode character used as a single-token placeholder; its embedding
# is overwritten at forward time with the normalised activation vector.
INJECT_TOKEN = "㊗"

# Full user prompt from the paper / reference stage3_build.py (_DEFAULT_ACTOR_TEMPLATE).
# Single user message — no system message. Chat template applied at training time.
# ㊗ inside <concept> tags is replaced with the normalised h_l at embedding time.
AV_USER_PROMPT = (
    "You are a meticulous AI researcher conducting an important investigation into "
    "activation vectors from a language model. Your overall task is to describe the "
    "semantic content of that activation vector.\n\n"
    "We will pass the vector enclosed in <concept> tags into your context. You must "
    "then produce an explanation for the vector, enclosed within <explanation> tags. "
    "The explanation consists of 2-3 text snippets describing that vector.\n\n"
    f"Here is the vector:\n\n<concept>{INJECT_TOKEN}</concept>\n\n"
    "Please provide an explanation."
)
