"""The released NLA pair for gemma-3-27b-it at layer 41, run under transformers.

kitft/nla-gemma3-27b-L41-av (the verbaliser, AV) turns a residual-stream vector
into text; kitft/nla-gemma3-27b-L41-ar (the reconstructor, AR) turns that text
back into a vector. How close the reconstruction comes to the original says how
much of the vector the words captured.

The recipe is kitft/nla-inference (README and nla_inference.py) with SGLang
replaced by transformers' generate. It is not the recipe of ``NLA/src``, which
is our Qwen-0.5B reproduction: the released gemma pair uses a different
injection character, injects at L2 norm 60000 rather than sqrt(d), and its AR
was trained with a BOS prefix. Everything NLA-specific is read from each
checkpoint's ``nla_meta.yaml`` and checked against the live tokenizer, as the
reference client does.

Reconstruction is reported three ways, all from the reference: ``mse_nrm``
(both vectors scaled to L2 = sqrt(d), mean squared error, = 2(1 - cos)),
``cos``, and ``fve_nrm`` = 1 - mse_nrm / Var(v_nrm), the variance of the
normalised training vectors. At this layer the vectors sit close to their mean
(Var = 0.0579), so cos is ~0.99 almost everywhere and fve_nrm is the number
that discriminates: 0 is no better than predicting the mean vector.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import torch
import yaml

AV_REPO = "kitft/nla-gemma3-27b-L41-av"
AR_REPO = "kitft/nla-gemma3-27b-L41-ar"
LAYER = 41                  # output of block 41 = transformers hidden_states[42]
# Var(v_nrm) over the pair's training vectors: the predict-the-mean MSE, the
# fve_nrm denominator (kitft/nla-inference examples/gemma27b_layer41_step6000.txt).
VAR_NRM = 0.0579

_EXPLANATION = re.compile(r"<explanation>\s*(.*?)\s*(?:</explanation>|$)", re.DOTALL)


def _local(repo: str, filename: str) -> Path:
    p = Path(repo) / filename
    if p.exists():
        return p
    from huggingface_hub import hf_hub_download
    return Path(hf_hub_download(repo_id=repo, filename=filename))


def load_meta(repo: str) -> dict:
    return yaml.safe_load(_local(repo, "nla_meta.yaml").read_text())


def extract_explanation(text: str) -> str:
    """The text inside <explanation> tags; an unclosed tag (the decode hit its
    token budget) keeps everything after it, and no tag keeps the whole text,
    as the reference client does."""
    m = _EXPLANATION.search(text)
    return (m.group(1) if m else text).strip()


def _ids(enc) -> list[int]:
    """apply_chat_template(tokenize=True) returns a list in some versions and
    a BatchEncoding in others."""
    return list(enc["input_ids"] if hasattr(enc, "keys") else enc)


def av_prompt_ids(tok, meta: dict) -> tuple[list[int], int]:
    """The AV's canonical prompt and the position the vector goes in.

    One-step ``tokenize=True``, as the reference insists: the template string
    already carries <bos>, so a two-step render-then-encode with special tokens
    would add a second one and move the injection site.
    """
    t = meta["tokens"]
    content = meta["prompt_templates"]["av"].format(injection_char=t["injection_char"])
    ids = _ids(tok.apply_chat_template([{"role": "user", "content": content}],
                                       tokenize=True, add_generation_prompt=True))
    sites = [p for p, i in enumerate(ids) if i == t["injection_token_id"]
             and 0 < p < len(ids) - 1
             and ids[p - 1] == t["injection_left_neighbor_id"]
             and ids[p + 1] == t["injection_right_neighbor_id"]]
    if len(sites) != 1:
        raise ValueError(f"expected one injection site with the sidecar's neighbours, found {sites}")
    return ids, sites[0]


def normalise(v: torch.Tensor, scale: float) -> torch.Tensor:
    """Rescale rows to L2 norm ``scale``; the norm is taken in fp32."""
    n = v.float().norm(dim=-1, keepdim=True).clamp_min(1e-12)
    return v.float() * (scale / n)


class Verbaliser:
    """vector -> explanation, greedy by default (reproducible, as in the
    reference's worked examples)."""

    def __init__(self, repo: str = AV_REPO, device: str = "cuda", dtype=torch.bfloat16):
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.meta = load_meta(repo)
        assert self.meta["role"] == "av", self.meta["role"]
        self.tok = AutoTokenizer.from_pretrained(repo)
        self.model = AutoModelForCausalLM.from_pretrained(repo, dtype=dtype, device_map=device)
        self.model.eval().requires_grad_(False)
        self.scale = float(self.meta["extraction"]["injection_scale"])
        ids, self.site = av_prompt_ids(self.tok, self.meta)
        dev = self.model.get_input_embeddings().weight.device
        self.ids = torch.tensor([ids], device=dev)
        # Gemma's embedding layer multiplies by sqrt(d) inside forward(); the
        # injected vector replaces a row *after* that, so the module (not the
        # raw weight) must produce the other rows. Checked, not assumed.
        emb = self.model.get_input_embeddings()
        with torch.no_grad():
            got = emb(self.ids[:, :2]).float().norm()
            raw = emb.weight[self.ids[0, :2]].float().norm()
        d = self.model.config.hidden_size
        if not math.isclose(float(got / raw), math.sqrt(d), rel_tol=0.02):
            raise AssertionError(f"embedding module scales by {float(got / raw):.2f}, "
                                 f"expected sqrt(d) = {math.sqrt(d):.2f}")

    @torch.no_grad()
    def explain(self, vectors: np.ndarray, max_new_tokens: int = 200, batch_size: int = 32,
                temperature: float = 0.0) -> list[str]:
        out: list[str] = []
        emb = self.model.get_input_embeddings()
        base = emb(self.ids)                                   # (1, T, d), already scaled
        for s in range(0, len(vectors), batch_size):
            v = torch.as_tensor(np.asarray(vectors[s:s + batch_size]), device=base.device)
            e = base.expand(len(v), -1, -1).clone()
            e[:, self.site] = normalise(v, self.scale).to(e.dtype)
            kw = dict(do_sample=False) if temperature == 0 else dict(do_sample=True, temperature=temperature)
            gen = self.model.generate(inputs_embeds=e,
                                      attention_mask=torch.ones(e.shape[:2], dtype=torch.long, device=e.device),
                                      max_new_tokens=max_new_tokens,
                                      pad_token_id=self.tok.pad_token_id, **kw)
            if gen.shape[1] > max_new_tokens:                 # some versions echo the prompt ids
                gen = gen[:, self.ids.shape[1]:]
            out += self.tok.batch_decode(gen, skip_special_tokens=True)
        return out


class Reconstructor:
    """explanation -> vector: the AR's 42-layer body without its final norm,
    then the trained value head, read at the last token."""

    def __init__(self, repo: str = AR_REPO, device: str = "cuda", dtype=torch.bfloat16):
        from safetensors.torch import load_file
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.meta = load_meta(repo)
        assert self.meta["role"] in ("ar", "critic"), self.meta["role"]
        self.template = self.meta["prompt_templates"]["ar"]
        self.mse_scale = float(self.meta["extraction"]["mse_scale"])
        self.tok = AutoTokenizer.from_pretrained(repo)
        # Trained with BOS (the reference measured fve_nrm 0.31 without it
        # against 0.77 with it); the prompt must end on the sidecar's suffix.
        probe = self.tok(self.template.format(explanation="x"), add_special_tokens=True)["input_ids"]
        assert probe[0] == self.tok.bos_token_id, "AR prompts must start with BOS"
        suffix = self.meta["tokens"].get("critic_suffix_ids")
        assert not suffix or probe[-len(suffix):] == suffix, (probe[-8:], suffix)
        full = AutoModelForCausalLM.from_pretrained(repo, dtype=dtype, device_map=device)
        self.body = full.model
        if not hasattr(self.body, "norm"):
            raise AssertionError(f"{type(self.body).__name__} has no final norm to strip")
        self.body.norm = torch.nn.Identity()
        self.body.eval().requires_grad_(False)
        d = full.config.hidden_size
        dev = next(self.body.parameters()).device
        self.head = torch.nn.Linear(d, d, bias=False, dtype=dtype, device=dev)
        sd = load_file(str(_local(repo, "value_head.safetensors")))
        self.head.weight.data.copy_(sd["weight"] if "weight" in sd else next(iter(sd.values())))
        self.head.eval().requires_grad_(False)
        self.tok.padding_side = "right"

    @torch.no_grad()
    def reconstruct(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        dev = next(self.body.parameters()).device
        out = []
        for s in range(0, len(texts), batch_size):
            enc = self.tok([self.template.format(explanation=t) for t in texts[s:s + batch_size]],
                           add_special_tokens=True, padding=True, return_tensors="pt").to(dev)
            h = self.body(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"],
                          use_cache=False).last_hidden_state
            last = enc["attention_mask"].sum(1) - 1            # right padding: last real token
            out.append(self.head(h[torch.arange(len(last), device=dev), last]).float().cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, self.head.in_features), np.float32)

    def score(self, texts: list[str], gold: np.ndarray, batch_size: int = 16) -> dict[str, np.ndarray]:
        return reconstruction_scores(self.reconstruct(texts, batch_size), gold, self.mse_scale)


def reconstruction_scores(pred: np.ndarray, gold: np.ndarray, mse_scale: float,
                          var_nrm: float = VAR_NRM) -> dict[str, np.ndarray]:
    """mse_nrm, cos and fve_nrm per row, as the reference defines them."""
    def nrm(x):
        x = np.asarray(x, dtype=np.float64)
        return x / np.clip(np.linalg.norm(x, axis=-1, keepdims=True), 1e-12, None) * mse_scale
    p, g = nrm(pred), nrm(gold)
    mse = ((p - g) ** 2).mean(-1)
    cos = (p * g).sum(-1) / mse_scale ** 2
    return {"mse_nrm": mse, "cos": cos, "fve_nrm": 1 - mse / var_nrm}
