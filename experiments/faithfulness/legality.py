"""Which options were legal when a recorded decision was taken.

Every replay masks the re-scored distribution to the options SWIM would have
accepted, as the controller did live. That set used to be read off the keys of
the recorded distribution -- but the recorded distribution holds only options
that appeared in the endpoint's top-20 logprobs, so a legal option the model
gave almost no mass was treated as illegal, and an intervention that moved mass
onto it had that mass silently discarded (5-8 of 105 decisions per prompt-A
run).

The set is recomputed here from the recorded observation with the controller's
own rule, so it cannot drift from what the controller enforced.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "CONTROLLER"))
from controller.actions import DimmerMode, Kind, action_space, is_legal  # noqa: E402
from controller.swim import Observation  # noqa: E402

_OBS_FIELDS = ("servers", "active_servers", "max_servers", "dimmer", "basic_rt",
               "opt_rt", "basic_throughput", "opt_throughput", "arrival_rate")


def observation(record: dict) -> Observation:
    o = record["observation"]
    return Observation(**{k: o[k] for k in _OBS_FIELDS},
                       utilizations=tuple(o["utilizations"]))


def legal_ids(record: dict) -> list[str]:
    """Option ids legal in the recorded state, in legend order.

    The logged options are the legend text, so the actions are rebuilt the way
    the controller built them -- ``action_space`` over the same observation --
    and checked against that text before anything is trusted.
    """
    options = record["decision"]["options"]
    obs = observation(record)
    step = any("one step" in label for _, label in options)
    actions = action_space(obs, DimmerMode.STEP if step else DimmerMode.LEVELS)
    if len(actions) != len(options):
        raise ValueError(f"period {record.get('period')}: {len(options)} options "
                         f"logged, {len(actions)} rebuilt")
    for (oid, label), action in zip(options, actions):
        if label.split()[0] != action.kind.value or (
                not step and action.kind is Kind.SET_DIMMER
                and abs(float(label.split()[1]) - action.value) > 1e-9):
            raise ValueError(f"period {record.get('period')}: option {oid} is "
                             f"{label!r} in the log but {action} when rebuilt")
    return [oid for (oid, _), action in zip(options, actions) if is_legal(action, obs)]
