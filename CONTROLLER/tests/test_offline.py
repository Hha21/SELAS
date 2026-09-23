"""Offline tests: no SWIM container, no model, no network beyond localhost.

The fake SWIM server speaks the real line protocol from
``SWIM/src/externalControl/AdaptInterface.cc``, including the part that matters
most and is easiest to get wrong: several commands may arrive in one buffer, and
each gets its own reply line.
"""

from __future__ import annotations

import socket
import threading

import pytest

from controller import (
    ContextBuilder, DimmerMode, LLMPolicy, Observation, ReactivePolicy,
    ReasoningStyle, StubBackend, SwimClient, Trajectory,
)
from controller.actions import (
    ADD_SERVER, NO_OP, REMOVE_SERVER, Action, Kind, is_legal, legal_actions, validate,
)
from controller.actions import UnsafeAction
from controller.context import P0, P_ACTION


# --------------------------------------------------------------------------
# a fake SWIM
# --------------------------------------------------------------------------
class FakeSwim:
    """Minimal stand-in for AdaptInterface, with the same reply shapes."""

    def __init__(self) -> None:
        self.state = {
            "get_servers": 2, "get_active_servers": 2, "get_max_servers": 3,
            "get_dimmer": 0.5, "get_basic_rt": 0.4, "get_opt_rt": 1.2,
            "get_basic_throughput": 10.0, "get_opt_throughput": 5.0,
            "get_arrival_rate": 15.0,
        }
        self.utilization = {"server1": 0.8, "server2": 0.9, "server3": -1.0}
        self.received: list[str] = []
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _reply(self, line: str) -> str:
        self.received.append(line)
        parts = line.split()
        if not parts:
            return ""
        cmd, args = parts[0], parts[1:]
        if cmd in ("add_server", "remove_server", "set_dimmer"):
            if cmd == "set_dimmer":
                if not args:
                    return "error: missing dimmer argument\n"
                self.state["get_dimmer"] = float(args[0])
            return "OK\n"
        if cmd == "get_utilization":
            if not args:
                return "error: missing server argument\n"
            value = self.utilization.get(args[0])
            if value is None:
                return f"error: server '{args[0]}' does no exist\n"
            if value < 0:
                return f"error: server '{args[0]}' does no exist\n"
            return f"{value}\n"
        if cmd in self.state:
            return f"{self.state[cmd]}\n"
        return "error: unknown command\n"

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                buf = b""
                while True:
                    try:
                        chunk = conn.recv(4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    buf += chunk
                    # Reply to every complete line in the buffer, as SWIM does.
                    while b"\n" in buf:
                        raw, buf = buf.split(b"\n", 1)
                        conn.sendall(self._reply(raw.decode().strip()).encode())


@pytest.fixture
def fake_swim():
    return FakeSwim()


# --------------------------------------------------------------------------
# client + derived metrics
# --------------------------------------------------------------------------
def test_sense_round_trip(fake_swim):
    with SwimClient(host="127.0.0.1", port=fake_swim.port, timeout=5.0) as client:
        obs = client.sense()

    assert obs.servers == 2 and obs.active_servers == 2 and obs.max_servers == 3
    assert obs.dimmer == pytest.approx(0.5)
    # throughput-weighted: (0.4*10 + 1.2*5) / 15
    assert obs.avg_rt == pytest.approx((0.4 * 10 + 1.2 * 5) / 15)
    # server3 replies with an error and must contribute nothing
    assert obs.total_utilization == pytest.approx(1.7)
    assert obs.mean_utilization == pytest.approx(0.85)
    assert obs.spare == pytest.approx(2 - 1.7)
    assert obs.booting is False


def test_sense_is_pipelined(fake_swim):
    """All nine scalars go out together, then the utilisation batch."""
    with SwimClient(host="127.0.0.1", port=fake_swim.port, timeout=5.0) as client:
        client.sense()
    assert fake_swim.received[:3] == ["get_servers", "get_active_servers", "get_max_servers"]
    assert fake_swim.received.count("get_utilization server1") == 1


def test_actions_reach_swim(fake_swim):
    with SwimClient(host="127.0.0.1", port=fake_swim.port, timeout=5.0) as client:
        assert client.add_server() == "OK"
        assert client.set_dimmer(0.25) == "OK"
    assert "set_dimmer 0.25" in fake_swim.received


def test_reconnects_after_drop(fake_swim):
    client = SwimClient(host="127.0.0.1", port=fake_swim.port, timeout=5.0)
    client.connect()
    client.sense()
    client.close()               # simulate a dropped connection
    assert client.sense().servers == 2


def test_zero_throughput_has_no_response_time():
    obs = _obs(basic_tp=0.0, opt_tp=0.0)
    assert obs.avg_rt == 0.0
    assert obs.has_traffic is False


# --------------------------------------------------------------------------
# the reactive oracle
# --------------------------------------------------------------------------
def _obs(**kw) -> Observation:
    base = dict(
        servers=2, active_servers=2, max_servers=3, dimmer=0.5,
        basic_rt=0.4, opt_rt=0.4, basic_throughput=10.0, opt_throughput=0.0,
        arrival_rate=15.0, utilizations=(0.5, 0.5),
    )
    # allow the throughput shorthand used above
    if "basic_tp" in kw:
        base["basic_throughput"] = kw.pop("basic_tp")
    if "opt_tp" in kw:
        base["opt_throughput"] = kw.pop("opt_tp")
    base.update(kw)
    return Observation(**base)


def test_breach_adds_a_server_when_headroom_exists():
    obs = _obs(basic_rt=1.0, opt_rt=1.0)
    assert ReactivePolicy().decide(obs) == ADD_SERVER


def test_breach_at_max_servers_lowers_the_dimmer():
    obs = _obs(servers=3, active_servers=3, max_servers=3, basic_rt=1.0, opt_rt=1.0,
               utilizations=(0.9, 0.9, 0.9), dimmer=0.5)
    assert ReactivePolicy().decide(obs) == Action(Kind.SET_DIMMER, 0.25)


def test_breach_while_booting_lowers_the_dimmer():
    """No scaling while a server boots -- servers > active_servers."""
    obs = _obs(servers=3, active_servers=2, basic_rt=1.0, opt_rt=1.0, dimmer=0.5)
    assert ReactivePolicy().decide(obs) == Action(Kind.SET_DIMMER, 0.25)


def test_dimmer_floor_is_zero():
    obs = _obs(servers=3, active_servers=3, max_servers=3, basic_rt=1.0, opt_rt=1.0,
               dimmer=0.0)
    assert ReactivePolicy().decide(obs) == NO_OP


def test_sla_met_with_spare_raises_the_dimmer():
    obs = _obs(basic_rt=0.1, opt_rt=0.1, utilizations=(0.3, 0.3), dimmer=0.5)
    assert obs.spare == pytest.approx(1.4)
    assert ReactivePolicy().decide(obs) == Action(Kind.SET_DIMMER, 0.75)


def test_sla_met_at_full_dimmer_removes_a_server():
    obs = _obs(basic_rt=0.1, opt_rt=0.1, utilizations=(0.2, 0.2), dimmer=1.0)
    assert ReactivePolicy().decide(obs) == REMOVE_SERVER


def test_sla_met_without_spare_does_nothing():
    obs = _obs(basic_rt=0.1, opt_rt=0.1, utilizations=(0.9, 0.9), dimmer=0.5)
    assert obs.spare == pytest.approx(0.2)
    assert ReactivePolicy().decide(obs) == NO_OP


def test_reactive2_drops_the_spare_guard():
    obs = _obs(basic_rt=0.1, opt_rt=0.1, utilizations=(0.9, 0.9), dimmer=0.5)
    assert ReactivePolicy(require_spare=False).decide(obs) == Action(Kind.SET_DIMMER, 0.75)


def test_response_time_exactly_on_threshold_does_nothing():
    """SWIM compares strictly > then strictly <, so the boundary is inert."""
    obs = _obs(basic_rt=0.75, opt_rt=0.75, utilizations=(0.1, 0.1), dimmer=0.5)
    assert obs.avg_rt == pytest.approx(0.75)
    assert ReactivePolicy().decide(obs) == NO_OP


# --------------------------------------------------------------------------
# action space
# --------------------------------------------------------------------------
def test_cannot_scale_while_booting():
    obs = _obs(servers=3, active_servers=2)
    assert not is_legal(ADD_SERVER, obs)
    assert not is_legal(REMOVE_SERVER, obs)
    assert is_legal(NO_OP, obs)


def test_cannot_remove_the_last_server():
    obs = _obs(servers=1, active_servers=1, utilizations=(0.5,))
    assert not is_legal(REMOVE_SERVER, obs)


def test_a_dimmer_move_to_the_current_value_is_not_an_action():
    obs = _obs(dimmer=0.5)
    assert not is_legal(Action(Kind.SET_DIMMER, 0.5), obs)
    assert is_legal(Action(Kind.SET_DIMMER, 0.7), obs)


def test_step_mode_matches_the_reactive_action_space():
    obs = _obs(dimmer=0.5)
    values = {a.value for a in legal_actions(obs, DimmerMode.STEP) if a.kind is Kind.SET_DIMMER}
    assert values == {0.25, 0.75}


def test_safety_gate_refuses_impossible_actions():
    obs = _obs(servers=3, active_servers=3, max_servers=3)
    with pytest.raises(UnsafeAction):
        validate(ADD_SERVER, obs)
    with pytest.raises(UnsafeAction):
        validate(Action(Kind.SET_DIMMER, 1.5), obs)


# --------------------------------------------------------------------------
# context builder
# --------------------------------------------------------------------------
def _trajectory(obs: Observation, period: int = 0) -> Trajectory:
    traj = Trajectory(window=5)
    traj.record_observation(period, obs)
    return traj


def test_static_prefix_is_identical_across_states():
    """Segment A must not vary, or P0 differences stop meaning 'state'.

    The pool ceiling is part of segment A but is a configuration constant, not
    a time-varying quantity: SWIM reports the same max_servers every period of
    a run. So the invariant that matters is across *states of one run*, which
    is what this asserts.
    """
    builder = ContextBuilder()
    a = builder.options_for(_obs(dimmer=0.1))
    b = builder.options_for(_obs(dimmer=0.9, servers=3, active_servers=3))
    assert builder.static_prefix(a, 3) == builder.static_prefix(b, 3)


def test_step_mode_keeps_the_prefix_static_too():
    builder = ContextBuilder(dimmer_mode=DimmerMode.STEP)
    a = builder.options_for(_obs(dimmer=0.25))
    b = builder.options_for(_obs(dimmer=0.75))
    assert builder.static_prefix(a, 3) == builder.static_prefix(b, 3)


def test_the_prompt_states_the_real_pool_ceiling():
    """A hardcoded "1..3" would have told the model the pool was capped at
    three while the state block said twelve -- and the intervention results say
    it follows the reasoning over the telemetry, so it would likely have
    believed the constraint rather than the observation."""
    builder = ContextBuilder()
    opts = builder.options_for(_obs())
    assert "servers   1..3;" in builder.static_prefix(opts, 3)
    assert "servers   1..12;" in builder.static_prefix(opts, 12)
    assert builder.static_prefix(opts, 3) != builder.static_prefix(opts, 12)


def test_both_prompt_paths_report_the_same_ceiling():
    """The chat and completion paths build segment A separately; a fix applied
    to one and not the other would be invisible until a run used the other."""
    builder = ContextBuilder()
    traj = _trajectory(_obs(max_servers=12))
    chat, _ = builder.build_messages(0, traj)
    flat = builder.build(0, traj)
    assert "servers   1..12;" in chat[0]["content"]
    assert "servers   1..12;" in flat.text


def test_probe_offsets_land_where_they_claim():
    builder = ContextBuilder(reasoning=ReasoningStyle.SCAFFOLD)
    traj = _trajectory(_obs())
    prompt = builder.build(0, traj, reasoning_text=(
        " breached.\n  Capacity: tight.\n  Trend: rising.\n  Therefore: add one."
    ))
    assert prompt.text[prompt.probes[P_ACTION] - len("Action:"):prompt.probes[P_ACTION]] == "Action:"
    assert prompt.text.endswith("Action:")
    # P0 sits at the end of the live state block: everything after the last
    # "---" separator and before any reasoning the model generates.
    head = prompt.text[:prompt.probes[P0]]
    live_state = head[head.rindex("---"):]
    assert "Reasoning:" not in live_state
    assert "arrival rate" in live_state
    assert head.endswith("req/s") or "arrival rate" in live_state


def test_scaffold_fields_get_their_own_probes():
    builder = ContextBuilder(reasoning=ReasoningStyle.SCAFFOLD)
    prompt = builder.build(0, _trajectory(_obs()), reasoning_text=(
        " breached.\n  Capacity: tight.\n  Trend: rising.\n  Therefore: add one."
    ))
    for name in ("P_sla", "P_capacity", "P_trend", "P_therefore"):
        assert name in prompt.probes
    assert prompt.probes["P_sla"] < prompt.probes["P_therefore"] < prompt.probes[P_ACTION]


def test_a_field_the_model_skipped_gets_no_probe():
    builder = ContextBuilder(reasoning=ReasoningStyle.SCAFFOLD)
    prompt = builder.build(0, _trajectory(_obs()), reasoning_text=" breached, that is all.")
    assert "P_sla" in prompt.probes
    assert "P_capacity" not in prompt.probes


def test_reasoning_none_goes_straight_to_the_action():
    builder = ContextBuilder(reasoning=ReasoningStyle.NONE)
    prompt = builder.build(0, _trajectory(_obs()))
    assert "Reasoning:" not in prompt.text.split("Worked examples:")[-1].split("---")[-1]
    assert prompt.text.endswith("Action:")


def test_state_block_reports_the_breach_and_the_history():
    obs = _obs(basic_rt=1.0, opt_rt=1.0)
    traj = Trajectory(window=5)
    for period in range(3):
        traj.record_observation(period, obs)
    block = ContextBuilder().state_block(2, traj)
    assert "BREACHED" in block
    assert "last 3 periods" in block


def test_effects_are_attributed_a_period_later():
    traj = Trajectory(window=5)
    traj.record_observation(0, _obs(basic_rt=1.0, opt_rt=1.0))
    traj.record_decision(0, ADD_SERVER, _obs(basic_rt=1.0, opt_rt=1.0))
    # still open: the effect genuinely is not known yet
    assert traj.recent_decisions()[-1].rt_delta is None
    traj.record_observation(1, _obs(basic_rt=0.5, opt_rt=0.5))
    closed = traj.recent_decisions()[-1]
    assert closed.rt_delta == pytest.approx(-0.5)


# --------------------------------------------------------------------------
# the LLM policy, end to end, with no model
# --------------------------------------------------------------------------
@pytest.mark.parametrize("chat", [False, True])
def test_llm_policy_produces_a_legal_action_and_two_distributions(chat):
    obs = _obs(basic_rt=1.0, opt_rt=1.0)
    policy = LLMPolicy(backend=StubBackend(seed=1), builder=ContextBuilder(), chat=chat)
    result = policy(0, obs, _trajectory(obs))

    assert is_legal(result.action, obs)
    if chat:
        # The scored position is the end of the final assistant turn, so that
        # turn must carry the action cue -- otherwise the next token is whatever
        # opens a reply rather than the action letter.
        assert result.messages and result.messages[-1]["role"] == "assistant"
        assert result.messages[-1]["content"].endswith("Action:")
        assert result.prompt is None
    else:
        assert result.prompt and result.prompt.endswith("Action:")
    assert set(result.distribution) <= set(result.raw_distribution)
    assert sum(result.distribution.values()) == pytest.approx(1.0)
    # every option surviving the mask must itself be legal
    by_id = dict(ContextBuilder().options_for(obs))
    for oid in result.distribution:
        assert is_legal(by_id[oid], obs)


@pytest.mark.parametrize("model_output,label", [
    ("Reasoning:\n  SLA: breached.\n  Therefore: add one.", "model emits the header"),
    ("  SLA: breached.\n  Therefore: add one.",             "model omits the header"),
])
def test_chat_turn_carries_exactly_one_scaffold(model_output, label):
    """The header must appear once, whatever the model returned.

    On the completion path the prompt stops mid-line at "  SLA:" and the model
    continues it. In chat form the model writes the whole turn and emits the
    header itself, so prepending the scaffold as well left an empty "  SLA:"
    line ahead of the real one -- still scoreable, but every field probe would
    anchor on the blank line and every captured activation would be about the
    wrong position.
    """
    b = ContextBuilder()
    msgs, _ = b.build_messages(0, _trajectory(_obs()), reasoning=model_output)
    content = msgs[-1]["content"]
    assert content.count("Reasoning:") == 1, label
    assert content.count("SLA:") == 1, label
    assert content.endswith("Action:")
    assert "SLA:Reasoning:" not in content


def test_ablated_chat_turn_is_just_the_action_cue():
    b = ContextBuilder()
    msgs, _ = b.build_messages(0, _trajectory(_obs()), reasoning="")
    assert msgs[-1]["content"] == "Action:"


def test_chat_and_completion_agree_on_the_action_space():
    """Both formats must offer the same options, or results are incomparable."""
    obs = _obs()
    b = ContextBuilder()
    flat = b.build(0, _trajectory(obs)).options
    msgs_opts = b.build_messages(0, _trajectory(obs))[1]
    assert [o for o, _ in flat] == [o for o, _ in msgs_opts]
    assert [str(a) for _, a in flat] == [str(a) for _, a in msgs_opts]


def test_illegal_options_are_masked_out():
    """At max servers, add_server keeps raw mass but cannot be chosen."""
    obs = _obs(servers=3, active_servers=3, max_servers=3, basic_rt=1.0, opt_rt=1.0,
               utilizations=(0.9, 0.9, 0.9))
    builder = ContextBuilder()
    policy = LLMPolicy(backend=StubBackend(seed=3), builder=builder)
    result = policy(0, obs, _trajectory(obs))

    add_id = next(oid for oid, a in builder.options_for(obs) if a == ADD_SERVER)
    assert add_id in result.raw_distribution
    assert add_id not in result.distribution
    assert result.action != ADD_SERVER


def test_scoring_backend_failure_falls_back_rather_than_crashing():
    class Broken(StubBackend):
        def score(self, prompt, options):
            raise RuntimeError("endpoint down")

    obs = _obs(basic_rt=1.0, opt_rt=1.0)
    policy = LLMPolicy(backend=Broken(), builder=ContextBuilder())
    result = policy(0, obs, _trajectory(obs))
    assert result.policy.endswith("fallback")
    assert result.action == ADD_SERVER          # the reactive answer


def test_reactive_step_follows_the_level_count():
    """SWIM's rule steps by 1/(levels-1). At the published configuration's 10
    levels that is 1/9, not the reduced configuration's 0.25 -- which the port
    used regardless until it was told the level count."""
    obs = _obs(basic_rt=0.1, opt_rt=0.1, dimmer=0.5, servers=3, active_servers=3,
               max_servers=12, utilizations=(0.1, 0.1, 0.1))
    assert ReactivePolicy().decide(obs) == Action(Kind.SET_DIMMER, 0.75)
    assert ReactivePolicy(dimmer_levels=10).decide(obs) == \
        Action(Kind.SET_DIMMER, round(0.5 + 1 / 9, 6))


def test_dimmer_actions_reach_full_content():
    """SWIM's reported utility pays the server-cost term only at dimmer 1, so a
    controller whose actions stop short of 1 can never earn it."""
    from controller.actions import DIMMER_REPRESENTATIVES
    assert max(DIMMER_REPRESENTATIVES) == 1.0
    labels = [label for _, label in ContextBuilder().options_for(_obs())]
    assert "set_dimmer 1" in labels


def test_objective_states_the_priority_order_and_can_be_removed():
    traj = _trajectory(_obs())
    on = ContextBuilder().build_messages(0, traj)[0][0]["content"]
    off = ContextBuilder(objective=False).build_messages(0, traj)[0][0]["content"]
    assert "strict priority order" in on
    assert on.index("keep the SLA") < on.index("optional content") < on.index("as few servers")
    assert "Objective" not in off
    flat = ContextBuilder().build(0, traj).text
    assert "strict priority order" in flat
