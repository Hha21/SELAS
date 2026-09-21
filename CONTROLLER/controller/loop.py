"""The control loop.

Sense, decide, act, once per evaluation period, for as long as the simulation
runs. SWIM is pinned to real time by ``cSocketRTScheduler``, so a period here is
a wall-clock period and the schedule is absolute rather than cumulative -- a slow
decision costs that period some of its budget, it does not shift every later
period.

Two things the loop does beyond the obvious:

* **The reactive rule is evaluated every period regardless of who is driving.**
  It costs nothing, it needs no model, and it turns each run into ~90 paired
  decisions instead of one aggregate number. Where the two rules agree, the LLM
  is not the explanation for the outcome; where they disagree is the interesting
  set, and it is identified for free.

* **Every run gets its own directory and a ``run_id`` stamped on every record.**
  Appending to a shared log with only a timestamp to separate runs is how a
  previous system here ended up with the authors' shipped data and eight local
  runs in one file, silently mixed.
"""

from __future__ import annotations

import json
import logging
import signal
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .actions import Kind, UnsafeAction, validate
from .policies import PolicyResult, ReactivePolicy
from .swim import Observation, SwimClient
from .trajectory import Trajectory

log = logging.getLogger("controller.loop")

Policy = Callable[[int, Observation, Trajectory], PolicyResult]


class ControlLoop:
    def __init__(
        self,
        client: SwimClient,
        policy: Policy,
        trajectory: Trajectory,
        *,
        run_dir: Path,
        run_id: str,
        period_seconds: float = 60.0,
        max_periods: int | None = None,
        shadow: ReactivePolicy | None = None,
        dry_run: bool = False,
    ) -> None:
        self.client = client
        self.policy = policy
        self.trajectory = trajectory
        self.run_dir = run_dir
        self.run_id = run_id
        self.period_seconds = period_seconds
        self.max_periods = max_periods
        self.shadow = shadow
        self.dry_run = dry_run
        self._stop = False
        self._records = 0

        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.run_dir / "decisions.jsonl"

    # -- lifecycle ---------------------------------------------------------
    def request_stop(self, *_: object) -> None:
        if not self._stop:
            log.info("stop requested; finishing the current period")
        self._stop = True

    def install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self.request_stop)

    # -- execution ---------------------------------------------------------
    def _execute(self, result: PolicyResult, obs: Observation) -> dict:
        action = result.action
        if action.kind is Kind.NO_OP:
            return {"sent": False, "reply": None, "reason": "no_op"}
        if self.dry_run:
            return {"sent": False, "reply": None, "reason": "dry_run"}

        try:
            validate(action, obs)
        except UnsafeAction as exc:
            log.warning("refusing to send %s: %s", action, exc)
            return {"sent": False, "reply": None, "reason": f"unsafe: {exc}"}

        try:
            if action.kind is Kind.ADD_SERVER:
                reply = self.client.add_server()
            elif action.kind is Kind.REMOVE_SERVER:
                reply = self.client.remove_server()
            else:
                reply = self.client.set_dimmer(float(action.value))
        except Exception as exc:
            log.error("failed to execute %s: %s", action, exc)
            return {"sent": False, "reply": None, "reason": f"error: {exc}"}

        ok = reply.strip() == "OK"
        if not ok:
            log.warning("SWIM rejected %s: %s", action, reply)
        return {"sent": True, "reply": reply, "reason": None if ok else "rejected"}

    # -- logging -----------------------------------------------------------
    def _write(self, record: dict) -> None:
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        self._records += 1

    # -- main --------------------------------------------------------------
    def run(self) -> int:
        started = time.monotonic()
        period = 0
        log.info("run %s -> %s", self.run_id, self.run_dir)

        while not self._stop:
            if self.max_periods is not None and period >= self.max_periods:
                log.info("reached max_periods=%d", self.max_periods)
                break

            tick_start = time.monotonic()
            try:
                obs = self.client.sense()
            except Exception as exc:
                log.error("sense failed in period %d: %s", period, exc)
                self._sleep_until(started, period + 1)
                period += 1
                continue

            self.trajectory.record_observation(period, obs)
            result = self.policy(period, obs, self.trajectory)

            shadow_action = None
            if self.shadow is not None:
                shadow_action = self.shadow.decide(obs, self.trajectory)

            outcome = self._execute(result, obs)
            self.trajectory.record_decision(period, result.action, obs)

            record = {
                "run_id": self.run_id,
                "period": period,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sim_elapsed_s": round(tick_start - started, 3),
                "observation": obs.as_dict(),
                "decision": {
                    "policy": result.policy,
                    "action": str(result.action),
                    "action_kind": result.action.kind.value,
                    "action_value": result.action.value,
                    "latency_s": round(result.latency_s, 4),
                    "distribution": result.distribution,
                    "raw_distribution": result.raw_distribution,
                    "options": result.options,
                    "probes": result.probes,
                    "notes": result.notes,
                },
                "reasoning": result.reasoning,
                "prompt": result.prompt,
                "messages": result.messages,
                "shadow_reactive": str(shadow_action) if shadow_action else None,
                "agrees_with_reactive": (
                    None if shadow_action is None else shadow_action == result.action
                ),
                "execution": outcome,
            }
            self._write(record)

            log.info(
                "period %-3d rt=%.3f util=%.2f srv=%d/%d dim=%.2f -> %-20s "
                "(reactive: %s%s) %.2fs",
                period, obs.avg_rt, obs.total_utilization, obs.active_servers,
                obs.max_servers, obs.dimmer, str(result.action),
                shadow_action, "" if shadow_action == result.action else " DIFFERS",
                result.latency_s,
            )

            period += 1
            self._sleep_until(started, period)

        log.info("stopped after %d periods, %d records -> %s",
                 period, self._records, self.log_path)
        return period

    def _sleep_until(self, started: float, next_period: int) -> None:
        """Sleep to the next absolute tick, skipping any period already missed."""
        target = started + next_period * self.period_seconds
        now = time.monotonic()
        if now > target:
            missed = int((now - target) // self.period_seconds) + 1
            log.warning("decision overran its period by %.1fs; skipping %d tick(s)",
                        now - target, missed)
            return
        while not self._stop and time.monotonic() < target:
            time.sleep(min(0.5, target - time.monotonic()))
