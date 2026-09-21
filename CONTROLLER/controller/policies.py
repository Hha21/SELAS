"""Decision rules: the reactive oracle, and the LLM.

``ReactivePolicy`` is a line-for-line port of SWIM's own
``ReactiveAdaptationManager::evaluate``. It exists to be the correctness oracle
for the whole harness -- run it against ``swim_sa.ini`` config ``Reactive``, run
index 6 with ``--seed-set=1``, and it must reproduce the published utility of
2647. Until it does, no number produced by any other policy means anything.

Details that look like details and are not:

* the comparison is strictly ``>`` then strictly ``<``, so a response time
  exactly on the threshold produces no action at all;
* ``spare`` is ``activeServers - total_utilization``, a sum over servers, not a
  mean (see ``swim.py``);
* the dimmer step is ``1/(levels-1)`` clamped to [0, 1] -- the *controller's*
  arithmetic, which is not the same grid as the utility scorer's brownout
  levels.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .actions import (
    ADD_SERVER, NO_OP, REMOVE_SERVER, Action, DimmerMode, Kind,
    DIMMER_STEP, is_legal, validate,
)
from .backends import Backend, StubBackend
from .context import P_ACTION, ContextBuilder, ReasoningStyle
from .swim import Observation
from .trajectory import Trajectory

log = logging.getLogger("controller.policy")


@dataclass
class PolicyResult:
    """Everything one decision produced, including what was not acted on.

    The unmasked distribution is kept alongside the masked one on purpose:
    whether the model puts mass on an illegal action tells you whether it has
    internalised the constraints, and that is a finding, not noise.
    """

    action: Action
    policy: str
    reasoning: str | None = None
    prompt: str | None = None
    messages: list[dict] | None = None      # chat form; None on the completion path
    probes: dict[str, int] = field(default_factory=dict)
    distribution: dict[str, float] = field(default_factory=dict)          # masked
    raw_distribution: dict[str, float] = field(default_factory=dict)      # unmasked
    options: list[tuple[str, str]] = field(default_factory=list)          # (id, label)
    latency_s: float = 0.0
    notes: dict[str, Any] = field(default_factory=dict)


class ReactivePolicy:
    """SWIM's ReactiveAdaptationManager, in Python."""

    name = "reactive"

    def __init__(self, sla: float = 0.75, require_spare: bool = True) -> None:
        self.sla = sla
        # Reactive2 is this rule minus the spare-capacity guard.
        self.require_spare = require_spare

    def decide(self, obs: Observation, traj: Trajectory | None = None) -> Action:
        dimmer = obs.dimmer
        spare = obs.spare
        booting = obs.booting
        rt = obs.avg_rt

        if rt > self.sla:
            if not booting and obs.servers < obs.max_servers:
                return ADD_SERVER
            if dimmer > 0.0:
                return Action(Kind.SET_DIMMER, max(0.0, round(dimmer - DIMMER_STEP, 6)))
            return NO_OP

        if rt < self.sla:
            if not self.require_spare or spare > 1:
                if dimmer < 1.0:
                    return Action(Kind.SET_DIMMER, min(1.0, round(dimmer + DIMMER_STEP, 6)))
                if not booting and obs.servers > 1:
                    return REMOVE_SERVER
        return NO_OP

    def __call__(self, period: int, obs: Observation, traj: Trajectory) -> PolicyResult:
        start = time.perf_counter()
        action = self.decide(obs, traj)
        return PolicyResult(
            action=action,
            policy=self.name,
            latency_s=time.perf_counter() - start,
        )


class NullPolicy:
    """Never acts. The control that says whether acting helped at all.

    SWIM starts at `initialServers = 3` with the dimmer already high, so a
    controller that does nothing holds maximum capacity for the whole run and
    never pays the 60 s boot delay. That is not obviously bad: the first full
    gemma-3-27b-it run chose no_op on 91 of 105 periods, never touched the server
    count, and still beat the reactive rule by 105% -- which is equally
    consistent with good judgement and with inertia.

    Without this arm the two are indistinguishable, and "the LLM beat the
    baseline" would rest on a comparison that a constant function might also
    win.
    """

    name = "null"

    def decide(self, obs: Observation, traj: Trajectory | None = None) -> Action:
        return NO_OP

    def __call__(self, period: int, obs: Observation, traj: Trajectory) -> PolicyResult:
        return PolicyResult(action=NO_OP, policy=self.name, latency_s=0.0)


class LLMPolicy:
    """One LLM call chain per period: reason, then score the action space."""

    name = "llm"

    def __init__(
        self,
        backend: Backend,
        builder: ContextBuilder,
        *,
        dimmer_mode: DimmerMode = DimmerMode.LEVELS,
        max_reasoning_tokens: int = 200,
        temperature: float = 0.7,
        fallback: ReactivePolicy | None = None,
        chat: bool = True,
    ) -> None:
        self.backend = backend
        self.builder = builder
        self.dimmer_mode = dimmer_mode
        # Chat by default: these are instruction-tuned checkpoints, and driving
        # them as raw few-shot completions puts them outside the format their
        # post-training optimised. It also matters downstream -- the released
        # NLA pairs were trained on chat-template activations, so a
        # raw-completion runtime would stack a format shift on top of the domain
        # shift the interpretability results are trying to measure.
        self.chat = chat
        self.max_reasoning_tokens = max_reasoning_tokens
        self.temperature = temperature
        # Only reached if every option is masked out or the backend fails --
        # scoring cannot produce an unparseable answer, so this is a transport
        # guard, not a parsing one.
        self.fallback = fallback or ReactivePolicy(sla=builder.sla)

    def __call__(self, period: int, obs: Observation, traj: Trajectory) -> PolicyResult:
        start = time.perf_counter()
        notes: dict[str, Any] = {}

        reasoning_text: str | None = None
        messages = None

        if self.chat:
            gen_messages, options = self.builder.build_messages(period, traj)
            if self.builder.reasoning is not ReasoningStyle.NONE:
                try:
                    reasoning_text = self.backend.generate_chat(
                        gen_messages,
                        max_tokens=self.max_reasoning_tokens,
                        temperature=self.temperature,
                        stop=["\nAction:", "\n---"],
                    )
                except Exception as exc:
                    log.warning("reasoning pass failed (%s); scoring without it", exc)
                    notes["reasoning_error"] = str(exc)
                    reasoning_text = ""
            messages, options = self.builder.build_messages(
                period, traj, reasoning=reasoning_text or "")
            prompt = None
        else:
            if self.builder.reasoning is not ReasoningStyle.NONE:
                reasoning_prompt = self.builder.build(period, traj)
                try:
                    reasoning_text = self.backend.generate(
                        reasoning_prompt.text,
                        max_tokens=self.max_reasoning_tokens,
                        temperature=self.temperature,
                        stop=["\nAction:", "\n---"],
                    )
                except Exception as exc:
                    log.warning("reasoning pass failed (%s); scoring without it", exc)
                    notes["reasoning_error"] = str(exc)
                    reasoning_text = ""
            prompt = self.builder.build(period, traj, reasoning_text=reasoning_text)
            options = prompt.options

        # The stub has no view of the state, so give it the reactive answer to
        # concentrate mass on; a served model ignores this entirely.
        if isinstance(self.backend, StubBackend):
            preferred = self.fallback.decide(obs, traj)
            self.backend.preferred = next(
                (oid for oid, a in options if a == preferred), None
            )

        option_ids = [oid for oid, _ in options]
        try:
            raw = (self.backend.score_chat(messages, option_ids) if self.chat
                   else self.backend.score(prompt.text, option_ids))
        except Exception as exc:
            log.error("scoring failed (%s); falling back to the reactive rule", exc)
            result = self.fallback(period, obs, traj)
            result.policy = f"{self.name}:fallback"
            result.latency_s = time.perf_counter() - start
            result.notes = {"score_error": str(exc)}
            return result

        legal_ids = [oid for oid, a in options if is_legal(a, obs)]
        masked = {oid: p for oid, p in raw.items() if oid in legal_ids}
        total = sum(masked.values())
        if total > 0:
            masked = {k: v / total for k, v in masked.items()}
        else:
            # Every legal option scored zero -- degenerate, so take the safe
            # option rather than an arbitrary argmax over nothing.
            log.warning("period %d: no probability mass on any legal action", period)
            masked = {oid: 1.0 for oid, a in options if a == NO_OP}
            notes["degenerate_distribution"] = True

        chosen_id = max(masked, key=masked.__getitem__)
        action = dict(options)[chosen_id]

        try:
            validate(action, obs)
        except Exception as exc:
            log.warning("chosen action %s rejected by the safety gate (%s)", action, exc)
            notes["unsafe"] = str(exc)
            action = NO_OP

        return PolicyResult(
            action=action,
            policy=self.name,
            reasoning=reasoning_text,
            prompt=None if self.chat else prompt.text,
            messages=messages,
            probes={} if self.chat else prompt.probes,
            distribution=masked,
            raw_distribution=raw,
            options=self.builder.legend_entries(options),
            latency_s=time.perf_counter() - start,
            notes=notes,
        )
