"""Swap the objective in a recorded decision's system prompt, and nothing else.

The mediation experiment holds a decision's state (and, in one condition, its
reasoning) fixed and changes only the objective the controller was given. The
objective is one block of the system message, between the constraints and the
action legend (``ContextBuilder._objective_lines``), so the swap is a
substitution of that block. It is checked, not assumed: the block found in the
recorded message must be exactly the one the builder renders for the claimed
objective, or the swap refuses -- a prompt that differs anywhere else would
confound the one difference the experiment is about.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "CONTROLLER"))
from controller.context import OBJECTIVES, ContextBuilder  # noqa: E402

# The last constraints line; the objective block starts after it and a blank line.
_BEFORE = "  period    one decision every"
_AFTER = "Actions:"


def objective_block(objective: str, max_servers: int) -> str:
    """The objective exactly as it appears in the system message ("" for none)."""
    if objective not in OBJECTIVES:
        raise ValueError(f"unknown objective {objective!r}")
    lines = ContextBuilder(objective=objective)._objective_lines(max_servers)
    return ("\n".join(lines) + "\n") if lines else ""


def _segment(system: str) -> tuple[int, int]:
    i = system.index(_BEFORE)
    start = system.index("\n", i) + 2          # past the period line and the blank line
    end = system.index(_AFTER, start)
    return start, end


def swap_objective(system: str, old: str, new: str, max_servers: int) -> str:
    """The system message with objective ``old`` replaced by ``new``."""
    start, end = _segment(system)
    found, expected = system[start:end], objective_block(old, max_servers)
    if found != expected:
        raise ValueError(f"the recorded objective block is not {old!r}:\n{found!r}")
    return system[:start] + objective_block(new, max_servers) + system[end:]


def swap_messages(messages: list[dict], old: str, new: str, max_servers: int) -> list[dict]:
    if messages[0]["role"] != "system":
        raise ValueError("expected a system message first")
    out = [dict(m) for m in messages]
    out[0]["content"] = swap_objective(messages[0]["content"], old, new, max_servers)
    return out
