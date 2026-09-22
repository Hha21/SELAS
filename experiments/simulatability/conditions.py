"""The three input conditions a simulatability score compares.

Hase et al.'s leakage-adjusted simulatability asks a *simulator* -- a model
standing in for the human the explanation is written for -- to predict the
explained model's output under three inputs: the input alone (``x``), the
explanation alone (``e``), and both (``xe``). The explanation is useful to the
extent that seeing it helps: ``acc(xe) - acc(x)``. The ``e`` arm exists because
an explanation that simply states the answer raises that difference without
explaining anything, so the score is computed separately on the examples where
``e`` alone was sufficient (leaking) and where it was not, and averaged.

Two things about this setting make the construction simpler than theirs.

The target is not a gold label. There is no correct action for a period -- only
the action the controller took -- so the simulator's job is to reproduce *the
controller's* decision, which is what simulatability means here and removes the
need for ground truth entirely.

The simulator is not trained. Theirs is a T5 fine-tuned on explanation-answer
pairs; ours is a frozen, smaller instruct model from the same family, prompted
with the same exemplars the controller saw. Fine-tuning a simulator on 105
decisions of which 91 are ``no_op`` would learn the base rate and little else,
and the scoring call is already the same one the controller makes. The cost is
that a weak simulator can depress every arm at once, which is why the per-arm
accuracies are reported alongside the difference rather than folded into it.

A fourth condition is ours rather than theirs. The recorded reasoning ends in a
``Therefore:`` line that names the action in words, so ``e`` alone is expected to
leak almost everywhere, which collapses the leaking/non-leaking split that
carries their whole adjustment. ``e_premises`` drops that line and keeps the
premises, separating "the explanation states the answer" from "the explanation
contains what is needed to derive it" -- the distinction the intervention sweep
already found matters here, where negating the SLA premise moved nothing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "faithfulness"))

import interventions as iv  # noqa: E402  single source of assistant_turn

# Constant across periods on purpose: anything varying here would be telemetry
# leaking back in through the redaction itself.
WITHHELD = "  (telemetry withheld)"

_PERIOD = re.compile(r"^\s*Period\s+(\d+)\s*$", re.MULTILINE)


def redact_state(content: str) -> str:
    """Strip a state block down to its header.

    The period number stays: it is not telemetry, and keeping the block's shape
    means the ``e`` arm differs from ``xe`` by the observation and nothing else.
    """
    m = _PERIOD.search(content)
    header = f"---\nPeriod {m.group(1)}" if m else "---"
    return f"{header}\n{WITHHELD}"


def _with_state(messages: list[dict], content: str) -> list[dict]:
    out = [dict(m) for m in messages]
    out[-2]["content"] = content
    return out


def check(messages: list[dict]) -> None:
    """Fail loudly on a shape the conditions would silently mis-edit."""
    if len(messages) < 3:
        raise ValueError(f"expected system + turns, got {len(messages)} messages")
    if messages[-1]["role"] != "assistant" or messages[-2]["role"] != "user":
        raise ValueError(
            f"expected [... user, assistant], got "
            f"[... {messages[-2]['role']}, {messages[-1]['role']}]")


# -- the conditions ----------------------------------------------------------
# Only the final turn is touched. The exemplars are held identical across all
# four arms, including the reasoning inside their assistant turns: they define
# the response format, and stripping them in the ``x`` arm would change the
# demonstrated format at the same time as the information, confounding the one
# difference the score is built on. It also keeps ``x`` identical to the
# ``ablate`` arm of the intervention sweep, so the two are directly comparable.

def xe(messages: list[dict]) -> list[dict]:
    """State and reasoning, exactly as the controller sent it."""
    check(messages)
    return [dict(m) for m in messages]


def x(messages: list[dict]) -> list[dict]:
    """State alone. The baseline the explanation has to beat."""
    check(messages)
    return iv.rebuild_messages(messages, None)


def e(messages: list[dict]) -> list[dict]:
    """Reasoning alone. The leakage probe."""
    check(messages)
    return _with_state(messages, redact_state(messages[-2]["content"]))


def e_premises(messages: list[dict]) -> list[dict]:
    """Reasoning minus its conclusion, state withheld.

    ``truncate(..., 3)`` cuts at the fourth scaffold field, which is the
    ``Therefore:`` line, leaving SLA, Capacity and Trend.
    """
    check(messages)
    reasoning = iv.reasoning_from_messages(messages)
    kept = iv.truncate(reasoning, n_fields=3)
    return iv.rebuild_messages(
        _with_state(messages, redact_state(messages[-2]["content"])), kept)


CONDITIONS = {
    "xe": xe,
    "x": x,
    "e": e,
    "e_premises": e_premises,
}
