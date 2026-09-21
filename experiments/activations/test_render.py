"""Tests for chat rendering and probe location.

These run without torch or a real tokenizer, because the logic under test is
string manipulation and the failure mode is silent: a probe off by one token
still produces activations, still produces explanations, and every number
downstream is quietly about the wrong position.
"""

import sys
from pathlib import Path

import pytest

# Import the string helpers without pulling in torch.
_src = (Path(__file__).parent / "capture.py").read_text()
_ns: dict = {}
exec(_src[_src.index("SCAFFOLD_FIELDS"):_src.index("def load_decisions")], _ns)
render_chat, locate_probes = _ns["render_chat"], _ns["locate_probes"]


class FakeTok:
    """Gemma-3 shaped template: <start_of_turn>role\\ncontent<end_of_turn>\\n"""

    chat_template = "fake"

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False):
        out = [
            f"<start_of_turn>{'model' if m['role'] == 'assistant' else m['role']}\n"
            f"{m['content']}<end_of_turn>\n"
            for m in messages
        ]
        if add_generation_prompt:
            out.append("<start_of_turn>model\n")
        return "".join(out)


def _messages(reasoning="Reasoning:\n  SLA: met, 0.041 s.\n  Capacity: plenty.\n"
                        "  Trend: rising.\n  Therefore: be cautious.\nAction:"):
    return [
        {"role": "system", "content": "You are the adaptation controller."},
        {"role": "user", "content": "Period 3\n  servers 1 active"},
        {"role": "assistant", "content": "Reasoning:\n  SLA: breached.\nAction: A"},
        {"role": "user", "content": "Period 45\n  servers 3 active\n  arrival rate 40.6 req/s"},
        {"role": "assistant", "content": reasoning},
    ]


def test_render_stops_inside_the_assistant_turn():
    """No end-of-turn marker after the final content.

    The server scores a turn that is still open; rendering the final assistant
    message normally would close it and shift every probe by a token.
    """
    r = render_chat(FakeTok(), _messages())
    assert r.rstrip().endswith("Action:")
    assert "<end_of_turn>" not in r[-40:]


def test_action_probe_is_the_final_position():
    msgs = _messages()
    r = render_chat(FakeTok(), msgs)
    assert locate_probes(r, msgs)["P_action"] == len(r)


def test_field_probes_land_at_the_end_of_their_own_line():
    msgs = _messages()
    r = render_chat(FakeTok(), msgs)
    p = locate_probes(r, msgs)
    for name, text in (("P_sla", "0.041 s."), ("P_capacity", "plenty."),
                       ("P_trend", "rising."), ("P_therefore", "be cautious.")):
        assert r[:p[name]].endswith(text), name
    assert p["P_sla"] < p["P_capacity"] < p["P_trend"] < p["P_therefore"] < p["P_action"]


def test_probes_ignore_the_worked_examples():
    """The exemplars contain their own 'SLA:' and 'Action:' lines.

    Searching the whole rendered string would anchor every probe in the
    demonstrations rather than the live decision.
    """
    msgs = _messages()
    r = render_chat(FakeTok(), msgs)
    p = locate_probes(r, msgs)
    assert p["P_sla"] > r.index("Period 45")


def test_state_probe_ends_the_live_telemetry():
    msgs = _messages()
    r = render_chat(FakeTok(), msgs)
    assert r[:locate_probes(r, msgs)["P0_state_end"]].endswith("arrival rate 40.6 req/s")


def test_a_field_the_model_skipped_gets_no_probe():
    msgs = _messages(reasoning="Reasoning:\n  SLA: met, that is all.\nAction:")
    p = locate_probes(render_chat(FakeTok(), msgs), msgs)
    assert "P_sla" in p and "P_capacity" not in p
