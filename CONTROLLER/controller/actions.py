"""The action space, its legality rules, and the safety clamp.

SWIM offers three tactics -- add a server, remove a server, set the dimmer --
plus the option of doing nothing. That makes the decision a categorical choice
over at most eight options, which is what lets the controller *score* actions
rather than generate and parse them (see ``backends.py``).

Two dimmer modes are provided, and the choice is an experimental control rather
than a detail:

``LEVELS``
    Five absolute settings, one per distinguishable utility level. SWIM's
    scorer quantises brownout into ``numberOfBrownoutLevels`` bands via
    ``Model::brownoutFactorToLevel``, so dimmer values inside one band are
    indistinguishable in the utility it reports; offering one representative per
    band spans everything the scorer can actually tell apart.

``STEP``
    Up or down one ``1/(levels-1)`` step from the current value, clamped to
    [0, 1] -- exactly what ``ReactiveAdaptationManager`` can do. Use this when
    comparing against the reactive baseline, so that a difference in outcome is
    attributable to the decision rule and not to a larger action space.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .swim import Observation


# Five dimmer targets spanning the full range, 0 to 1.
#
# The top value has to be 1.0. SWIM reports utility with the SEAMS 2017 function
# (plotResults.R, periodUtilitySEAMS2017A), which credits the server-cost term
# 10 * (maxServers - avgServers) only when revenue is at its optimum -- that is,
# when the dimmer is 1 and every response carries optional content. The previous
# targets stopped at 0.9, chosen to sit on the grid of the simulator's own
# ICAC 2016 scorer, and so left the controller structurally unable to earn that
# term while SWIM's reactive manager, which steps to 1.0, could.
#
# They are not quantised to numberOfBrownoutLevels and do not need to be:
# AdaptInterface::cmdSetDimmer takes a continuous value and calls
# setBrownout(1 - dimmer) without rounding, and the reported utility reads the
# dimmer from the recorded brownoutFactor vector, which holds that value.
#
# Quarters, which is also SWIM's reactive step at 5 levels.
DIMMER_LEVELS = 5
DIMMER_STEP = 1.0 / (DIMMER_LEVELS - 1)          # 0.25, for STEP mode
DIMMER_REPRESENTATIVES = (0.0, 0.25, 0.5, 0.75, 1.0)


class Kind(str, Enum):
    ADD_SERVER = "add_server"
    REMOVE_SERVER = "remove_server"
    SET_DIMMER = "set_dimmer"
    NO_OP = "no_op"


class DimmerMode(str, Enum):
    LEVELS = "levels"
    STEP = "step"


@dataclass(frozen=True)
class Action:
    kind: Kind
    value: float | None = None       # dimmer target, for SET_DIMMER only

    def __str__(self) -> str:
        if self.kind is Kind.SET_DIMMER:
            return f"set_dimmer {self.value:g}"
        return self.kind.value

    @property
    def label(self) -> str:
        """Human-readable form used in the prompt legend and in logs."""
        return str(self)


NO_OP = Action(Kind.NO_OP)
ADD_SERVER = Action(Kind.ADD_SERVER)
REMOVE_SERVER = Action(Kind.REMOVE_SERVER)


def action_space(obs: "Observation", mode: DimmerMode = DimmerMode.LEVELS) -> list[Action]:
    """Every action the controller may offer this period, legal or not.

    The space is built from the observation so that ``STEP`` mode can express
    "one step from here", but it is deliberately *not* filtered by legality --
    the model is shown a stable legend and its full distribution is recorded,
    including any mass it puts on illegal actions. Filtering happens in
    ``legal_actions``.
    """
    actions = [ADD_SERVER, REMOVE_SERVER, NO_OP]
    if mode is DimmerMode.LEVELS:
        actions += [Action(Kind.SET_DIMMER, v) for v in DIMMER_REPRESENTATIVES]
    else:
        down = max(0.0, round(obs.dimmer - DIMMER_STEP, 6))
        up = min(1.0, round(obs.dimmer + DIMMER_STEP, 6))
        actions += [Action(Kind.SET_DIMMER, down), Action(Kind.SET_DIMMER, up)]
    return actions


def is_legal(action: Action, obs: "Observation") -> bool:
    """Whether SWIM would accept this action in this state.

    Mirrors the guards in ``ReactiveAdaptationManager::evaluate``: no scaling
    while a server is booting, never below one server or above ``maxServers``.
    A dimmer action that would not change anything is treated as illegal so it
    cannot masquerade as an adaptation.
    """
    if action.kind is Kind.NO_OP:
        return True
    if action.kind is Kind.ADD_SERVER:
        return not obs.booting and obs.servers < obs.max_servers
    if action.kind is Kind.REMOVE_SERVER:
        return not obs.booting and obs.servers > 1
    if action.kind is Kind.SET_DIMMER:
        if action.value is None or not (0.0 <= action.value <= 1.0):
            return False
        return abs(action.value - obs.dimmer) > 1e-9
    return False


def legal_actions(obs: "Observation", mode: DimmerMode = DimmerMode.LEVELS) -> list[Action]:
    return [a for a in action_space(obs, mode) if is_legal(a, obs)]


class UnsafeAction(ValueError):
    """The chosen action would violate an invariant and was not sent to SWIM."""


def validate(action: Action, obs: "Observation") -> Action:
    """Last gate before the command goes out.

    POLARIS spent a Verification Agent and a NATS round trip on this guarantee.
    It is a handful of predicates, it runs in-process, and -- unlike an agent --
    it cannot itself fail to respond.
    """
    if action.kind is Kind.SET_DIMMER:
        if action.value is None:
            raise UnsafeAction("set_dimmer without a value")
        if not (0.0 <= action.value <= 1.0):
            raise UnsafeAction(f"dimmer {action.value} outside [0, 1]")
    if action.kind is Kind.ADD_SERVER and obs.servers >= obs.max_servers:
        raise UnsafeAction(f"add_server at max_servers={obs.max_servers}")
    if action.kind is Kind.REMOVE_SERVER and obs.servers <= 1:
        raise UnsafeAction("remove_server at the last server")
    if action.kind in (Kind.ADD_SERVER, Kind.REMOVE_SERVER) and obs.booting:
        raise UnsafeAction(f"{action.kind.value} while a server is booting")
    return action
