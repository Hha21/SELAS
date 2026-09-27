"""Checks on the NLA pair wrapper that need no GPU.

The tokenizer checks need the released pair's tokenizer files: set
NLA_TOKENIZER_DIR to a directory holding the AV's tokenizer files and
nla_meta.yaml (a local copy or the HF cache snapshot); they skip otherwise.

Run:  python -m pytest experiments/nla/test_nla_pair.py -q
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nla_pair import VAR_NRM, av_prompt_ids, extract_explanation, load_meta, reconstruction_scores  # noqa: E402


def test_explanation_is_read_inside_its_tags():
    assert extract_explanation("<explanation>\nA list.\n</explanation>") == "A list."
    # A decode that hit its token budget has no closing tag; keep what it wrote.
    assert extract_explanation("<explanation>\nA list, then") == "A list, then"
    assert extract_explanation("no tags at all") == "no tags at all"


def test_scores_follow_the_reference_definitions():
    rng = np.random.default_rng(0)
    g = rng.normal(size=(3, 64))
    s = reconstruction_scores(np.stack([g[0], -g[1], 5 * g[2]]), g, mse_scale=8.0)  # sqrt(64)
    assert s["cos"] == pytest.approx([1, -1, 1])
    assert s["mse_nrm"] == pytest.approx(2 * (1 - s["cos"]))   # the reference's identity
    assert s["fve_nrm"][0] == pytest.approx(1.0)
    assert s["fve_nrm"][1] == pytest.approx(1 - 4 / VAR_NRM)


def _tok_dir():
    d = os.environ.get("NLA_TOKENIZER_DIR")
    if not d or not (Path(d) / "nla_meta.yaml").exists():
        pytest.skip("set NLA_TOKENIZER_DIR to the AV's tokenizer files and nla_meta.yaml")
    return d


def test_injection_site_is_inside_the_concept_tags():
    from transformers import AutoTokenizer
    d = _tok_dir()
    tok, meta = AutoTokenizer.from_pretrained(d), load_meta(d)
    ids, site = av_prompt_ids(tok, meta)
    assert ids[0] == tok.bos_token_id and ids.count(tok.bos_token_id) == 1
    text = tok.decode(ids)
    assert "<concept>" + meta["tokens"]["injection_char"] + "</concept>" in text
    assert tok.convert_ids_to_tokens(ids[site]) == meta["tokens"]["injection_char"]
