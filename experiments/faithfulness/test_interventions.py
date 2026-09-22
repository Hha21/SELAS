#!/usr/bin/env python3
"""Interventions must bite on both reasoning styles.

The scaffolded arms and the free-form ones write differently, and an
intervention that only understands field labels silently returns the original
for the free-form arms -- which reads downstream as "the perturbation changed
nothing", the exact conclusion the arm exists to test.
"""
import sys
sys.path.insert(0, ".")
import interventions as iv

SCAFFOLD = """Reasoning:
  SLA: breached, 1.240 s against a 0.750 s threshold.
  Capacity: 1 of 3 servers, spare 0.04, nothing booting.
  Trend: arrival rate climbing and utilisation near saturation.
  Therefore: capacity is the binding constraint, so add a server."""

PROSE = ("Reasoning: The response time is well within the SLA (0.166 s < 0.750 s). "
         "Utilization is very low despite a reasonable arrival rate. "
         "This suggests the configuration is over-provisioned. "
         "Therefore I will leave the system as it is.")

FAILURES = []
def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  ' + detail}")
    if not cond:
        FAILURES.append(name)

for label, text in (("scaffold", SCAFFOLD), ("prose", PROSE)):
    print(label)
    for n in (1, 2, 3):
        out = iv.truncate(text, n)
        check(f"{label}: truncate_{n} is a real edit", out != text, repr(out[:60]))
    t1, t2, t3 = (iv.truncate(text, n) for n in (1, 2, 3))
    check(f"{label}: truncations nest", len(t1) <= len(t2) <= len(t3) < len(text),
          f"{len(t1)}/{len(t2)}/{len(t3)} vs {len(text)}")
    check(f"{label}: truncate_3 drops the conclusion",
          "Therefore" not in t3 and "leave the system" not in t3, repr(t3[-60:]))
    check(f"{label}: truncate_1 keeps the SLA claim",
          "0.750" in t1 or "SLA" in t1, repr(t1))
    c = iv.corrupt(text)
    check(f"{label}: corrupt is a real edit", c != text, repr(c[:70]))
    co = iv.corrupt_open(text)
    check(f"{label}: corrupt_open drops the conclusion", "Therefore" not in co)
    check(f"{label}: filler keeps roughly the shape",
          iv.filler(text) != text and len(iv.filler(text)) > 0)
    check(f"{label}: ablate removes everything", iv.ablate(text) is None)
    print()

print("the scaffold path still cuts at field boundaries")
t = iv.truncate(SCAFFOLD, 3)
check("keeps SLA, Capacity, Trend",
      all(f + ":" in t for f in ("SLA", "Capacity", "Trend")))
check("drops Therefore", "Therefore:" not in t)

print("\nprose too short to cut is returned unchanged for the caller to skip")
one = "Reasoning: Everything is fine."
check("single sentence unchanged", iv.truncate(one, 3) == one)

print()
if FAILURES:
    print(f"{len(FAILURES)} failed: {', '.join(FAILURES)}")
    raise SystemExit(1)
print("all checks passed")
