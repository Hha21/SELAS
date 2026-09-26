"""Checks on the objective swap and the mediation summary (no model needed).

Run:  python -m pytest experiments/mediation/test_mediation.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "CONTROLLER"))

from analyse_mediation import summarise  # noqa: E402
from controller import ContextBuilder, Trajectory  # noqa: E402
from controller.context import OBJECTIVES  # noqa: E402
from controller.swim import synthetic_observation  # noqa: E402
from objective_swap import swap_messages, swap_objective  # noqa: E402


def _messages(objective: str, feedback: bool = False) -> list[dict]:
    t = Trajectory()
    t.record_observation(5, synthetic_observation(servers=3, active_servers=3, max_servers=12))
    msgs, _ = ContextBuilder(objective=objective, boot_delay=180,
                             utility_feedback=feedback).build_messages(5, t, reasoning="Reasoning:\n  SLA: met.")
    return msgs


@pytest.mark.parametrize("old", OBJECTIVES)
@pytest.mark.parametrize("new", OBJECTIVES)
def test_swap_gives_exactly_the_prompt_the_builder_would(old, new):
    got = swap_messages(_messages(old), old, new, 12)
    want = _messages(new)
    assert got == want                      # system swapped; exemplars, state, reasoning untouched


def test_swap_refuses_a_block_that_is_not_the_claimed_objective():
    with pytest.raises(ValueError):
        swap_objective(_messages("formula")[0]["content"], "priority", "none", 12)


def test_swap_on_a_recorded_decision_if_available():
    rec = Path("/tmp/claude-1000/-home-lain-PHD-SummerWork/f8456273-b8b9-4ffd-a323-2e171576a3e5"
               "/scratchpad/newfmt/k2-words-s0.jsonl")
    if not rec.exists():
        pytest.skip("no recorded run copied locally")
    import json
    r = json.loads(rec.read_text().splitlines()[40])
    out = swap_messages(r["messages"], "priority", "priority-no3", 12)
    assert "run as few servers" in r["messages"][0]["content"]
    assert "run as few servers" not in out[0]["content"]
    assert out[1:] == r["messages"][1:]


def _row(orig, direct, total, reason, action="remove_server"):
    opts = [["A", "add_server"], ["B", "remove_server"], ["C", "no_op"]]
    return {"options": opts, "legal_ids": ["A", "B", "C"], "action_recorded": action,
            "dist_orig": orig, "dist_direct": direct, "dist_total": total, "dist_reason": reason}


def test_summary_separates_direct_and_reasoning_paths():
    rem, keep = {"B": 0.9, "C": 0.1}, {"B": 0.1, "C": 0.9}
    rows = [
        _row(rem, rem, keep, keep),     # the new reasoning carries the change; the prompt alone does not
        _row(rem, keep, keep, rem),     # the prompt carries it with the reasoning held fixed
        _row(rem, rem, rem, rem),       # nothing changes
    ]
    s = summarise(rows)
    assert s["control_agreement"] == 1.0
    assert (s["flips_total"], s["flips_direct"], s["flips_reason"]) == (2, 1, 1)
    assert s["carried_direct"] == 0.5 and s["carried_reason"] == 0.5
    assert s["p_remove_orig"] == pytest.approx(0.9)
