"""Offline checks for edit_patch.py: the letter edit, and that the cached
last-token replay (with and without a patch) equals a full forward pass, on a
tiny random Gemma-3 with sliding-window layers shorter than the prompt.

    NLA/.venv/bin/python -m pytest experiments/nla/test_edit_patch.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edit_patch import (Patcher, edit_groups, letter_swap, load_supplied, masked_softmax,  # noqa: E402
                        seeded_direction, unit)


def test_letter_swap_names_the_choice_only():
    text = ('Final token ":" ends a three-choice answer label ("Answer:"), requiring the letter "C" '
            'to complete the code label "C" to specify the "C" (Cruise) option of no action. '
            "or 'C' or \"C.\" or option C. A structured walk through options A/B/C.")
    new, n = letter_swap(text, "C", "A")
    assert n == 6
    assert "options A/B/C" in new and new.startswith("Final token")
    assert '"A" (Cruise)' in new and "'A'" in new and '"A."' in new and "option A." in new


def test_letter_swap_keeps_words_and_suffixes():
    new, n = letter_swap('a lettered option like "D" or "D4" to set it to zero. Do it.', "D", "H")
    assert (new, n) == ('a lettered option like "H" or "H4" to set it to zero. Do it.', 2)
    assert letter_swap("Action = D, then Done", "D", "A") == ("Action = A, then Done", 1)
    assert letter_swap("no quoted letter here", "C", "A") == ("no quoted letter here", 0)


def test_supplied_edits_match_decisions_and_set_the_control_size(tmp_path):
    rows = [(7, {"run": "r/s0", "period": 3, "action": "no_op",
                 "options": [["A", "add_server"], ["C", "no_op"]]}, {"explanation": "orig"})]
    f = tmp_path / "edits.jsonl"
    f.write_text('{"run": "r/s0", "period": 3, "target": "A", "kind": "rewrite", "edited": "cf"}\n'
                 '{"run": "r/s0", "period": 3, "target": "A", "kind": "paraphrase", "edited": "pp"}\n'
                 '{"run": "r/s1", "period": 0, "target": "A", "kind": "rewrite", "edited": "x"}\n')
    edits, skipped = load_supplied(f, rows)
    assert skipped == {"not among the decisions replayed": 1}
    assert [(e["row"], e["kind"], e["chosen"], e["explanation"]) for e in edits] == \
        [(7, "rewrite", "C", "orig"), (7, "paraphrase", "C", "orig")]
    rec = {"orig": np.zeros(3), "cf": np.array([3.0, 0, 0]), "pp": np.array([0, 1.0, 0])}
    [(target, dirs, n_main, _)] = list(edit_groups(edits, rec, supplied=True))
    assert target == "A" and n_main == 3.0
    assert dirs["rewrite"][1] == 3.0 and dirs["paraphrase"][1] == 1.0
    assert dirs["paraphrase_matched"][1] == 3.0          # the paraphrase at the rewrite's size
    assert np.allclose(dirs["paraphrase_matched"][0], [0, 1, 0])
    # a paraphrase alone is not patched: there is no rewrite to set the target and size
    assert list(edit_groups([edits[1]], rec, supplied=True)) == []


def test_masked_softmax_and_directions():
    d = masked_softmax({"A": -1.0, "B": -2.0, "C": 0.0}, ["A", "B"])
    assert set(d) == {"A", "B"} and abs(sum(d.values()) - 1) < 1e-9 and d["A"] > d["B"]
    u = seeded_direction(16, "run", 3, "A")
    assert np.allclose(u, seeded_direction(16, "run", 3, "A")) and abs(np.linalg.norm(u) - 1) < 1e-9
    assert not np.allclose(u, seeded_direction(16, "run", 3, "B"))
    assert abs(np.linalg.norm(unit(np.ones(4) * 7)) - 1) < 1e-12


class _Tok:
    """Letters only: "A".."H" map to ids 10.., " A".." H" to ids 30.."""
    def __call__(self, s, add_special_tokens=False):
        c = s.strip()
        return {"input_ids": [(30 if s.startswith(" ") else 10) + ord(c) - ord("A")]}


@pytest.fixture(scope="module")
def tiny():
    torch = pytest.importorskip("torch")
    tf = pytest.importorskip("transformers")
    torch.manual_seed(0)
    cfg = tf.Gemma3TextConfig(vocab_size=64, hidden_size=32, intermediate_size=64,
                              num_hidden_layers=6, num_attention_heads=4, num_key_value_heads=2,
                              head_dim=8, sliding_window=4, max_position_embeddings=128)
    model = tf.Gemma3ForCausalLM(cfg).eval()
    return torch, model


def _full(torch, P, ids, letters, delta=None):
    P.delta = None if delta is None else torch.as_tensor(delta)
    try:
        with torch.no_grad():
            out = P.model(input_ids=torch.tensor([ids]), use_cache=False, output_hidden_states=True)
    finally:
        P.delta = None
    lp = torch.log_softmax(out.logits[0, -1].float(), -1)
    return {L: max(float(lp[i]) for i in P.ids_for(L)) for L in letters}, out.hidden_states


def test_cached_replay_matches_full_forward(tiny):
    torch, model = tiny
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    P = Patcher(model, _Tok(), layer=3)
    ids = [int(x) for x in torch.randint(0, 64, (13,), generator=torch.Generator().manual_seed(1))]
    letters = list("ABCD")

    want, hs = _full(torch, P, ids, letters)
    cache = P.prefix(ids)
    got, h = P.last(cache, ids[-1], letters)
    assert max(abs(want[L] - got[L]) for L in letters) < 1e-4
    assert np.allclose(h, hs[4][0, -1].numpy(), atol=1e-4)      # hidden_states[layer + 1]

    delta = (3.0 * seeded_direction(32, "t")).astype(np.float32)
    want_p, _ = _full(torch, P, ids, letters, delta)
    got_p, h_p = P.last(cache, ids[-1], letters, delta)          # the same cache, reused
    assert max(abs(want_p[L] - got_p[L]) for L in letters) < 1e-4
    assert max(abs(want_p[L] - want[L]) for L in letters) > 1e-3  # the patch did something
    assert np.allclose(h_p - h, delta, atol=1e-4)
    again, _ = P.last(cache, ids[-1], letters)                    # the cache was not consumed
    assert max(abs(again[L] - got[L]) for L in letters) < 1e-5
