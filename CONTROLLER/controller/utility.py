"""The utility SWIM reports, estimated from one period's observation.

SWIM reports results with periodUtilitySEAMS2017A (tools/plotResults.R), from
Moreno et al., "Comparing model-based predictive approaches to self-adaptation:
CobRA and PLA" (SEAMS 2017). Per period, with a the arrival rate in req/s:

    response time over the threshold   1.5 * min(0, a - kappa)
    within it, dimmer at 1             1.5 * a + 10 * (maxServers - servers)
    within it, dimmer below 1          a * ((1 - d) * 1.0 + d * 1.5)

where kappa = maxServers * maxServiceRate is the most the pool could serve.

The official figure is computed after the run from recorded vectors -- per-
request response times, time-weighted dimmer and server counts -- which a
controller cannot see while it runs. This is the same function applied to what
it *can* see each period, so it is an estimate: good enough to show the
controller what its choices are costing, not a substitute for the reported
number, which is always computed by experiments/controller_comparison/
swim_utility.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .swim import Observation

# From swim.ini: *.maxServiceRate = 1 / 0.04452713, "used for the SEAMS'17
# CobRA-PLA utility function". SWIM does not report it over the socket.
MAX_SERVICE_RATE = 1 / 0.04452713
BASIC_REVENUE, OPT_REVENUE, SERVER_COST = 1.0, 1.5, 10.0


def kappa(max_servers: int) -> float:
    return max_servers * MAX_SERVICE_RATE


def period_utility(obs: "Observation", sla: float = 0.75) -> float:
    a = obs.arrival_rate
    if obs.avg_rt > sla:
        return OPT_REVENUE * min(0.0, a - kappa(obs.max_servers))
    d = obs.dimmer
    revenue = a * ((1 - d) * BASIC_REVENUE + d * OPT_REVENUE)
    if d >= 1.0 - 1e-5:
        return revenue + SERVER_COST * (obs.max_servers - obs.servers)
    return revenue
