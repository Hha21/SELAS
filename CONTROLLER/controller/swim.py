"""TCP client for the SWIM exemplar's external control interface.

SWIM exposes a line-oriented TCP interface (default :4242): write
``<command>\n``, read one ``\n``-terminated line back. That is the entire API --
see ``SWIM/src/externalControl/AdaptInterface.cc``.

Three things about that interface are easy to get wrong, and are handled here so
nothing downstream has to think about them:

* ``set_dimmer v`` and ``get_dimmer`` both speak *dimmer*, not brownout. The
  simulator stores ``brownout = 1 - dimmer`` internally (AdaptInterface.cc:129,
  Model.cc:153). Higher dimmer = more optional content = richer responses and
  higher latency. The internal ``SetDimmerTactic`` uses the same units, so a
  value sent here means exactly what it means to SWIM's own controller.

* There is no ``get_response_time``. Response time is reported per service class
  and has to be recombined throughput-weighted, exactly as SWIM's own probe does
  (``SimProbe::getUpdatedObservations``).

* ``utilization`` in SWIM's adaptation logic is the *sum* over servers, not the
  mean -- ``obs.utilization += ...`` per server, commented "get total
  utilization" in HAProxyProbe.cc:62. That is what makes ``spare = activeServers
  - utilization`` read as "spare server-equivalents". Taking a mean here silently
  makes ``spare > 1`` almost always true and breaks the reactive baseline.
"""

from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Any


log = logging.getLogger("controller.swim")

# Commands whose replies we batch into one round trip. Order matters: replies
# come back in the order the commands were sent, because AdaptInterface splits
# the received buffer on newlines and answers each in turn.
_SENSE_SCALARS = (
    "get_servers",
    "get_active_servers",
    "get_max_servers",
    "get_dimmer",
    "get_basic_rt",
    "get_opt_rt",
    "get_basic_throughput",
    "get_opt_throughput",
    "get_arrival_rate",
)


class SwimError(RuntimeError):
    """SWIM replied with an ``error:`` line, or the reply could not be parsed."""


@dataclass(frozen=True)
class Observation:
    """One period's view of the managed system.

    ``servers`` is the total provisioned count and ``active_servers`` those
    actually serving; they differ exactly while a server is booting, which is
    what ``booting`` reports.
    """

    servers: int
    active_servers: int
    max_servers: int
    dimmer: float
    basic_rt: float
    opt_rt: float
    basic_throughput: float
    opt_throughput: float
    arrival_rate: float
    utilizations: tuple[float, ...]          # per server, index 0 == server1
    wall_time: float = field(default_factory=time.time)

    # -- derived -----------------------------------------------------------
    @property
    def avg_rt(self) -> float:
        """Throughput-weighted response time across both service classes.

        Zero throughput (no completed requests this window) has no defined
        response time; reporting 0.0 there would read as "perfectly fast" and
        trip an SLA-satisfied branch, so callers get 0.0 only when genuinely
        nothing was served and should treat it with ``has_traffic``.
        """
        total_tp = self.basic_throughput + self.opt_throughput
        if total_tp <= 0.0:
            return 0.0
        return (self.basic_rt * self.basic_throughput + self.opt_rt * self.opt_throughput) / total_tp

    @property
    def has_traffic(self) -> bool:
        return (self.basic_throughput + self.opt_throughput) > 0.0

    @property
    def total_utilization(self) -> float:
        """Sum over servers -- SWIM's own definition. See module docstring."""
        return sum(self.utilizations)

    @property
    def mean_utilization(self) -> float:
        """Per-server average. For display only; never for the spare guard."""
        if self.active_servers <= 0:
            return 0.0
        return self.total_utilization / self.active_servers

    @property
    def spare(self) -> float:
        """SWIM's ``spareUtilization``: active servers minus total utilization."""
        return self.active_servers - self.total_utilization

    @property
    def booting(self) -> bool:
        return self.servers > self.active_servers

    def as_dict(self) -> dict[str, Any]:
        return {
            "servers": self.servers,
            "active_servers": self.active_servers,
            "max_servers": self.max_servers,
            "dimmer": self.dimmer,
            "basic_rt": self.basic_rt,
            "opt_rt": self.opt_rt,
            "basic_throughput": self.basic_throughput,
            "opt_throughput": self.opt_throughput,
            "arrival_rate": self.arrival_rate,
            "utilizations": list(self.utilizations),
            "avg_rt": self.avg_rt,
            "total_utilization": self.total_utilization,
            "spare": self.spare,
            "booting": self.booting,
            "wall_time": self.wall_time,
        }


class SwimClient:
    """Persistent line-oriented connection to SWIM, with reconnect.

    A persistent socket rather than connect-per-command: the sense batch is one
    round trip instead of ten, which keeps the measured decision latency about
    the model rather than about TCP setup. The connection is re-established
    transparently if the simulator drops it.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 4242,
        timeout: float = 10.0,
        max_retries: int = 3,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.max_retries = max_retries
        self._sock: socket.socket | None = None
        self._rfile: Any = None

    # -- connection --------------------------------------------------------
    def connect(self) -> None:
        self.close()
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        self._sock = sock
        # Buffered reader so a reply split across TCP segments -- or several
        # replies coalesced into one -- still reads back as discrete lines.
        self._rfile = sock.makefile("r", encoding="utf-8", newline="\n")
        log.info("connected to SWIM at %s:%d", self.host, self.port)

    def close(self) -> None:
        for obj in (self._rfile, self._sock):
            try:
                if obj is not None:
                    obj.close()
            except OSError:
                pass
        self._rfile = None
        self._sock = None

    def __enter__(self) -> "SwimClient":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- raw protocol ------------------------------------------------------
    def _exchange(self, commands: list[str]) -> list[str]:
        """Write every command in one go, read back one reply line per command."""
        if self._sock is None:
            self.connect()
        assert self._sock is not None and self._rfile is not None

        payload = "".join(c + "\n" for c in commands).encode()
        self._sock.sendall(payload)

        replies: list[str] = []
        for cmd in commands:
            line = self._rfile.readline()
            if not line:
                raise ConnectionError(f"SWIM closed the connection during {cmd!r}")
            replies.append(line.strip())
        return replies

    def command(self, *commands: str) -> list[str]:
        """Send commands and return their replies, retrying on connection loss."""
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._exchange(list(commands))
            except (OSError, ConnectionError) as exc:
                last = exc
                log.warning(
                    "SWIM exchange failed (attempt %d/%d): %s",
                    attempt + 1, self.max_retries + 1, exc,
                )
                self.close()
                if attempt < self.max_retries:
                    time.sleep(min(2.0 ** attempt, 5.0))
        raise ConnectionError(f"SWIM unreachable at {self.host}:{self.port}") from last

    @staticmethod
    def _num(reply: str, command: str) -> float:
        if reply.startswith("error:"):
            raise SwimError(f"{command!r} -> {reply}")
        try:
            return float(reply)
        except ValueError as exc:
            raise SwimError(f"{command!r} -> unparseable reply {reply!r}") from exc

    # -- sensing -----------------------------------------------------------
    def sense(self) -> Observation:
        """One batched read of everything the controller needs."""
        scalar_replies = self.command(*_SENSE_SCALARS)
        vals = {
            cmd: self._num(reply, cmd)
            for cmd, reply in zip(_SENSE_SCALARS, scalar_replies)
        }

        max_servers = int(vals["get_max_servers"])
        # Query every provisioned slot, not just the active ones: SWIM's own
        # total is taken over its whole utilization map, which retains entries
        # for servers that have since been removed (their sliding-window value
        # decays to zero on its own).
        util_cmds = [f"get_utilization server{i}" for i in range(1, max_servers + 1)]
        util_replies = self.command(*util_cmds)
        utils: list[float] = []
        for cmd, reply in zip(util_cmds, util_replies):
            if reply.startswith("error:"):
                utils.append(0.0)       # slot does not exist -- contributes nothing
                continue
            value = self._num(reply, cmd)
            utils.append(max(0.0, value))   # -1.0 is SWIM's "no such server"

        return Observation(
            servers=int(vals["get_servers"]),
            active_servers=int(vals["get_active_servers"]),
            max_servers=max_servers,
            dimmer=vals["get_dimmer"],
            basic_rt=vals["get_basic_rt"],
            opt_rt=vals["get_opt_rt"],
            basic_throughput=vals["get_basic_throughput"],
            opt_throughput=vals["get_opt_throughput"],
            arrival_rate=vals["get_arrival_rate"],
            utilizations=tuple(utils),
        )

    # -- acting ------------------------------------------------------------
    def add_server(self) -> str:
        return self.command("add_server")[0]

    def remove_server(self) -> str:
        return self.command("remove_server")[0]

    def set_dimmer(self, value: float) -> str:
        return self.command(f"set_dimmer {value:g}")[0]
