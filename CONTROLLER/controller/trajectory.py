"""Rolling history of what the system did and what happened next.

The controller is memoryless as far as SWIM is concerned -- every period it
reads the current state and nothing else. The trajectory is what turns that into
the "current state *and* how we got here" that the context builder needs, and it
is also where an action's observed effect is attributed, so the model can be
shown whether its last decision helped.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

from .actions import Action
from .swim import Observation


@dataclass(frozen=True)
class Decision:
    """An action taken in a period, and what the next period looked like.

    ``rt_delta`` is filled in one period later, once the following observation
    exists. It stays ``None`` for the most recent decision, which is honest --
    the effect genuinely is not known yet, and showing a fabricated zero there
    would teach the model that its last action did nothing.
    """

    period: int
    action: Action
    rt_before: float
    rt_after: float | None = None

    @property
    def rt_delta(self) -> float | None:
        if self.rt_after is None:
            return None
        return self.rt_after - self.rt_before


class Trajectory:
    """Bounded history of observations and decisions.

    ``window`` bounds what the context builder can show. It is deliberately
    small: the prompt is rebuilt every period and a long tail of history would
    both dominate the token budget and make the static/dynamic split in the
    prompt less clean.
    """

    def __init__(self, window: int = 5, action_window: int = 3) -> None:
        self.window = window
        self.observations: deque[tuple[int, Observation]] = deque(maxlen=window)
        self.decisions: deque[Decision] = deque(maxlen=action_window)
        self._pending: Decision | None = None

    def record_observation(self, period: int, obs: Observation) -> None:
        # Close out the previous period's decision first: its effect is exactly
        # the change in response time between the state it was taken in and the
        # state that followed.
        if self._pending is not None:
            closed = Decision(
                period=self._pending.period,
                action=self._pending.action,
                rt_before=self._pending.rt_before,
                rt_after=obs.avg_rt,
            )
            self.decisions.append(closed)
            self._pending = None
        self.observations.append((period, obs))

    def record_decision(self, period: int, action: Action, obs: Observation) -> None:
        self._pending = Decision(period=period, action=action, rt_before=obs.avg_rt)

    # -- views -------------------------------------------------------------
    @property
    def latest(self) -> tuple[int, Observation] | None:
        return self.observations[-1] if self.observations else None

    def recent_observations(self, n: int | None = None) -> list[tuple[int, Observation]]:
        items = list(self.observations)
        return items if n is None else items[-n:]

    def recent_decisions(self, n: int | None = None) -> list[Decision]:
        """Closed decisions, oldest first, plus the still-open one if any."""
        items: list[Decision] = list(self.decisions)
        if self._pending is not None:
            items.append(self._pending)
        return items if n is None else items[-n:]

    def series(self, attr: str, n: int | None = None) -> list[float]:
        """A named observation attribute over the window, oldest first."""
        return [float(getattr(o, attr)) for _, o in self.recent_observations(n)]

    def __len__(self) -> int:
        return len(self.observations)

    def __iter__(self) -> Iterable[tuple[int, Observation]]:
        return iter(self.observations)
