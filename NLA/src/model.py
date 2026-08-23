import torch.nn as nn
from transformers import AutoModelForCausalLM, AutoTokenizer

from src.config import DEVICE, DTYPE, MODEL_ID


def load_tokenizer(model_id: str | None = None):
    """Tokenizer for `model_id`, defaulting to the target model T.

    Callers pass an explicit id when the weights they are loading ship their own
    tokenizer -- a published AV/AR defines the inject token's id for its own
    embedding table, so borrowing T's tokenizer could point at a different row.
    """
    return AutoTokenizer.from_pretrained(model_id or MODEL_ID)


def load_target(device: str = DEVICE):
    """Load the frozen target model T. No parameter ever trains through this.

    `device` may be "auto" to shard a model larger than one card across all
    visible GPUs (a 12B target does not fit on a single 24GB 4090).
    """
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        dtype=DTYPE,
        device_map=device,
    )
    model.eval()
    model.requires_grad_(False)
    return model


def decoder_stack(model) -> nn.Module:
    """Return the text transformer body -- the module owning `.layers` and `.norm`.

    Qwen2/Llama expose it at `.model`, but Gemma-3's multimodal checkpoints wrap
    the text stack one level deeper at `.model.language_model`. Both the forward
    hook (data.py, server/inference.py) and the AR truncation (ar.py) need this
    exact module; hooking or truncating the wrong one is the failure mode that
    silently poisons every downstream number, so resolve it once here rather
    than hardcoding an attribute path at each call site.
    """
    for owner in (getattr(model, "model", None), model):
        if owner is None:
            continue
        if isinstance(getattr(owner, "layers", None), nn.ModuleList):
            return owner
        lang = getattr(owner, "language_model", None)
        if lang is not None and isinstance(getattr(lang, "layers", None), nn.ModuleList):
            return lang
    raise AttributeError(
        f"could not locate the decoder stack on {type(model).__name__}; "
        f"add its attribute path to decoder_stack()"
    )


def decoder_layers(model) -> nn.ModuleList:
    """Return the decoder block list, whatever the backbone calls it."""
    return decoder_stack(model).layers
