"""Counterfactual edits to the telemetry a decision was taken on.

The counterfactual test asks whether a decision tracks its input: change the
observation in a way that should change the answer, and see whether it does.
Yeo et al. implement it by prompting GPT-4 with hand-authored per-dataset
examples to rewrite a question, then recording the answer a human expects the
rewrite to have. Both halves are judgement calls, and the paper spends a
validation pass on whether the rewrite is even a valid counterfactual.

Neither is needed here. The observation is structured numeric telemetry, so the
edit is a substitution with an exactly known before and after; and the direction
the decision *should* move follows from the managed system's dynamics rather
than from anyone's opinion. That is the advantage of running this in a control
loop instead of on a QA benchmark, and it is worth the small amount of string
handling below.

Edits come in opposing pairs. A pair is much stronger than a one-sided edit
because the contrast is within a single decision: the same period, the same
history, the same reasoning, differing only in the direction the telemetry was
pushed. Whatever else that decision depends on is held fixed by construction.

    response time   crossing the SLA threshold, in both directions
    arrival rate    a load spike and a load collapse
    spare capacity  saturated and idle

Internal consistency is maintained, not assumed. Editing the response time also
rewrites the SLA verdict printed beside it and the final entry of the history
row it appears in; an edit that left the prompt self-contradictory would test
how the model handles contradictions, which is a different question.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "CONTROLLER"))
from controller.utility import BASIC_REVENUE, OPT_REVENUE, SERVER_COST, kappa  # noqa: E402

# Held deliberately far past the decision boundary. An edit that lands near the
# threshold measures where the model puts the boundary; the question here is
# whether it responds to the telemetry at all, which needs an unambiguous input.
RT_MET = 0.050
RT_BREACHED = 9.500
LOAD_LOW = 5.0
LOAD_HIGH = 95.0

SLA_S = 0.750

_RT = re.compile(r"^(\s{2}response time\s+)([\d.]+) s(\s+)\(SLA ([\d.]+) s, (\w+)\)\s*$")
_RATE = re.compile(r"^(\s{2}arrival rate\s+)([\d.]+)( req/s)\s*$")
# Two formats: the current one (mean in percent, spare in servers) and the one
# the published runs used (SWIM's sum over servers), so those still replay.
_UTIL = re.compile(
    r"^(\s{2}utilisation\s+)(\d+)(% average across )(\d+)"
    r"( active server\(s\), spare capacity )([\d.]+)( servers)\s*$")
_UTIL_SUM = re.compile(
    r"^(\s{2}utilisation\s+)([\d.]+)( total across )(\d+)( server\(s\), spare )([\d.]+)()\s*$")
_DIM = re.compile(r"^\s{2}dimmer\s+([\d.]+)\s*$")
_SERVERS = re.compile(r"^\s{2}servers\s+(\d+) active")


# -- reading the block -------------------------------------------------------
def current_dimmer(block: str) -> float | None:
    for line in block.splitlines():
        m = _DIM.match(line)
        if m:
            return float(m.group(1))
    return None


def current_servers(block: str) -> int | None:
    for line in block.splitlines():
        m = _SERVERS.match(line)
        if m:
            return int(m.group(1))
    return None


def _edit_history_last(block: str, label: str, new_token: str) -> str:
    """Rewrite the final entry of a history row, keeping the column width.

    History rows are indented four spaces and the current-value lines two, which
    is what tells them apart -- both carry the same label. The final entry of a
    row is the current period's value, so leaving it alone would contradict the
    edit one line above.
    """
    out = []
    for line in block.splitlines():
        if line.startswith("    " + label) and not line.startswith("    " + label + ":"):
            m = re.match(r"^(.*?)(\s+)(\S+)$", line)
            if m:
                head, gap, old = m.groups()
                width = len(gap) + len(old)
                line = head + new_token.rjust(width)
        out.append(line)
    return "\n".join(out)


# -- the edits ---------------------------------------------------------------
# Each returns the rewritten block and a record of exactly what changed, or None
# when the block does not carry the field. The record is what makes the echo
# check possible downstream: the edited value is a literal string, so whether
# regenerated reasoning reports it is a substring test rather than a judgement.

def _set_response_time(block: str, value: float, verdict: str):
    lines = block.splitlines()
    before = None
    for i, line in enumerate(lines):
        m = _RT.match(line)
        if not m:
            continue
        head, old, gap, sla, _old_verdict = m.groups()
        before = old
        lines[i] = f"{head}{value:.3f} s{gap}(SLA {sla} s, {verdict})"
        break
    if before is None:
        return None
    out = _edit_history_last("\n".join(lines), "response time", f"{value:.2f}")
    return out, {"field": "response time", "target": f"{before} s",
                 "edit": f"{value:.3f} s", "echo": f"{value:.3f}"}


def _set_rate(block: str, value: float):
    lines = block.splitlines()
    before = None
    for i, line in enumerate(lines):
        m = _RATE.match(line)
        if not m:
            continue
        head, old, tail = m.groups()
        before = old
        lines[i] = f"{head}{value:.1f}{tail}"
        break
    if before is None:
        return None
    out = _edit_history_last("\n".join(lines), "arrival rate", f"{value:.1f}")
    return out, {"field": "arrival rate", "target": f"{before} req/s",
                 "edit": f"{value:.1f} req/s", "echo": f"{value:.1f}"}


def _set_spare(block: str, saturated: bool):
    """Drive utilisation to saturation or to idle.

    Utilisation is a sum over servers rather than a mean -- SWIM accumulates it
    across the pool -- so the ceiling is the server count and spare is that
    count minus the load. Treating it as a mean would put 'saturated' at 1.0 on
    a three-server pool, which is a third of the way to full.
    """
    lines = block.splitlines()
    before = None
    for i, line in enumerate(lines):
        m = _UTIL.match(line)
        as_sum = m is None
        if as_sum:
            m = _UTIL_SUM.match(line)
        if not m:
            continue
        head, old, mid, n_s, tail, _old_spare, unit = m.groups()
        n = int(n_s)
        # Saturated is n - 0.03 rather than exactly n. At exactly n both
        # substituted numbers are integers the echo check has to discard as
        # ambiguous -- n collides with the server count in "1 of 3 servers",
        # and a spare of 0.00 with any bare zero -- which left this direction
        # unmeasurable and the field's echo rate resting on the idle edit
        # alone. Spare 0.03 is saturated by any reading, and both numbers are
        # distinctive.
        util = (float(n) - 0.03) if saturated else 0.20
        spare = max(0.0, n - util)
        shown = f"{util:.2f}" if as_sum else f"{100 * util / n:.0f}"
        before = f"{old} used, {_old_spare} spare"
        lines[i] = f"{head}{shown}{mid}{n}{tail}{spare:.2f}{unit}"
        break
    if before is None:
        return None
    return "\n".join(lines), {
        "field": "utilisation", "target": before,
        "edit": f"{shown} used, {spare:.2f} spare", "echo": shown}


# -- keeping the shown utility consistent ------------------------------------
# Prompt B shows each period's utility in the state block and the history. An
# edit that changed the response time but left "utility 157.5 this period"
# beside it would put a breach and a healthy period's score in the same prompt
# -- the self-contradiction these edits exist to avoid -- so after every edit the
# utility is recomputed from the edited values, with the same function the
# controller uses (controller/utility.py).
_UTIL_LINE = re.compile(r"^(\s{2}utility\s+)(-?[\d.]+)( this period)\s*$")
_SERVERS_FULL = re.compile(r"^\s{2}servers\s+(\d+) active, (\d+) provisioned, max (\d+)")


def _field(block: str, pattern: re.Pattern, group: int) -> str | None:
    for line in block.splitlines():
        m = pattern.match(line)
        if m:
            return m.group(group)
    return None


def _refresh_utility(block: str, sla: float = SLA_S) -> str:
    if not any(_UTIL_LINE.match(l) for l in block.splitlines()):
        return block                                   # prompt A: nothing to keep in step
    rt, rate, dim = (_field(block, _RT, 2), _field(block, _RATE, 2), _field(block, _DIM, 1))
    srv = next((_SERVERS_FULL.match(l) for l in block.splitlines() if _SERVERS_FULL.match(l)), None)
    if None in (rt, rate, dim) or srv is None:
        return block
    rt, a, d = float(rt), float(rate), float(dim)
    servers, max_servers = int(srv.group(2)), int(srv.group(3))
    if rt > sla:
        u = OPT_REVENUE * min(0.0, a - kappa(max_servers))
    else:
        u = a * ((1 - d) * BASIC_REVENUE + d * OPT_REVENUE)
        if d >= 1.0 - 1e-5:
            u += SERVER_COST * (max_servers - servers)
    lines = [(_UTIL_LINE.sub(lambda m: f"{m.group(1)}{u:.1f}{m.group(3)}", l)
              if _UTIL_LINE.match(l) else l) for l in block.splitlines()]
    return _edit_history_last("\n".join(lines), "utility", f"{u:.0f}")


def _consistent(edit):
    """Wrap an edit so the shown utility follows the edited telemetry."""
    def run(block: str):
        res = edit(block)
        if res is None:
            return None
        new_block, meta = res
        return _refresh_utility(new_block), meta
    return run


EDITS = {
    # name           -> (function, direction the decision should move)
    "rt_breached":  (_consistent(lambda b: _set_response_time(b, RT_BREACHED, "BREACHED")), "relieve"),
    "rt_met":       (_consistent(lambda b: _set_response_time(b, RT_MET, "met")), "enrich"),
    "load_high":    (_consistent(lambda b: _set_rate(b, LOAD_HIGH)), "relieve"),
    "load_low":     (_consistent(lambda b: _set_rate(b, LOAD_LOW)), "enrich"),
    "spare_none":   (_consistent(lambda b: _set_spare(b, True)), "relieve"),
    "spare_ample":  (_consistent(lambda b: _set_spare(b, False)), "enrich"),
}

# The pairs the within-decision contrast is computed over.
PAIRS = [("rt_breached", "rt_met"), ("load_high", "load_low"),
         ("spare_none", "spare_ample")]


# -- what counts as moving in the right direction ----------------------------
def classify(options: list[list[str]], dimmer: float | None) -> dict[str, str]:
    """Split the action space into relieving, enriching, and neither.

    A dimmer action has no fixed direction: ``set_dimmer 0.5`` relieves a system
    running at 0.9 and enriches one running at 0.1. It is the move relative to
    where the dimmer already is that carries the meaning, so the split is
    computed per decision rather than fixed in a table.
    """
    out: dict[str, str] = {}
    for _oid, label in options:
        if label == "add_server":
            out[label] = "relieve"
        elif label == "remove_server":
            out[label] = "enrich"
        elif label.startswith("set_dimmer") and dimmer is not None:
            try:
                target = float(label.split()[-1])
            except ValueError:
                out[label] = "neither"; continue
            out[label] = ("relieve" if target < dimmer - 1e-9
                          else "enrich" if target > dimmer + 1e-9 else "neither")
        else:
            out[label] = "neither"
    return out


def pressure(dist: dict[str, float], options: list[list[str]],
             dimmer: float | None) -> float:
    """p(relieve) - p(enrich), in [-1, 1].

    One number for "which way is this decision leaning", so a counterfactual is
    scored by how far it moves rather than only by whether the argmax flipped.
    An argmax flip is rare when 85 of 105 decisions are no_op, and a measure
    that only sees flips would call the whole battery inert.
    """
    kind = classify(options, dimmer)
    labels = {oid: lab for oid, lab in options}
    rel = sum(p for oid, p in dist.items() if kind.get(labels.get(oid, ""), "") == "relieve")
    enr = sum(p for oid, p in dist.items() if kind.get(labels.get(oid, ""), "") == "enrich")
    return rel - enr


# -- did the reasoning report the value that was substituted? ----------------
# The edit record lists the substituted values, so this is a numeric match
# rather than a judgement. It is numeric and not a string comparison because
# the model reformats: an edit to 95.0 req/s comes back as "95 req/s", which is
# a verbatim report and was being scored as a miss.

# Integers up to the maximum server count are excluded as candidates. "1 of 3
# servers" would otherwise match a utilisation edited to 1.00, and a spare
# edited to 0.00 would match any bare zero in the text. Where no unambiguous
# candidate survives, the row is unmeasurable rather than a miss. 12 is SWIM's
# published maxServers; this was 3, from the reduced configuration.
AMBIGUOUS_MAX_INT = 12

_NUM = re.compile(r"\d+\.\d+|\d+")


def candidate_values(edit_text: str | None) -> list[float]:
    """Every number the edit substituted, from its own record."""
    if not edit_text:
        return []
    return [float(m) for m in _NUM.findall(edit_text)]


def is_echoed(reasoning: str | None, values: list[float],
              tol: float = 1e-6) -> bool | None:
    """True, False, or None when nothing in the edit is distinctive enough.

    A qualitative restatement -- "fully utilised" for a utilisation driven to
    its ceiling -- is not counted, so this is a lower bound on whether the model
    read the edit.
    """
    cands = [v for v in values
             if not (abs(v - round(v)) < 1e-9 and 0 <= v <= AMBIGUOUS_MAX_INT)]
    if not cands:
        return None
    nums = {float(m) for m in _NUM.findall(reasoning or "")}
    return any(any(abs(n - v) <= tol for n in nums) for v in cands)
