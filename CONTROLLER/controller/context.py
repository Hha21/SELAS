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


# Single-token identifiers. Scored one token at a time, so length bias cannot
# enter the comparison the way it would with whole-phrase continuations.
OPTION_IDS = "ABCDEFGH"

# The scaffold fields, in order. Each becomes a labelled probe position.
SCAFFOLD_FIELDS = ("SLA", "Capacity", "Trend", "Therefore")

P0 = "P0_state_end"
P_ACTION = "P_action"


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
    ) -> None:
        self.sla = sla
        self.boot_delay = boot_delay
        self.period_seconds = period_seconds
        self.dimmer_mode = dimmer_mode
        self.reasoning = reasoning
        self.window = window
        self.exemplars = exemplars if exemplars is not None else _DEFAULT_EXEMPLARS

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

    # -- segment A ---------------------------------------------------------
    def static_prefix(self, options: list[tuple[str, Action]]) -> str:
        legend = "\n".join(f"  {oid}  {label}" for oid, label in self.legend_entries(options))
        lines = [
            "You are the adaptation controller for a web application served by a pool",
            "of servers. Each period you observe the system and choose exactly one action.",
            "",
            "Constraints:",
            f"  servers   1..3; a new server takes {self.boot_delay} s to boot; one at a time;",
            "            no scaling while a server is booting",
            "  dimmer    0.0..1.0, the fraction of responses served with optional content.",
            "            Higher dimmer means richer responses and higher response time.",
            f"  SLA       average response time below {self.sla:g} s",
            f"  period    one decision every {self.period_seconds} s",
            "",
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

        history = traj.recent_observations(self.window)
        if len(history) > 1:
            lines.append(f"  last {len(history)} periods")
            lines.append(f"    response time {_fmt_series([o.avg_rt for _, o in history], places=2)}")
            lines.append(f"    arrival rate  {_fmt_series([o.arrival_rate for _, o in history], places=1)}")
            lines.append(f"    servers       {_fmt_series([float(o.active_servers) for _, o in history], places=0)}")
            lines.append(f"    dimmer        {_fmt_series([o.dimmer for _, o in history], places=2)}")

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
        prefix = self.static_prefix(options)
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

        text += "Action:"
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
