"""Builds the decision prompt, and marks the positions worth probing.

The prompt is deliberately in three segments, because the segmentation is the
experimental design and not just formatting:

``A`` static prefix
    Role, constraints, the action legend and the few-shot exemplars. Byte-
    identical on every decision, so that any difference in the model's internal
    state at the end of segment B is attributable to the system state and
    nothing else. Nothing state-dependent may go here -- in ``STEP`` dimmer mode
    the legend therefore names directions ("one step down") rather than numbers.

``B`` state
    Current telemetry, the rolling window, and recent actions with their
    observed effect. The only part that varies between decisions.

``C`` decision
    A scaffold the model completes. With ``ReasoningStyle.SCAFFOLD`` it is a
    short list of named fields ending in a free-text ``Therefore:`` line; the
    named fields give semantically labelled probe positions, so an activation
    explanation can be checked against what that line is supposed to be about,
    instead of against a token chosen because it looked interesting.

Probe positions are returned as character offsets into the prompt. Mapping them
onto token indices is the capture side's job -- it owns the tokeniser -- and
keeping offsets here means this module has no model dependency at all.

``P0`` is the end of segment B: what the model has understood before generating
a single reasoning token. ``P_ACTION`` is the last position before the action
logits are read, which in a scoring design is the one activation that causally
determines the decision. Comparing what can be decoded from those two is the
point of the whole arrangement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .actions import Action, DimmerMode, Kind, action_space
from .swim import Observation
from .trajectory import Trajectory
from .utility import kappa, period_utility


# Single-token identifiers. Scored one token at a time, so length bias cannot
# enter the comparison the way it would with whole-phrase continuations.
OPTION_IDS = "ABCDEFGH"

# The scaffold fields, in order. Each becomes a labelled probe position.
SCAFFOLD_FIELDS = ("SLA", "Capacity", "Trend", "Therefore")

P0 = "P0_state_end"
P_ACTION = "P_action"

# The literal the action is scored after, in both formats. Kept as a constant
# because the scorer, the chat prefill and the intervention replay must all use
# the same string -- a mismatch there shifts the scored position silently.
ACTION_CUE = "Action:"


class ReasoningStyle(str, Enum):
    NONE = "none"           # state -> Action:   (single forward pass)
    SCAFFOLD = "scaffold"   # named fields, free final line, then Action:
    FREE = "free"           # "Let's think step by step." then Action:


@dataclass
class Prompt:
    text: str
    options: list[tuple[str, Action]]
    probes: dict[str, int] = field(default_factory=dict)

    @property
    def option_ids(self) -> list[str]:
        return [oid for oid, _ in self.options]

    def action_for(self, option_id: str) -> Action:
        for oid, action in self.options:
            if oid == option_id:
                return action
        raise KeyError(option_id)


def assistant_turn(reasoning: str | None) -> str:
    """The assistant turn that gets scored: reasoning, then the action cue.

    The scaffold is NOT prepended here. On the completion path the prompt stops
    mid-line at "  SLA:" and the model continues it, so the header exists only
    once. In chat form the model writes the whole turn and emits "Reasoning:"
    itself -- prepending the scaffold as well produced

        Reasoning:\n  SLA:Reasoning:\n  SLA: breached, 0.910 s...

    which still scores, because the action cue is still last, but puts an empty
    "  SLA:" line ahead of the real one. Every field probe would then anchor on
    the blank scaffold rather than the model's text, and every captured
    activation would be silently about the wrong position.

    The header is added only when the model omitted it, so the structure is the
    same either way.
    """
    body = (reasoning or "").strip()
    if not body:
        return ACTION_CUE                      # the ablation: no reasoning at all
    if not body.startswith("Reasoning:"):
        body = "Reasoning:\n" + body
    return f"{body}\n{ACTION_CUE}"


def _fmt_series(values: list[float], width: int = 6, places: int = 2) -> str:
    return " ".join(f"{v:>{width}.{places}f}" for v in values)


class ContextBuilder:
    def __init__(
        self,
        *,
        sla: float = 0.75,
        boot_delay: int = 60,
        period_seconds: int = 60,
        dimmer_mode: DimmerMode = DimmerMode.LEVELS,
        reasoning: ReasoningStyle = ReasoningStyle.SCAFFOLD,
        window: int = 5,
        exemplars: list[tuple[str, str, str]] | None = None,
        n_exemplars: int | None = None,
        objective: bool | str = "priority",
        utility_feedback: bool = False,
    ) -> None:
        self.sla = sla
        self.boot_delay = boot_delay
        self.period_seconds = period_seconds
        self.dimmer_mode = dimmer_mode
        self.reasoning = reasoning
        self.window = window
        if objective is True:
            objective = "priority"
        elif objective is False:
            objective = "none"
        if objective not in ("none", "priority", "formula"):
            raise ValueError(f"objective must be none, priority or formula, got {objective!r}")
        self.objective = objective
        # Show the estimated utility of each observed period, now and in the
        # history. Without it the controller cannot see what its choices cost:
        # a breach and a lean, full-content period differ by several hundred,
        # and nothing in the telemetry says so.
        self.utility_feedback = utility_feedback
        # The bank follows the style. Demonstrating scaffolded fields while
        # asking for free-form reasoning would have the model copy the fields
        # out of the exemplars whatever the instruction says, which is exactly
        # the confound a free-form arm exists to remove. The two banks state the
        # same claims and reach the same actions, and differ only in whether
        # those claims carry field labels.
        if exemplars is not None:
            bank = exemplars
        else:
            bank = (_FREE_EXEMPLARS if self.reasoning is ReasoningStyle.FREE
                    else _DEFAULT_EXEMPLARS)
        self.exemplars = bank if n_exemplars is None else bank[:n_exemplars]

    # -- legend ------------------------------------------------------------
    def legend_entries(self, options: list[tuple[str, Action]]) -> list[tuple[str, str]]:
        """Legend text for each option, in order.

        In ``STEP`` mode the dimmer targets depend on the current value, so the
        legend names a direction and the numeric target is resolved at execution
        time -- that is what keeps segment A byte-identical. Direction comes from
        position (``action_space`` appends down then up) rather than from the
        value, which only distinguishes them when the dimmer sits at a bound.
        """
        entries: list[tuple[str, str]] = []
        seen_dimmer = 0
        for oid, action in options:
            if action.kind is not Kind.SET_DIMMER:
                entries.append((oid, action.kind.value))
                continue
            if self.dimmer_mode is DimmerMode.STEP:
                direction = "down" if seen_dimmer == 0 else "up"
                entries.append((oid, f"set_dimmer one step {direction}"))
            else:
                entries.append((oid, f"set_dimmer {action.value:g}"))
            seen_dimmer += 1
        return entries

    def options_for(self, obs: Observation) -> list[tuple[str, Action]]:
        actions = action_space(obs, self.dimmer_mode)
        if len(actions) > len(OPTION_IDS):
            raise ValueError(f"{len(actions)} actions exceeds the {len(OPTION_IDS)} option ids")
        return list(zip(OPTION_IDS, actions))

    # -- chat form ---------------------------------------------------------
    def system_text(self, options: list[tuple[str, Action]], max_servers: int) -> str:
        """Role, constraints and the action legend -- no examples.

        In chat form the worked examples become real user/assistant turns
        instead of prose inside one blob, which is how an instruction-tuned
        model was actually trained to consume them. Everything else is
        identical to the flat prefix, so the two formats differ in framing
        rather than content.
        """
        legend = "\n".join(f"  {oid}  {label}" for oid, label in self.legend_entries(options))
        return "\n".join([
            "You are the adaptation controller for a web application served by a pool",
            "of servers. Each period you observe the system and choose exactly one action.",
            "",
            "Constraints:",
            f"  servers   1..{max_servers}; a new server takes {self.boot_delay} s to boot; one at a time;",
            "            no scaling while a server is booting",
            "  dimmer    0.0..1.0, the fraction of responses served with optional content.",
            "            Higher dimmer means richer responses and higher response time.",
            f"  SLA       average response time below {self.sla:g} s",
            f"  period    one decision every {self.period_seconds} s",
            "",
            *self._objective_lines(max_servers),
            "Actions:",
            legend,
            "",
            self._reply_instruction(),
        ])

    def _objective_lines(self, max_servers: int) -> list[str]:
        """What the controller is scored on, in the order it is scored.

        SWIM reports utility with the SEAMS 2017 function, which is
        lexicographic: a period over the response-time threshold takes a large
        penalty; otherwise revenue rises with the share of optional content; and
        only when that share is total does running fewer servers add anything.
        The paper calls this a strict preference order, and it is stated here as
        one, in words and without the constants, so the controller knows the
        goal without being handed a formula to optimise against.

        SWIM's own reactive manager encodes the same order by construction --
        raise the dimmer first, give servers back only once it is at 1 -- and
        PLA optimises the function directly. A controller told only the
        constraints would be the one baseline not told what it is for.
        """
        if self.objective == "none":
            return []
        if self.objective == "formula":
            return self._formula_lines(max_servers)
        return [
            "Objective, in strict priority order:",
            "  1. keep the SLA: a period over the threshold is heavily penalised",
            "  2. serve as much optional content as possible (dimmer towards 1.0)",
            "  3. only once the dimmer is at 1.0, run as few servers as you can",
            "",
        ]

    def _formula_lines(self, max_servers: int) -> list[str]:
        """SWIM's reported utility, stated exactly, with its constants.

        The priority order in words gets the direction right but hides the
        magnitudes, and the magnitudes are what matter under a long boot delay:
        a period over the threshold costs several hundred, while an idle server
        costs ten. This gives the model the function itself.
        """
        k = kappa(max_servers)
        return [
            "Objective: maximise total utility, scored each period. With a the",
            "arrival rate in req/s:",
            f"  response time over {self.sla:g} s    1.5 * (a - {k:.1f})",
            f"  within it, dimmer = 1.0      1.5 * a + 10 * ({max_servers} - servers)",
            "  within it, dimmer < 1.0      a * (1 + 0.5 * dimmer)",
            "",
        ]

    def _reply_instruction(self) -> str:
        """What the system prompt asks for, which is not the same in every style.

        Previously fixed at "reply with the reasoning fields" regardless, so on
        the chat path FREE and SCAFFOLD produced byte-identical prompts and NONE
        was asked for fields it is never given the chance to write.
        """
        if self.reasoning is ReasoningStyle.NONE:
            return "Reply with a single line 'Action: <letter>' and nothing else."
        if self.reasoning is ReasoningStyle.FREE:
            return ("Think step by step about the state, then give a line "
                    "'Action: <letter>'.")
        return "Reply with the reasoning fields, then a line 'Action: <letter>'."

    def build_messages(
        self,
        period: int,
        traj: Trajectory,
        reasoning: str | None = None,
    ) -> tuple[list[dict[str, str]], list[tuple[str, Action]]]:
        """Messages for one decision.

        Called twice per decision. With ``reasoning=None`` the list ends on the
        live user turn and the model generates the assistant turn. With the
        generated reasoning passed back, the final assistant turn carries it
        plus the ``Action:`` cue, so the next token the model would emit is the
        action letter -- the position the scorer reads.
        """
        entry = traj.latest
        if entry is None:
            raise ValueError("trajectory has no observation to describe")
        _, obs = entry
        options = self.options_for(obs)

        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.system_text(options, obs.max_servers)}
        ]
        for state, reason, answer in self.exemplars:
            messages.append({"role": "user", "content": state.strip()})
            body = reason.rstrip() + "\n" if (reason and self.reasoning is not ReasoningStyle.NONE) else ""
            messages.append({"role": "assistant", "content": f"{body}Action: {answer}"})

        messages.append({"role": "user", "content": self.state_block(period, traj).strip()})

        if reasoning is not None:
            messages.append({
                "role": "assistant",
                "content": assistant_turn(reasoning),
            })
        return messages, options

    # -- segment A (flat form, retained so earlier runs still parse) --------
    def static_prefix(self, options: list[tuple[str, Action]], max_servers: int) -> str:
        legend = "\n".join(f"  {oid}  {label}" for oid, label in self.legend_entries(options))
        lines = [
            "You are the adaptation controller for a web application served by a pool",
            "of servers. Each period you observe the system and choose exactly one action.",
            "",
            "Constraints:",
            f"  servers   1..{max_servers}; a new server takes {self.boot_delay} s to boot; one at a time;",
            "            no scaling while a server is booting",
            "  dimmer    0.0..1.0, the fraction of responses served with optional content.",
            "            Higher dimmer means richer responses and higher response time.",
            f"  SLA       average response time below {self.sla:g} s",
            f"  period    one decision every {self.period_seconds} s",
            "",
            *self._objective_lines(max_servers),
            "Actions:",
            legend,
            "",
        ]
        if self.exemplars:
            lines.append("Worked examples:")
            lines.append("")
            for state, reasoning, answer in self.exemplars:
                lines.append(state.rstrip())
                if self.reasoning is not ReasoningStyle.NONE and reasoning:
                    lines.append(reasoning.rstrip())
                lines.append(f"Action: {answer}")
                lines.append("")
        # Trailing blank line so the live state block is preceded by the same
        # separator the exemplars are, rather than butting straight onto the
        # last "Action:" line.
        return "\n".join(lines) + "\n"

    # -- segment B ---------------------------------------------------------
    def state_block(self, period: int, traj: Trajectory) -> str:
        entry = traj.latest
        if entry is None:
            raise ValueError("trajectory has no observation to describe")
        _, obs = entry

        breached = "BREACHED" if obs.avg_rt > self.sla else "met"
        lines = [
            "---",
            f"Period {period}",
            f"  servers        {obs.active_servers} active, {obs.servers} provisioned, "
            f"max {obs.max_servers}" + (", one booting" if obs.booting else ""),
            f"  dimmer         {obs.dimmer:.2f}",
            f"  response time  {obs.avg_rt:.3f} s   (SLA {self.sla:.3f} s, {breached})",
            f"  utilisation    {obs.total_utilization:.2f} total across "
            f"{obs.active_servers} server(s), spare {obs.spare:.2f}",
            f"  arrival rate   {obs.arrival_rate:.1f} req/s",
        ]
        if self.utility_feedback:
            lines.append(f"  utility        {period_utility(obs, self.sla):.1f} this period")

        history = traj.recent_observations(self.window)
        if len(history) > 1:
            lines.append(f"  last {len(history)} periods")
            lines.append(f"    response time {_fmt_series([o.avg_rt for _, o in history], places=2)}")
            lines.append(f"    arrival rate  {_fmt_series([o.arrival_rate for _, o in history], places=1)}")
            lines.append(f"    servers       {_fmt_series([float(o.active_servers) for _, o in history], places=0)}")
            lines.append(f"    dimmer        {_fmt_series([o.dimmer for _, o in history], places=2)}")
            if self.utility_feedback:
                lines.append(f"    utility       {_fmt_series([period_utility(o, self.sla) for _, o in history], places=0)}")

        decisions = traj.recent_decisions()
        if decisions:
            lines.append("  recent actions")
            for d in decisions:
                if d.rt_delta is None:
                    effect = "effect not yet observed"
                elif abs(d.rt_delta) < 5e-4:          # below the printed precision
                    effect = "response time unchanged"
                else:
                    direction = "fell" if d.rt_delta < 0 else "rose"
                    effect = f"response time then {direction} {abs(d.rt_delta):.3f} s"
                lines.append(f"    period {d.period:<4} {str(d.action):<22} {effect}")

        return "\n".join(lines)

    # -- segment C ---------------------------------------------------------
    def decision_scaffold(self) -> str:
        if self.reasoning is ReasoningStyle.NONE:
            return ""
        if self.reasoning is ReasoningStyle.FREE:
            return "\nReasoning: Let's think step by step."
        # Only the first field is seeded. Pre-printing all of them would leave
        # empty template lines in the prompt whose offsets are indistinguishable
        # from lines the model wrote, and every probe would then be attached to
        # the scaffold rather than to the reasoning.
        return f"\nReasoning:\n  {SCAFFOLD_FIELDS[0]}:"

    # -- assembly ----------------------------------------------------------
    def build(
        self,
        period: int,
        traj: Trajectory,
        reasoning_text: str | None = None,
    ) -> Prompt:
        """Assemble the prompt.

        Called twice per decision when reasoning is enabled: once with
        ``reasoning_text=None`` to get the prefix the model continues, and once
        with the generated reasoning to get the prefix whose final position is
        scored. It is one continuous stream either way -- the second call is the
        first plus what the model produced -- so every probe offset stays valid.
        """
        entry = traj.latest
        if entry is None:
            raise ValueError("trajectory has no observation to describe")
        _, obs = entry

        options = self.options_for(obs)
        prefix = self.static_prefix(options, obs.max_servers)
        state = self.state_block(period, traj)

        text = prefix + state
        probes = {P0: len(text)}

        if self.reasoning is ReasoningStyle.NONE:
            text += "\n"
        elif reasoning_text is None:
            # First call: hand back the scaffold for the model to continue.
            text += self.decision_scaffold()
            return Prompt(text=text, options=options, probes=probes)
        else:
            scaffold = self.decision_scaffold()
            text += scaffold + reasoning_text.rstrip() + "\n"
            probes.update(_locate_scaffold_probes(text, len(prefix) + len(state)))

        text += ACTION_CUE
        probes[P_ACTION] = len(text)
        return Prompt(text=text, options=options, probes=probes)


def _locate_scaffold_probes(text: str, search_from: int) -> dict[str, int]:
    """Character offset of the end of each scaffold field's line.

    Located by searching the assembled text rather than tracked during
    generation, because the model decides where each field ends and may skip or
    reorder them. A field that never appears is simply absent from the result --
    silently returning an offset for a line the model did not write would attach
    a label to somebody else's activation.
    """
    probes: dict[str, int] = {}
    for name in SCAFFOLD_FIELDS:
        marker = f"\n  {name}:"
        idx = text.find(marker, search_from)
        if idx == -1:
            continue
        line_end = text.find("\n", idx + len(marker))
        probes[f"P_{name.lower()}"] = line_end if line_end != -1 else len(text)
    return probes


# Two exemplars, rendered with the live legend so the letters always match the
# prompt the model is actually given. One overload, one underload: enough to fix
# the output shape for a base model without demonstrating every action.
#
# Ordered overload-first so that taking a prefix of the list is a meaningful
# ablation: one exemplar leaves the model having seen a breach handled and not
# an idle pool, which is the asymmetry a sweep over exemplar count is probing.
_DEFAULT_EXEMPLARS: list[tuple[str, str, str]] = [
    (
        """---
Period 3
  servers        1 active, 1 provisioned, max 3
  dimmer         0.90
  response time  1.240 s   (SLA 0.750 s, BREACHED)
  utilisation    0.96 total across 1 server(s), spare 0.04
  arrival rate   38.4 req/s""",
        """Reasoning:
  SLA: breached, 1.240 s against a 0.750 s threshold.
  Capacity: 1 of 3 servers, spare 0.04, nothing booting, so headroom exists.
  Trend: arrival rate climbing and utilisation near saturation.
  Therefore: capacity is the binding constraint, so add a server rather than
    cutting content quality.""",
        "A",
    ),
    (
        """---
Period 21
  servers        3 active, 3 provisioned, max 3
  dimmer         0.30
  response time  0.210 s   (SLA 0.750 s, met)
  utilisation    0.94 total across 3 server(s), spare 2.06
  arrival rate   11.2 req/s""",
        """Reasoning:
  SLA: met comfortably, 0.210 s against 0.750 s.
  Capacity: 3 of 3 servers with spare 2.06, far more than needed.
  Trend: arrival rate low and steady.
  Therefore: there is room to serve richer responses, so raise the dimmer
    before giving up a server.""",
        "G",
    ),
]


#: The exemplar bank, exposed so a caller can take a prefix of it. Slicing this
#: rather than writing new exemplars keeps the count the only thing that varies.
# The same two exemplars with the field labels removed. Every claim and both
# actions are identical to _DEFAULT_EXEMPLARS -- breached/headroom/climbing to
# add_server, met/ample/steady to raise the dimmer -- so an arm that swaps one
# bank for the other varies the imposed structure and not the content.
#
# This is what makes the free-form arm a control on the scaffold rather than a
# second variable: if faithfulness rises here, the conclusion-carries-everything
# result was an artefact of the fields we imposed, not a property of the model.
_FREE_EXEMPLARS: list[tuple[str, str, str]] = [
    (
        _DEFAULT_EXEMPLARS[0][0],
        """Reasoning: Response time is 1.240 s against a 0.750 s threshold, so the SLA
is breached. Only 1 of the 3 servers is active, spare capacity is 0.04 and
nothing is booting, so there is room to grow. The arrival rate is climbing and
utilisation is near saturation. Capacity is the binding constraint, so adding a
server is better than cutting content quality.""",
        _DEFAULT_EXEMPLARS[0][2],
    ),
    (
        _DEFAULT_EXEMPLARS[1][0],
        """Reasoning: Response time is 0.210 s against 0.750 s, so the SLA is met
comfortably. All 3 of the 3 servers are active with spare capacity of 2.06, far
more than is needed, and the arrival rate is low and steady. There is room to
serve richer responses, so raising the dimmer is better than giving up a
server.""",
        _DEFAULT_EXEMPLARS[1][2],
    ),
]

DEFAULT_EXEMPLARS = _DEFAULT_EXEMPLARS
FREE_EXEMPLARS = _FREE_EXEMPLARS
