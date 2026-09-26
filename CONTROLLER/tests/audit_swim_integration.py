#!/usr/bin/env python3
"""Audit: end-to-end check of the controller <-> SWIM boundary against a real SWIM.

Three sub-commands:

  drive-a --port P --out DIR
      Drives a live SWIM for ~25 periods through the *production* path:
      ControlLoop -> LLMPolicy -> ContextBuilder -> (scripted backend) -> SwimClient.
      The scripted backend reads the action legend out of the system prompt, as a
      model would, and puts 0.9 of its mass on the letter whose label is the
      scripted action. So a letter/action mismatch anywhere in the chain shows up
      as the wrong change in SWIM's own recorded vectors.

  drive-b --case NAME --port P --out DIR
      Sends raw (unguarded) illegal commands to SWIM to characterise what the
      simulator itself does with them.

  check --results DIR
      Reads SWIM's .vec (SQLite) and the controller's decisions.jsonl and checks
      that exactly the scripted changes happened, at the scripted times, and that
      what the controller observed matches what SWIM recorded.

Written for the audit; not part of the production code.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from controller.actions import (  # noqa: E402
    ADD_SERVER, NO_OP, REMOVE_SERVER, Action, Kind, UnsafeAction, is_legal, validate,
)
from controller.context import ContextBuilder, ReasoningStyle  # noqa: E402
from controller.loop import ControlLoop  # noqa: E402
from controller.policies import LLMPolicy, ReactivePolicy  # noqa: E402
from controller.swim import SwimClient  # noqa: E402
from controller.trajectory import Trajectory  # noqa: E402

PERIOD = float(__import__("os").environ.get("AUDIT_PERIOD", "60"))
BOOT = 180.0


def D(v: float) -> Action:
    return Action(Kind.SET_DIMMER, v)


# period -> (scripted target, action expected to be *executed*)
# Illegal targets must be masked by LLMPolicy, leaving NO_OP (scripted 2nd choice).
SCRIPT: dict[int, tuple[Action, Action]] = {
    0: (NO_OP, NO_OP),
    1: (D(1.0), D(1.0)),
    2: (ADD_SERVER, ADD_SERVER),          # 3 -> 4 provisioned, active at +180
    3: (ADD_SERVER, NO_OP),               # illegal: booting
    4: (REMOVE_SERVER, NO_OP),            # illegal: booting
    5: (D(0.25), D(0.25)),
    6: (NO_OP, NO_OP),
    7: (ADD_SERVER, ADD_SERVER),          # 4 -> 5, active at +180
    8: (D(0.5), D(0.5)),
    9: (NO_OP, NO_OP),
    10: (NO_OP, NO_OP),
    11: (REMOVE_SERVER, REMOVE_SERVER),   # 5 -> 4
    12: (REMOVE_SERVER, REMOVE_SERVER),   # 4 -> 3
    13: (D(0.0), D(0.0)),
    14: (D(1.0), D(1.0)),
    15: (REMOVE_SERVER, REMOVE_SERVER),   # 3 -> 2
    16: (REMOVE_SERVER, REMOVE_SERVER),   # 2 -> 1
    17: (REMOVE_SERVER, NO_OP),           # illegal: last server
    18: (ADD_SERVER, ADD_SERVER),         # 1 -> 2, active at +180
    19: (D(0.75), D(0.75)),
    20: (D(1.0), D(1.0)),
    21: (D(1.0), NO_OP),                  # illegal: dimmer already 1.0
}


class ScriptedBackend:
    """Behaves like a served model: it only sees the messages and option ids."""

    name = "scripted"

    def __init__(self) -> None:
        self.period = 0
        self.log: list[dict] = []

    def generate_chat(self, messages, **kw) -> str:
        return "Reasoning:\n  SLA: scripted.\n  Therefore: scripted audit action."

    def generate(self, prompt, **kw) -> str:
        return self.generate_chat([])

    def _legend(self, text: str) -> dict[str, str]:
        block = text.split("Actions:\n", 1)[1].split("\n\n", 1)[0]
        out = {}
        for line in block.splitlines():
            m = re.match(r"^  ([A-H])  (.+)$", line)
            if m:
                out[m.group(2).strip()] = m.group(1)
        return out

    def score_chat(self, messages, options: list[str]) -> dict[str, float]:
        m = re.search(r"^Period (\d+)$", messages[-2]["content"] if messages[-1]["role"] == "assistant"
                      else messages[-1]["content"], re.M)
        self.period = int(m.group(1))
        target = SCRIPT.get(self.period, (NO_OP, NO_OP))[0]
        legend = self._legend(messages[0]["content"])
        letter = legend[str(target)]
        second = legend["no_op"]
        rest = [o for o in options if o not in (letter, second)]
        dist = {o: 0.01 / max(1, len(rest)) for o in rest}
        dist[letter] = 0.9
        dist[second] = dist.get(second, 0.0) + (0.09 if second != letter else 0.0)
        self.log.append({"period": self.period, "target": str(target),
                         "letter": letter, "legend": legend})
        return dist

    def score(self, prompt, options):
        raise NotImplementedError


def drive_a(port: int, out: Path, periods: int) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s %(message)s")
    backend = ScriptedBackend()
    builder = ContextBuilder(sla=0.75, period_seconds=60, boot_delay=180,
                             reasoning=ReasoningStyle.SCAFFOLD)
    policy = LLMPolicy(backend=backend, builder=builder,
                       fallback=ReactivePolicy(sla=0.75, dimmer_levels=10))
    client = SwimClient(port=port)
    loop = ControlLoop(client=client, policy=policy, trajectory=Trajectory(),
                       run_dir=out / "ctl", run_id="audit-a", period_seconds=PERIOD,
                       max_periods=periods, shadow=ReactivePolicy(dimmer_levels=10))
    loop.install_signal_handlers()
    with client:
        loop.run()
    (out / "backend_log.json").write_text(json.dumps(backend.log, indent=1))
    return 0


# ---------------------------------------------------------------------------
def drive_b(case: str, port: int, out: Path) -> int:
    """Raw, unguarded commands. Every step is logged; SWIM may die mid-way."""
    log: list[dict] = []
    c = SwimClient(port=port, max_retries=1, timeout=5.0)

    def rec(label, fn):
        t = time.time()
        try:
            v = fn()
            if hasattr(v, "as_dict"):
                v = {k: v.as_dict()[k] for k in ("servers", "active_servers", "max_servers",
                                                  "dimmer", "utilizations")}
            log.append({"t": t, "step": label, "ok": True, "value": v})
        except Exception as exc:          # noqa: BLE001
            log.append({"t": t, "step": label, "ok": False, "error": repr(exc)})
        print(json.dumps(log[-1]), flush=True)

    c.connect()
    rec("sense0", c.sense)
    if case == "add_while_booting":           # run with bootDelay 60, init 2, max 4
        obs = c.sense()
        rec("legal? add (before)", lambda: is_legal(ADD_SERVER, obs))
        rec("add_server #1", c.add_server)
        obs = c.sense()
        rec("sense after #1", lambda: obs)
        rec("is_legal(add) while booting", lambda: is_legal(ADD_SERVER, obs))
        rec("validate(add) while booting", lambda: str(validate(ADD_SERVER, obs)))
        rec("RAW add_server #2 while booting", c.add_server)
        rec("sense after #2", c.sense)
        time.sleep(70)
        rec("sense +70s", c.sense)
        time.sleep(5)
        rec("sense +75s", c.sense)
    elif case == "add_at_max":                # bootDelay 0, init 3, max 3
        obs = c.sense()
        rec("validate(add) at max", lambda: str(validate(ADD_SERVER, obs)))
        rec("RAW add_server at max", c.add_server)
        time.sleep(2)
        rec("sense after", c.sense)
        time.sleep(20)
        rec("sense +20s", c.sense)
    elif case == "remove_last":               # bootDelay 0, init 1, max 3
        obs = c.sense()
        rec("validate(remove) at 1", lambda: str(validate(REMOVE_SERVER, obs)))
        rec("RAW remove_server at 1", c.remove_server)
        time.sleep(2)
        rec("sense after", c.sense)
        time.sleep(20)
        rec("sense +20s", c.sense)
    elif case == "dimmer_values":             # bootDelay 0, init 3, max 3
        for v in ("0.25", "0.333333", "1.7", "-0.5", "abc", "1", "0"):
            rec(f"RAW set_dimmer {v}", lambda v=v: c.command(f"set_dimmer {v}")[0])
            rec(f"get_dimmer after {v}", lambda: c.command("get_dimmer")[0])
            time.sleep(1)
        # the client's own formatting of the five representative values
        for v in (0.0, 0.25, 0.5, 0.75, 1.0, 1 / 9, 8 / 9):
            rec(f"client.set_dimmer({v!r})", lambda v=v: c.set_dimmer(v))
            rec(f"get_dimmer after client {v!r}", lambda: c.command("get_dimmer")[0])
        rec("sense end", c.sense)
    else:
        raise SystemExit(f"unknown case {case}")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"b_{case}.json").write_text(json.dumps(log, indent=1, default=str))
    return 0


# ---------------------------------------------------------------------------
def read_vec(vec: Path, name: str) -> list[tuple[float, float]]:
    with sqlite3.connect(f"file:{vec}?mode=ro", uri=True) as c:
        exp = c.execute("SELECT simtimeExp FROM run LIMIT 1").fetchone()[0]
        rows = c.execute(
            "SELECT simtimeRaw, eventNumber, value FROM vector NATURAL JOIN vectorData "
            "WHERE vectorName=? ORDER BY simtimeRaw, eventNumber", (name,)).fetchall()
    return [(r * 10.0 ** exp, v) for r, _, v in rows]


def changes(series: list[tuple[float, float]]) -> list[tuple[float, float, float]]:
    """(time, old, new) for every change of value."""
    out, prev = [], None
    for t, v in series:
        if prev is not None and v != prev and t >= 1.0:   # t=0: initial servers
            out.append((t, prev, v))
        prev = v
    return out


def value_at(series, t, strict=True):
    """Last recorded value strictly before t."""
    v = None
    for x, y in series:
        if x < t or (not strict and x <= t):
            v = y
        else:
            break
    return v


def _estimate_offset(decisions, bchg) -> float:
    """sim time of controller-elapsed 0: median lag between each recorded dimmer
    change and the latest earlier sent set_dimmer decision with that value."""
    sent = [(d["sim_elapsed_s"], 1.0 - d["decision"]["action_value"]) for d in decisions
            if d["execution"]["sent"] and d["decision"]["action_kind"] == "set_dimmer"]
    diffs = []
    for tg, _, new in bchg:
        cands = [tg - e for e, b in sent if abs(b - new) < 1e-9 and 0 <= tg - e <= 30]
        if cands:
            diffs.append(min(cands))
    if not diffs:
        raise ValueError("no dimmer change could be paired with a decision")
    diffs.sort()
    return diffs[len(diffs) // 2]


def check(results: Path, scripted: bool = True, max_servers: int = 12) -> dict:
    vec = next(results.rglob("*.vec"))
    dec_path = next(results.rglob("decisions.jsonl"))
    decisions = [json.loads(l) for l in dec_path.read_text().splitlines() if l.strip()]
    servers = read_vec(vec, "serverCost:vector")
    active = read_vec(vec, "activeServers:vector")
    brown = read_vec(vec, "brownoutFactor:vector")
    life = read_vec(vec, "lifeTime:vector")
    t_min = max(1.0, min(x for x, _ in servers))       # warm-up: nothing recorded before

    report: dict = {"problems": [], "notes": [], "vec": str(vec), "decisions": len(decisions)}
    P = report["problems"]

    # 1. executed == recorded == scripted; reply OK; illegal never sent
    for d in decisions:
        k, got, ex = d["period"], d["decision"]["action"], d["execution"]
        if scripted and k in SCRIPT and got != str(SCRIPT[k][1]):
            P.append(f"period {k}: executed {got!r}, scripted {str(SCRIPT[k][1])!r}")
        if (d["decision"]["action_kind"] == "no_op") == ex["sent"]:
            P.append(f"period {k}: sent={ex['sent']} for {got} ({ex['reason']})")
        if ex["sent"] and ex["reply"] != "OK":
            P.append(f"period {k}: reply {ex['reply']!r}")

    bchg = changes(brown)
    offset = _estimate_offset(decisions, [c for c in bchg if c[0] >= t_min])
    report["offset_s"] = offset
    if not (-1.0 <= offset <= 15.0):
        P.append(f"implausible clock offset {offset:.2f}s")

    def tsim(d):
        return d["sim_elapsed_s"] + offset

    tol = 3.0          # usual lag: one reasoning pass plus the TCP round trip
    late = 60.0        # landing a whole period after sensing is a fault, not latency
    t_end = max(x for x, _ in life) if life else float("inf")
    exp_brown, exp_srv, exp_act = [], [], []
    for d in decisions:
        if not d["execution"]["sent"]:
            continue
        kind, val, t = d["decision"]["action_kind"], d["decision"]["action_value"], tsim(d)
        if kind == "set_dimmer":
            # a set_dimmer to the value already in force records no change
            if abs(val - d["observation"]["dimmer"]) > 1e-9:
                exp_brown.append((t, 1.0 - val))
        elif kind == "add_server":
            exp_srv.append((t, +1)); exp_act.append((t + BOOT, +1))
        elif kind == "remove_server":
            exp_srv.append((t, -1)); exp_act.append((t, -1))

    def match(label, got, expected, is_delta):
        """Pair each command with the recorded change it caused.

        Paired by value, nearest first, within [-3 s, +60 s] of sensing (the
        clock offset is estimated, so a change can appear to precede its
        command slightly) -- not by position. Positional pairing turned one slow
        decision into a misalignment of every later pair: a shared ~35 s vLLM
        pause at one period, or a decision sensed just before the warm-up cut
        but landing just after it, reported a clean run as 45 problems.
        Nearest-first keeps a warm-up command, whose change SWIM never recorded,
        from claiming the next period's change instead.
        """
        got = [c for c in got if c[0] >= t_min]
        expected = [(t, v) for t, v in expected if t >= t_min - late and t <= t_end]
        pairs = sorted((abs(tg - te), i, j)
                       for i, (te, ve) in enumerate(expected)
                       for j, (tg, og, ng) in enumerate(got)
                       if -tol <= tg - te <= late
                       and ((ng - og == ve) if is_delta else abs(ng - ve) < 1e-9))
        hit, used = {}, set()
        for _, i, j in pairs:
            if i not in hit and j not in used:
                hit[i] = j; used.add(j)
        lags = []
        for i, (te, ve) in enumerate(expected):
            if i not in hit:
                if te >= t_min + tol:          # before that, SWIM was not yet recording
                    P.append(f"{label}: expected {ve} at ~{te:.1f}s, no matching change recorded")
                continue
            lag = got[hit[i]][0] - te
            lags.append(lag)
            if lag > tol:
                report["notes"].append(f"{label}: {ve} landed {lag:.1f}s after ~{te:.1f}s")
        for i, (tg, og, ng) in enumerate(got):
            if i not in used:
                P.append(f"{label}: recorded {og}->{ng} at {tg:.1f}s with no command to cause it")
        report[label] = [(round(t, 2), o, n) for t, o, n in got]
        if lags:
            lags.sort()
            report[f"{label}_lag_median_s"] = round(lags[len(lags) // 2], 2)

    match("brownoutFactor", bchg, exp_brown, False)
    match("serverCost", changes(servers), exp_srv, True)
    match("activeServers", changes(active), exp_act, True)

    # 2. observation vs recorded state just before sensing; RT vs lifeTime
    obs_rows, rt_err = [], []
    allchg = changes(servers) + changes(active) + bchg
    for d in decisions:
        t, o = tsim(d), d["observation"]
        if t < t_min + tol:
            continue
        rec_srv, rec_act, rec_b = value_at(servers, t), value_at(active, t), value_at(brown, t)
        near = any(abs(x - t) < 2.0 for x, _, _ in allchg)
        win = [v for x, v in life if t - PERIOD < x <= t]
        rt_mean = sum(win) / len(win) if win else float("nan")
        row = {"period": d["period"], "t": round(t, 1),
               "obs_servers": o["servers"], "rec_servers": rec_srv,
               "obs_active": o["active_servers"], "rec_active": rec_act,
               "obs_dimmer": o["dimmer"], "rec_dimmer": None if rec_b is None else 1 - rec_b,
               "obs_avg_rt": round(o["avg_rt"], 4), "lifeTime_mean_60s": round(rt_mean, 4),
               "n_responses_60s": len(win),
               "obs_completions_60s": round(60 * (o["basic_throughput"] + o["opt_throughput"]), 1),
               "obs_total_util": round(o["total_utilization"], 3), "near_event": near}
        obs_rows.append(row)
        if o["max_servers"] != max_servers:
            P.append(f"max_servers observed {o['max_servers']} at period {d['period']}")
        if near:
            continue
        if o["servers"] != rec_srv or o["active_servers"] != rec_act \
                or abs(o["dimmer"] - (1 - rec_b)) > 1e-5:
            P.append(f"observation mismatch at period {d['period']}: {row}")
        if win and o["avg_rt"] > 0:
            rt_err.append(abs(o["avg_rt"] - rt_mean) / max(rt_mean, 1e-9))
    if rt_err:
        rt_err.sort()
        report["rt_rel_err_median"] = rt_err[len(rt_err) // 2]
        report["rt_rel_err_p90"] = rt_err[int(0.9 * (len(rt_err) - 1))]
    report["observations"] = obs_rows
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("drive-a"); a.add_argument("--port", type=int, required=True)
    a.add_argument("--out", type=Path, required=True); a.add_argument("--periods", type=int, default=25)
    b = sub.add_parser("drive-b"); b.add_argument("--case", required=True)
    b.add_argument("--port", type=int, required=True); b.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("check"); c.add_argument("--results", type=Path, required=True)
    c.add_argument("--unscripted", action="store_true", help="a real run, not drive-a")
    c.add_argument("--brief", action="store_true", help="omit the per-period table")
    args = ap.parse_args()
    if args.cmd == "drive-a":
        return drive_a(args.port, args.out, args.periods)
    if args.cmd == "drive-b":
        return drive_b(args.case, args.port, args.out)
    rep = check(args.results, scripted=not args.unscripted)
    if args.brief:
        rep.pop("observations")
    print(json.dumps(rep, indent=1, default=str))
    return 1 if rep["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
