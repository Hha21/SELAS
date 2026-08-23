"""
Activation Reconstructor (AR) — the decoder half of the NLA.

Architecture (per paper):
  - Base: the transformer body of T truncated to its first PROBE_LAYER layers.
    The final-layer norm is removed so last_hidden_state = raw x_l (matching
    the hook-captured activation stored in the dataset).
  - Head: Linear(d_model, d_model, bias=False), always trainable.
  - Input:  AR_PREFIX + z + AR_SUFFIX  (z = original text for oracle; AV
            description during GRPO). The last-token hidden state at layer l
            is the "value head" position.
  - Output: predicted activation â, shape (batch, d_model).

Truncating to l layers saves ~33% memory and removes the need to map
backwards through layers l+1..24, which a single linear layer cannot do.
"""

import torch
import torch.nn as nn
from transformers import AutoModelForCausalLM

from src.config import AR_SOURCE, DEVICE, DTYPE, MODEL_ID, PROBE_LAYER, TORCH_DEVICE
from src.model import decoder_stack


class Reconstructor(nn.Module):
    def __init__(self, base, d_model: int):
        super().__init__()
        self.base = base
        self.head = nn.Linear(d_model, d_model, bias=False)   # no bias, per reference impl

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor = None,
    ) -> torch.Tensor:
        out = self.base(input_ids=input_ids, attention_mask=attention_mask)
        h = out.last_hidden_state[:, -1, :]   # (batch, d_model) last-token pool
        # Under device_map="auto" the base is sharded, so its output lands on
        # whichever card holds the last layer -- not necessarily the head's.
        # A no-op when unsharded.
        h = h.to(self.head.weight.device)
        return self.head(h)                    # â  (batch, d_model)


def load_ar(device: str = DEVICE, freeze_base: bool = True) -> Reconstructor:
    """
    Load a fresh copy of T, truncate it to PROBE_LAYER, and wrap as AR.

    Truncation: keep only layers[0..PROBE_LAYER], discard the rest and the
    final norm so that last_hidden_state == raw x_l (same quantity the hook
    captures during activation extraction).
    """
    # A published AR is already truncated (its config reports PROBE_LAYER+1
    # layers and it ships no model.norm), so the truncation below is a no-op for
    # it rather than a second, destructive cut. A local .pt is applied on top of
    # the base model by the caller, so that path builds the base as before.
    kind, src = AR_SOURCE
    base_id = str(src) if kind == "hub" else MODEL_ID

    full_model = AutoModelForCausalLM.from_pretrained(
        base_id,
        dtype=DTYPE,
        device_map=device,
    )

    base = decoder_stack(full_model)   # Qwen2Model, or Gemma3's text stack

    # Truncate to first PROBE_LAYER+1 decoder layers and strip the final norm.
    # The norm was fitted after 24 layers; without it, last_hidden_state is the
    # raw residual stream at layer PROBE_LAYER, matching what the hook captures.
    base.layers = nn.ModuleList(list(base.layers)[: PROBE_LAYER + 1])
    base.norm   = nn.Identity()

    base.train()
    if freeze_base:
        base.requires_grad_(False)

    d  = full_model.config.hidden_size
    ar = Reconstructor(base, d)
    # A concrete device: `device` may be the device_map "auto", which Tensor.to
    # rejects. The head is one d x d matrix, so it does not need sharding.
    head_device = TORCH_DEVICE if device == "auto" else device
    ar.head = ar.head.to(device=head_device, dtype=DTYPE)
    # Identity init: output = x_l, a better starting point than random.
    # Reference impl notes this gives loss ~1.61 vs ~1.94 at step 0.
    nn.init.eye_(ar.head.weight)

    # A published AR keeps its trained head in a separate value_head.safetensors
    # (the shards hold only the truncated body), so load it over the identity
    # init. Without this the body would be the trained one but the head would
    # still be identity -- which reconstructs *something* and would not obviously
    # look broken.
    if kind == "hub":
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file

        head_path = hf_hub_download(repo_id=str(src), filename="value_head.safetensors")
        sd = load_file(head_path)
        key = "weight" if "weight" in sd else next(iter(sd))
        w = sd[key].to(device=ar.head.weight.device, dtype=ar.head.weight.dtype)
        if tuple(w.shape) != tuple(ar.head.weight.shape):
            raise ValueError(
                f"value_head shape {tuple(w.shape)} does not match AR head "
                f"{tuple(ar.head.weight.shape)} for {src}"
            )
        with torch.no_grad():
            ar.head.weight.copy_(w)
    return ar
