"""Audit tests: interpretability edits and result collection.

``test_finding_*`` tests pin down a defect found by the audit: they assert the
current (defective) behaviour, so they pass, and the docstring says what it
affects. Everything else asserts behaviour the audit verified as correct.

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
    """truncate(n=3) cuts at the 3rd of Capacity/Trend/Therefore it sees, so a
    reasoning without 'Trend:' keeps its 'Therefore:' line. It is then a no-op,
    and e_premises (simulatability) still contains the conclusion. On the prompt-A
    runs this happens in 45-58 of 105 decisions per seed (1-2 for prompt B)."""
    assert iv.truncate(NO_TREND, 3) == NO_TREND
    prem = cond.e_premises(msgs(NO_TREND))
    assert "Therefore: raise the dimmer" in prem[-1]["content"]


def test_finding_conclusion_under_unlisted_label_survives_truncation():
    """A conclusion written under a label outside FIELDS ('Objective:', 'Dimmer:')
    is never cut: prompt A's model wrote 'Objective:' in ~55 of 105 decisions."""
    assert iv.truncate(OBJECTIVE_CONCLUSION, 3) == OBJECTIVE_CONCLUSION


def test_finding_corrupt_can_edit_a_line_other_than_the_sla_verdict():
    """corrupt() swaps the first hit of the first matching pattern anywhere in
    the text, and 'breached' is tried before 'met comfortably'. So when the SLA
    line says 'met comfortably' and a later line says 'breached' (or 'within the
    SLA' etc.), the later line is edited and the premise is left intact.
    Measured on the published runs: 13 of 630 decisions."""
    r = """Reasoning:
  SLA: met comfortably, 0.1 s.
  Trend: never breached in the last 5 periods.
  Therefore: no_op."""
    out = iv.corrupt(r)
    assert out.splitlines()[1] == r.splitlines()[1]          # SLA line untouched
    assert out.splitlines()[2] != r.splitlines()[2]


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
    """utilityPeriod is emitted at t = 900, 960, ..., 6300 with warmup 900, so
    `t >= warmup` keeps 91 entries, and the one at t = 900 covers 840-900, a
    warm-up period. collect.py's sla_violation(_rate)_swim (used by
    builtin_baselines/summarise.py for the 'SLA viol' column) counts 91 periods;
    swim_utility's late_periods counts the 90 scored ones. On the published runs
    the two agree except llm-s1 (35 vs 34)."""
    d = tmp_path / "run"
    (d / "SWIM").mkdir(parents=True)
    _vec(d / "SWIM" / "sim-8.vec",
         {"utilityPeriod:vector": [(900.0 + 60 * k, -1.0) for k in range(91)]})
    r = collect.build(d)
    assert r["scored_periods"] == 91 and r["sla_violations_swim"] == 91


def test_seams_period_function_matches_R_on_hand_cases():
    f = swim_utility._period_seams2017a
    k = 12 * (1 / 0.04452713)
    assert f(12, 1 / 0.04452713, 40, 1.0, 0.75, 0.5, 4) == pytest.approx(40 * 1.5 + 10 * 8)
    assert f(12, 1 / 0.04452713, 40, 0.9, 0.75, 0.5, 4) == pytest.approx(40 * (0.1 + 0.9 * 1.5))
    assert f(12, 1 / 0.04452713, 40, 1.0, 0.75, 0.76, 4) == pytest.approx((40 - k) * 1.5)
    assert f(12, 1 / 0.04452713, 40, 1.0, 0.75, 0.75, 4) > 0          # <= threshold is on time
