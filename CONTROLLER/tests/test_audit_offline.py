"""Audit tests (offline): the controller's side of the SWIM boundary.

Independent of test_offline.py. Every expectation here is derived from SWIM's
C++ source (AdaptInterface.cc, ReactiveAdaptationManager.cc, SimProbe.cc,
ExecutionManagerModBase.cc, Model.cc), not from the controller's docstrings.

Tests named ``test_finding_*`` document a discrepancy found by the audit; they
assert the *current* behaviour so they pass, and say in their docstring why it
matters.

Run:  cd CONTROLLER && python -m pytest tests/test_audit_offline.py -q
"""

from __future__ import annotations

import math
import socket
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller import (  # noqa: E402
    ContextBuilder, ControlLoop, DimmerMode, LLMPolicy, Observation,
    OpenAICompatBackend, ReactivePolicy, ReasoningStyle, SwimClient, Trajectory,
)
from controller.actions import (  # noqa: E402
    ADD_SERVER, NO_OP, REMOVE_SERVER, Action, Kind, UnsafeAction, is_legal, validate,
)
from controller.context import DEFAULT_EXEMPLARS  # noqa: E402


def obs(servers=3, active=3, max_servers=12, dimmer=0.9, brt=0.2, ort=0.4,
        btp=10.0, otp=30.0, arrival=40.0, utils=None):
    if utils is None:
        utils = tuple([0.5] * active) + tuple([0.0] * (max_servers - active))
    return Observation(servers=servers, active_servers=active, max_servers=max_servers,
                       dimmer=dimmer, basic_rt=brt, opt_rt=ort, basic_throughput=btp,
                       opt_throughput=otp, arrival_rate=arrival, utilizations=tuple(utils))


def D(v):
    return Action(Kind.SET_DIMMER, v)


# ---------------------------------------------------------------------------
# 1. letter -> action mapping, legend, exemplars
# ---------------------------------------------------------------------------
def test_levels_mapping_and_legend_are_the_same_thing():
    b = ContextBuilder(boot_delay=180)
    o = obs()
    opts = b.options_for(o)
    assert opts == [("A", ADD_SERVER), ("B", REMOVE_SERVER), ("C", NO_OP), ("D", D(0.0)),
                    ("E", D(0.25)), ("F", D(0.5)), ("G", D(0.75)), ("H", D(1.0))]
    # every legend label is exactly the executed command string
    for (oid, label), (oid2, act) in zip(b.legend_entries(opts), opts):
        assert oid == oid2 and label == str(act)
    # and the legend in the system prompt is exactly that list
    sys_text = b.system_text(opts, o.max_servers)
    for oid, act in opts:
        assert f"\n  {oid}  {act}\n" in sys_text + "\n"


def test_legend_is_state_independent_in_levels_mode():
    b = ContextBuilder()
    texts = {b.system_text(b.options_for(obs(dimmer=d, servers=s, active=a)), 12)
             for d in (0.0, 0.25, 0.9, 1.0) for s, a in ((1, 1), (4, 3), (12, 12))}
    assert len(texts) == 1


def test_exemplar_letters_mean_what_the_reasoning_says_in_levels_mode():
    b = ContextBuilder()
    opts = dict(b.options_for(obs()))
    (_, r1, a1), (_, r2, a2) = DEFAULT_EXEMPLARS
    assert opts[a1] == ADD_SERVER and "add a server" in r1
    assert opts[a2].kind is Kind.SET_DIMMER and opts[a2].value > 0.30 and "raise the dimmer" in r2


def test_finding_step_mode_exemplar_letter_does_not_exist():
    """STEP mode offers only A-E, but exemplar 2 answers 'G'. No published run
    uses STEP mode (run_controller default is LEVELS and no job script passes
    --dimmer-mode), so this affects nothing reported."""
    b = ContextBuilder(dimmer_mode=DimmerMode.STEP)
    ids = [oid for oid, _ in b.options_for(obs())]
    assert ids == list("ABCDE")
    assert DEFAULT_EXEMPLARS[1][2] not in ids


# ---------------------------------------------------------------------------
# 2. legality vs SWIM's guards
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("o,action,legal", [
    (obs(servers=4, active=3), ADD_SERVER, False),        # booting
    (obs(servers=4, active=3), REMOVE_SERVER, False),     # booting
    (obs(servers=12, active=12), ADD_SERVER, False),      # at max
    (obs(servers=11, active=11), ADD_SERVER, True),
    (obs(servers=1, active=1), REMOVE_SERVER, False),     # last server
    (obs(servers=2, active=2), REMOVE_SERVER, True),
    (obs(dimmer=1.0), D(1.0), False),                     # no change
    (obs(dimmer=0.9), D(1.0), True),
    (obs(dimmer=0.9), D(1.5), False),
    (obs(dimmer=0.9), D(-0.1), False),
    (obs(dimmer=0.9), D(float("nan")), False),
    (obs(servers=4, active=3), D(0.5), True),             # dimmer is fine while booting
])
def test_legality(o, action, legal):
    assert is_legal(action, o) is legal
    if action.kind in (Kind.ADD_SERVER, Kind.REMOVE_SERVER) or (
            action.kind is Kind.SET_DIMMER and not (0 <= action.value <= 1)):
        if legal:
            validate(action, o)
        else:
            with pytest.raises(UnsafeAction):
                validate(action, o)


# ---------------------------------------------------------------------------
# 3. bytes on the wire, and executed == recorded
# ---------------------------------------------------------------------------
class RecordingSwim:
    """Speaks AdaptInterface's line protocol and records every line received."""

    def __init__(self, state):
        self.state = dict(state)
        self.received: list[str] = []
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        conn, _ = self.srv.accept()
        f = conn.makefile("rb")
        for raw in f:
            line = raw.decode().rstrip("\r\n")
            self.received.append(line)
            cmd, *args = line.split(" ")
            if cmd.startswith("get_utilization"):
                n = int(args[0][6:])
                reply = "0.5" if n <= self.state["get_active_servers"] else \
                    f"error: server '{args[0]}' does no exist"
            elif cmd.startswith("get_"):
                reply = str(self.state[cmd])
            else:
                reply = "OK"
            conn.sendall((reply + "\n").encode())


def test_each_action_is_sent_as_exactly_one_swim_command():
    cases = [(ADD_SERVER, "add_server"), (REMOVE_SERVER, "remove_server"),
             (D(0.0), "set_dimmer 0"), (D(0.25), "set_dimmer 0.25"),
             (D(0.5), "set_dimmer 0.5"), (D(0.75), "set_dimmer 0.75"),
             (D(1.0), "set_dimmer 1")]
    for action, wire in cases:
        fake = RecordingSwim({"get_servers": 3, "get_active_servers": 3, "get_max_servers": 12,
                              "get_dimmer": 0.9, "get_basic_rt": 0.1, "get_opt_rt": 0.2,
                              "get_basic_throughput": 1.0, "get_opt_throughput": 2.0,
                              "get_arrival_rate": 3.0})

        class Fixed:
            name = "fixed"

            def __call__(self, period, o, traj):
                from controller.policies import PolicyResult
                return PolicyResult(action=action, policy="fixed")

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            client = SwimClient(port=fake.port)
            loop = ControlLoop(client, Fixed(), Trajectory(), run_dir=Path(tmp), run_id="t",
                               period_seconds=0.01, max_periods=1)
            with client:
                loop.run()
            import json
            rec = json.loads((Path(tmp) / "decisions.jsonl").read_text())
        actions_sent = [l for l in fake.received if not l.startswith("get_")]
        assert actions_sent == [wire]
        assert rec["decision"]["action"] == str(action) and rec["execution"]["sent"]
        # AdaptInterface: dimmer = atof(arg); brownout = 1 - dimmer. The value round-trips.
        if action.kind is Kind.SET_DIMMER:
            assert float(wire.split()[1]) == action.value


def test_sense_reads_what_swim_means():
    fake = RecordingSwim({"get_servers": 4, "get_active_servers": 3, "get_max_servers": 12,
                          "get_dimmer": 0.75, "get_basic_rt": 0.1, "get_opt_rt": 0.5,
                          "get_basic_throughput": 30.0, "get_opt_throughput": 10.0,
                          "get_arrival_rate": 41.0})
    with SwimClient(port=fake.port) as c:
        o = c.sense()
    assert (o.servers, o.active_servers, o.max_servers, o.dimmer) == (4, 3, 12, 0.75)
    assert o.booting
    # SimProbe::getUpdatedObservations: sum over servers; throughput-weighted RT
    assert o.total_utilization == pytest.approx(1.5)
    assert o.spare == pytest.approx(3 - 1.5)
    assert o.avg_rt == pytest.approx((0.1 * 30 + 0.5 * 10) / 40)
    assert [l for l in fake.received if l.startswith("get_utilization")] == \
        [f"get_utilization server{i}" for i in range(1, 13)]


# ---------------------------------------------------------------------------
# 4. scoring -> distribution -> masking -> argmax
# ---------------------------------------------------------------------------
class DistBackend:
    name = "dist"

    def __init__(self, dist):
        self.dist = dist

    def generate_chat(self, messages, **kw):
        return "Reasoning:\n  SLA: x\n  Therefore: y"

    def score_chat(self, messages, options):
        return {k: v for k, v in self.dist.items() if k in options}


def _decide(dist, o):
    b = ContextBuilder(boot_delay=180)
    t = Trajectory()
    t.record_observation(0, o)
    return LLMPolicy(DistBackend(dist), b, temperature=0)(0, o, t)


def test_masking_renormalises_legal_mass_and_argmax_is_executed():
    o = obs(servers=4, active=3, dimmer=1.0)       # booting, dimmer at 1
    raw = {"A": 0.5, "B": 0.1, "C": 0.1, "D": 0.05, "E": 0.05, "F": 0.05, "G": 0.1, "H": 0.05}
    r = _decide(raw, o)
    assert r.raw_distribution == raw
    legal = {"C", "D", "E", "F", "G"}               # A, B illegal (booting), H = current dimmer
    assert set(r.distribution) == legal
    tot = sum(raw[k] for k in legal)
    for k in legal:
        assert r.distribution[k] == pytest.approx(raw[k] / tot)
    assert r.action in (NO_OP, D(0.75))             # tie C/G at 0.1: first in order wins
    assert r.action == NO_OP


def test_all_legal_options_missing_falls_back_to_no_op():
    o = obs(servers=4, active=3, dimmer=1.0)
    r = _decide({"A": 0.9, "B": 0.1}, o)
    assert r.action == NO_OP and r.notes.get("degenerate_distribution")


def test_openai_chat_scoring_parses_top_logprobs():
    be = OpenAICompatBackend("http://x", "m")
    table = [{"token": " A", "logprob": -0.1}, {"token": "A", "logprob": -2.0},
             {"token": " C", "logprob": -1.0}, {"token": "Add", "logprob": -0.05},
             {"token": "H", "logprob": -3.0}]
    be._post = lambda path, payload: {"choices": [{"logprobs": {"content": [
        {"top_logprobs": table}]}}]}
    dist = be.score_chat([], list("ABCDEFGH"))
    z = math.exp(-0.1) + math.exp(-1.0) + math.exp(-3.0)
    assert dist == pytest.approx({"A": math.exp(-0.1) / z, "C": math.exp(-1.0) / z,
                                  "H": math.exp(-3.0) / z})
    assert be.last_missing_ids == list("BDEFG")


# ---------------------------------------------------------------------------
# 5. the reactive port vs a transcription of ReactiveAdaptationManager::evaluate
# ---------------------------------------------------------------------------
def swim_reactive(o: Observation, levels: int) -> Action:
    """Line-by-line transcription of the C++, with SWIM's own avgResponseTime
    (SimProbe: (brt*btp + ort*otp)/(btp+otp), NaN when nothing completed)."""
    step = 1.0 / (levels - 1)
    dimmer = o.dimmer
    spare = o.active_servers - sum(o.utilizations)
    booting = o.servers > o.active_servers
    tp = o.basic_throughput + o.opt_throughput
    rt = (o.basic_rt * o.basic_throughput + o.opt_rt * o.opt_throughput) / tp if tp else math.nan
    if rt > 0.75:
        if not booting and o.servers < o.max_servers:
            return ADD_SERVER
        elif dimmer > 0.0:
            return D(max(0.0, dimmer - step))
    elif rt < 0.75:
        if spare > 1:
            if dimmer < 1.0:
                return D(min(1.0, dimmer + step))
            elif not booting and o.servers > 1:
                return REMOVE_SERVER
    return NO_OP


def _grid():
    for levels in (5, 10):
        for rt in (0.1, 0.75, 2.0):
            for s, a in ((1, 1), (2, 1), (3, 3), (12, 12), (12, 11)):
                for u in (0.0, 0.5, 0.95):
                    for d in (0.0, 0.1, 0.5, 1.0):
                        yield levels, obs(servers=s, active=a, dimmer=d, brt=rt, ort=rt,
                                          utils=[u] * a)


def test_reactive_port_matches_swim_when_there_is_traffic():
    for levels, o in _grid():
        port = ReactivePolicy(dimmer_levels=levels).decide(o)
        ref = swim_reactive(o, levels)
        if ref.kind is Kind.SET_DIMMER:
            assert port.kind is Kind.SET_DIMMER and port.value == pytest.approx(ref.value, abs=1e-6)
        else:
            assert port == ref, (levels, o)


def test_finding_reactive_port_acts_on_a_period_with_no_completed_requests():
    """SWIM's avgResponseTime is 0/0 = NaN when nothing completed in the window,
    so neither branch fires and the built-in manager does nothing. The port
    reads avg_rt as 0.0 (< SLA) and may raise the dimmer or remove a server.
    Only reachable when throughput is exactly zero (e.g. the controller's
    period 0 at t~1 s); affects the socket-driven reactive arm only."""
    o = obs(servers=3, active=3, dimmer=0.9, btp=0.0, otp=0.0, utils=[0.0] * 3)
    assert swim_reactive(o, 10) == NO_OP
    assert ReactivePolicy(dimmer_levels=10).decide(o) == D(1.0)
