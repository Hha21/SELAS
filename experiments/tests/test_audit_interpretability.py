"""Audit tests: interpretability edits and result collection.

``test_finding_*`` tests began as pins on a defect the audit found (F1-F4 in
PLAN.md); each now asserts the fixed behaviour, and its docstring says what was
wrong. Everything else asserts behaviour the audit verified as correct.

Run:  python -m pytest experiments/tests/test_audit_interpretability.py -q
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for p in ("experiments/faithfulness", "experiments/simulatability",
          "experiments/counterfactual", "experiments/controller_comparison", "CONTROLLER"):
    sys.path.insert(0, str(ROOT / p))

import interventions as iv  # noqa: E402
import legality  # noqa: E402
import conditions as cond  # noqa: E402
import edits as E  # noqa: E402
import collect  # noqa: E402
import swim_utility  # noqa: E402

STANDARD = """Reasoning:
  SLA: met comfortably, 0.102 s against 0.750 s.
  Capacity: 3 of 12 servers, spare 2.10.
  Trend: arrival rate steady.
  Therefore: raise the dimmer to 1.0."""

NO_TREND = """Reasoning:
  SLA: met comfortably, 0.102 s against 0.750 s.
  Capacity: 3 of 12 servers, spare 2.10.
  Therefore: raise the dimmer to 1.0."""

OBJECTIVE_CONCLUSION = """Reasoning:
  SLA: met comfortably, 0.102 s against 0.750 s.
  Capacity: 3 of 12 servers, spare 2.10.
  Trend: arrival rate steady.
  Objective: maximise the dimmer, so raise it to 1.0."""

STATE = """---
Period 12
  servers        3 active, 3 provisioned, max 12
  dimmer         0.90
  response time  0.102 s   (SLA 0.750 s, met)
  utilisation    0.90 total across 3 server(s), spare 2.10
  arrival rate   40.0 req/s
  utility        -12.0 this period
  last 3 periods
    response time   0.10   0.11   0.10
    arrival rate    39.0   41.0   40.0
    servers            3      3      3
    dimmer          0.90   0.90   0.90
    utility           58     60     58
  recent actions
    period 11   no_op                  response time then fell 0.010 s"""


def msgs(reasoning, state=STATE):
    return [{"role": "system", "content": "sys"},
            {"role": "user", "content": "exemplar"}, {"role": "assistant", "content": "Action: A"},
            {"role": "user", "content": state},
            {"role": "assistant", "content": iv.assistant_turn(reasoning)}]


# -- truncation / premises ------------------------------------------------------
def test_truncate3_removes_conclusion_on_standard_scaffold():
    out = iv.truncate(STANDARD, 3)
    assert "Therefore" not in out and "Trend:" in out


def test_finding_truncate3_keeps_conclusion_when_a_field_is_missing():
    """F1, fixed. truncate(n=3) cut at the 3rd of Capacity/Trend/Therefore it
    saw, so a reasoning without 'Trend:' kept its 'Therefore:' line and
    e_premises (simulatability) still held the conclusion. On the prompt-A runs
    that was 45-58 of 105 decisions per seed. The last field is now the
    conclusion, whatever precedes it."""
    out = iv.truncate(NO_TREND, 3)
    assert "Therefore" not in out and "Capacity:" in out
    prem = cond.e_premises(msgs(NO_TREND))
    assert "Therefore" not in prem[-1]["content"] and "Capacity:" in prem[-1]["content"]


def test_finding_conclusion_under_unlisted_label_survives_truncation():
    """F1, fixed. A conclusion under a label outside FIELDS ('Objective:') was
    never cut: prompt A's model put it there in ~55 of 105 decisions."""
    out = iv.truncate(OBJECTIVE_CONCLUSION, 3)
    assert "Objective" not in out and "Trend:" in out


def test_truncate_keeps_premises_the_model_added():
    """Extra premise fields stay in the premises arm; only the last field goes,
    and the shorter arms never reach the conclusion."""
    r = STANDARD.replace("  Therefore:", "  Recent Actions: removals raised response time.\n  Therefore:")
    assert iv.truncate(r, 3).rstrip().endswith("removals raised response time.")
    assert "Trend" not in iv.truncate(r, 2) and "Capacity" in iv.truncate(r, 2)
    three = STANDARD.replace("  Trend: arrival rate steady.\n", "")      # SLA, Capacity, Therefore
    assert iv.truncate(three, 2) == iv.truncate(three, 3)                # capped below the conclusion


def test_finding_corrupt_can_edit_a_line_other_than_the_sla_verdict():
    """F2, fixed. corrupt() swapped the first match of the first pattern
    anywhere in the text, and 'breached' was tried before 'met comfortably', so
    a later 'never breached' line was edited and the premise left intact (13 of
    630 decisions). Only the SLA field is edited now."""
    r = """Reasoning:
  SLA: met comfortably, 0.1 s.
  Trend: never breached in the last 5 periods.
  Therefore: no_op."""
    out = iv.corrupt(r)
    assert out.splitlines()[1] == "  SLA: breached, 0.1 s."
    assert out.splitlines()[2:] == r.splitlines()[2:]


@pytest.mark.parametrize("line,expected", [
    ("  SLA: severely breached, 3.6 s.", "  SLA: met comfortably, 3.6 s."),
    ("  SLA: not breached, 0.2 s.", "  SLA: breached, 0.2 s."),
    ("  SLA: met, 0.2 s.", "  SLA: breached, 0.2 s."),
    ("  SLA: BREACHED at 1.1 s.", "  SLA: MET at 1.1 s."),
])
def test_corrupt_negates_the_whole_verdict(line, expected):
    """Word-for-word negation made "severely breached" into "severely met
    comfortably" on 84 of 630 recorded SLA lines."""
    out = iv.corrupt(f"Reasoning:\n{line}\n  Therefore: no_op.")
    assert out.splitlines()[1] == expected


def test_corrupt_without_a_verdict_on_the_sla_line_is_a_no_op():
    r = "Reasoning:\n  SLA: 0.2 s.\n  Trend: never breached.\n  Therefore: no_op."
    assert iv.corrupt(r) == r


def test_filler_keeps_every_label_the_model_wrote():
    out = iv.filler(OBJECTIVE_CONCLUSION)
    assert [l.split(":")[0].strip() for l in out.splitlines()] == \
        ["Reasoning", "SLA", "Capacity", "Trend", "Objective"]
    assert all(set(l.split(":", 1)[1]) <= {" ", "."} for l in out.splitlines()[1:])


# -- legality (F3) ----------------------------------------------------------------
def _record(servers=3, active=3, dimmer=0.9, distribution=None):
    opts = [["A", "add_server"], ["B", "remove_server"], ["C", "no_op"],
            ["D", "set_dimmer 0"], ["E", "set_dimmer 0.25"], ["F", "set_dimmer 0.5"],
            ["G", "set_dimmer 0.75"], ["H", "set_dimmer 1"]]
    return {"period": 1, "observation": {
                "servers": servers, "active_servers": active, "max_servers": 12,
                "dimmer": dimmer, "basic_rt": 0.2, "opt_rt": 0.3, "basic_throughput": 10.0,
                "opt_throughput": 20.0, "arrival_rate": 30.0, "utilizations": [0.5] * active},
            "decision": {"options": opts, "distribution": distribution or {"C": 1.0}}}


def test_finding_legal_ids_come_from_the_state_not_the_recorded_distribution():
    """F3, fixed. legal_ids were the keys of the recorded distribution, which
    holds only options in the endpoint's top-20, so a legal option the model
    gave almost no mass was treated as illegal (5-8 of 105 for prompt A)."""
    # Everything is legal here, though the recorded distribution holds only C.
    assert legality.legal_ids(_record(distribution={"C": 1.0})) == list("ABCDEFGH")
    ids = legality.legal_ids(_record(dimmer=0.75))
    assert ids == ["A", "B", "C", "D", "E", "F", "H"]                 # G would not change anything
    assert legality.legal_ids(_record(servers=4, active=3)) == list("CDEFGH")    # booting
    assert "B" not in legality.legal_ids(_record(servers=1, active=1))


def test_legal_ids_refuse_a_legend_that_does_not_match():
    r = _record()
    r["decision"]["options"][6] = ["G", "set_dimmer 0.7"]
    with pytest.raises(ValueError):
        legality.legal_ids(r)


# -- rebuilding and conditions touch only what they claim ------------------------
def test_rebuild_messages_only_replaces_final_turn():
    m = msgs(STANDARD)
    out = iv.rebuild_messages(m, "Reasoning:\n  SLA: x")
    assert out[:-1] == m[:-1]
    assert out[-1]["content"].endswith("Action:")
    assert iv.rebuild_messages(m, STANDARD) == m                  # original reproduces


def test_conditions_edit_only_the_live_turns():
    m = msgs(STANDARD)
    assert cond.xe(m) == m
    x = cond.x(m)
    assert x[:-1] == m[:-1] and x[-1]["content"] == "Action:"
    e = cond.e(m)
    assert e[:-2] == m[:-2] and e[-1] == m[-1]
    assert "0.102" not in e[-2]["content"] and "Period 12" in e[-2]["content"]


# -- counterfactual edits --------------------------------------------------------
@pytest.mark.parametrize("name", list(E.EDITS))
def test_counterfactual_edit_changes_only_its_field(name):
    fn, _ = E.EDITS[name]
    new, meta = fn(STATE)
    old_l, new_l = STATE.splitlines(), new.splitlines()
    assert len(old_l) == len(new_l)
    changed = {o.split()[0] + " " + (o.split()[1] if len(o.split()) > 1 else "")
               for o, n in zip(old_l, new_l) if o != n}
    allowed = {"response time", "arrival rate", "utilisation 0.90", "utility -12.0", "utility 58"}
    assert changed <= allowed, changed
    # the servers / dimmer lines (legality inputs) are never touched
    for o, n in zip(old_l, new_l):
        if o.strip().startswith(("servers", "dimmer")):
            assert o == n


@pytest.mark.parametrize("name", list(E.EDITS))
def test_counterfactual_edit_on_the_current_state_format(name):
    """The same edits on the state as the controller now renders it (utilisation
    as a mean in percent), including the utility line prompt B shows."""
    sys.path.insert(0, str(ROOT / "CONTROLLER"))
    from controller import ContextBuilder, Observation, Trajectory
    t = Trajectory()
    for k in range(3):
        t.record_observation(10 + k, Observation(
            servers=3, active_servers=3, max_servers=12, dimmer=0.9, basic_rt=0.1,
            opt_rt=0.1, basic_throughput=40.0, opt_throughput=0.0, arrival_rate=40.0,
            utilizations=(0.3, 0.3, 0.3)))
    state = ContextBuilder(utility_feedback=True).state_block(12, t)
    new, meta = E.EDITS[name][0](state)
    assert new != state and meta["edit"]
    changed = {o.split()[0] for o, n in zip(state.splitlines(), new.splitlines()) if o != n}
    assert changed <= {"response", "arrival", "utilisation", "utility"}, changed
    if name.startswith("spare"):
        assert "active server(s), spare capacity" in new


def test_rt_edit_keeps_verdict_and_history_consistent():
    new, _ = E.EDITS["rt_breached"][0](STATE)
    assert "9.500 s   (SLA 0.750 s, BREACHED)" in new
    assert new.splitlines()[9].rstrip().endswith("9.50")
    # prompt B: utility line recomputed with the SEAMS 2017A late branch
    assert "  utility        -337.3 this period" in new or "utility        -" in new


# -- collection ------------------------------------------------------------------
def _vec(path: Path, series: dict[str, list[tuple[float, float]]]):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE run (runId INTEGER, simtimeExp INTEGER)")
    c.execute("INSERT INTO run VALUES (1, -12)")
    c.execute("CREATE TABLE runAttr (runId INTEGER, attrName TEXT, attrValue TEXT)")
    c.execute("INSERT INTO runAttr VALUES (1, 'simtimeExp', '-12')")
    c.execute("CREATE TABLE vector (vectorId INTEGER, runId INTEGER, moduleName TEXT, vectorName TEXT)")
    c.execute("CREATE TABLE vectorData (vectorId INTEGER, eventNumber INTEGER, simtimeRaw INTEGER, value REAL)")
    for i, (name, rows) in enumerate(series.items()):
        c.execute("INSERT INTO vector VALUES (?, 1, 'SWIM.monitor', ?)", (i, name))
        for k, (t, v) in enumerate(rows):
            c.execute("INSERT INTO vectorData VALUES (?, ?, ?, ?)", (i, k, int(round(t * 1e12)), v))
    c.commit()
    c.close()


def test_finding_swim_violation_count_includes_the_warmup_boundary_period(tmp_path):
    """F4, fixed. utilityPeriod is emitted at t = 900, 960, ..., 6300 with
    warmup 900, so `t >= warmup` kept 91 entries, and the one at t = 900 covers
    840-900, a warm-up period. collect.py's sla_violation(_rate)_swim (the 'SLA
    viol' column of builtin_baselines/summarise.py) counted 91 periods where
    swim_utility's late_periods counts the 90 scored ones."""
    d = tmp_path / "run"
    (d / "SWIM").mkdir(parents=True)
    _vec(d / "SWIM" / "sim-8.vec",
         {"utilityPeriod:vector": [(900.0 + 60 * k, -1.0) for k in range(91)]})
    r = collect.build(d)
    assert r["scored_periods"] == 90 and r["sla_violations_swim"] == 90
    assert r["utility_cumulative_icac2016"][0][0] == 960.0


def test_seams_period_function_matches_R_on_hand_cases():
    f = swim_utility._period_seams2017a
    k = 12 * (1 / 0.04452713)
    assert f(12, 1 / 0.04452713, 40, 1.0, 0.75, 0.5, 4) == pytest.approx(40 * 1.5 + 10 * 8)
    assert f(12, 1 / 0.04452713, 40, 0.9, 0.75, 0.5, 4) == pytest.approx(40 * (0.1 + 0.9 * 1.5))
    assert f(12, 1 / 0.04452713, 40, 1.0, 0.75, 0.76, 4) == pytest.approx((40 - k) * 1.5)
    assert f(12, 1 / 0.04452713, 40, 1.0, 0.75, 0.75, 4) > 0          # <= threshold is on time
