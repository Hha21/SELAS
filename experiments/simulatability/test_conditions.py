#!/usr/bin/env python3
"""Checks on the four conditions that need no model and no simulator.

The properties worth pinning are the ones a silent bug would break: that each
arm removes what it claims to remove and nothing else, that every arm still
ends at the action cue so the scored token is the action letter, and that the
exemplars are untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import conditions as C

MESSAGES = [
    {"role": "system", "content": "You are the adaptation controller.\nActions:\n  A  add_server"},
    {"role": "user", "content": "---\nPeriod 3\n  servers        1 active\n  dimmer         0.90"},
    {"role": "assistant", "content": "Reasoning:\n  SLA: breached.\nAction: A"},
    {"role": "user", "content": "---\nPeriod 7\n  servers        2 active\n  response time  1.240 s\n  arrival rate   38.4 req/s"},
    {"role": "assistant", "content": "Reasoning:\n  SLA: breached, 1.240 s.\n  Capacity: 2 of 3.\n"
                                     "  Trend: climbing.\n  Therefore: add a server.\nAction:"},
]

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  ' + detail}")
    if not cond:
        FAILURES.append(name)


def main() -> int:
    print("conditions")
    built = {k: f(MESSAGES) for k, f in C.CONDITIONS.items()}

    for name, msgs in built.items():
        check(f"{name}: ends at the action cue",
              msgs[-1]["content"].rstrip().endswith("Action:"),
              repr(msgs[-1]["content"][-40:]))
        check(f"{name}: exemplars untouched",
              msgs[:3] == MESSAGES[:3])
        check(f"{name}: message count preserved", len(msgs) == len(MESSAGES))

    print("\nwhat each arm removes")
    check("xe is the recorded prompt", built["xe"] == MESSAGES)

    check("x drops the reasoning",
          "1.240" not in built["x"][-1]["content"]
          and "Therefore" not in built["x"][-1]["content"])
    check("x keeps the state",
          "38.4 req/s" in built["x"][-2]["content"])

    check("e drops the state",
          "38.4 req/s" not in built["e"][-2]["content"]
          and "2 active" not in built["e"][-2]["content"])
    check("e keeps the period header",
          "Period 7" in built["e"][-2]["content"])
    check("e keeps the reasoning",
          "Therefore: add a server." in built["e"][-1]["content"])

    check("e_premises drops the conclusion",
          "Therefore" not in built["e_premises"][-1]["content"])
    check("e_premises keeps the premises",
          all(f in built["e_premises"][-1]["content"]
              for f in ("SLA:", "Capacity:", "Trend:")))
    check("e_premises drops the state",
          "38.4 req/s" not in built["e_premises"][-2]["content"])

    print("\nnon-mutation")
    check("the input is not modified",
          MESSAGES[-2]["content"].endswith("38.4 req/s")
          and MESSAGES[-1]["content"].endswith("Action:"))

    print("\nredaction is constant")
    a = C.redact_state("---\nPeriod 7\n  arrival rate 38.4 req/s")
    b = C.redact_state("---\nPeriod 7\n  arrival rate 11.2 req/s\n  servers 3 active")
    check("same period, different telemetry -> identical block", a == b, f"{a!r} vs {b!r}")

    print("\nshape checks")
    for bad, why in [
        ([{"role": "user", "content": "x"}], "too short"),
        ([{"role": "system", "content": "s"}, {"role": "assistant", "content": "a"},
          {"role": "user", "content": "u"}], "wrong final roles"),
    ]:
        try:
            C.check(bad)
            check(f"rejects {why}", False, "no error raised")
        except ValueError:
            check(f"rejects {why}", True)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failed: {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
