#!/usr/bin/env python3
"""
Dashboard bridge: NATS -> HTTP JSON, for the NLA frontend's architecture view.

POLARIS components talk to each other over NATS. The frontend cannot speak NATS
(it is a browser), and the NLA server deliberately does not depend on nats-py --
keeping POLARIS's dependencies (nats/grpc) and NLA's (torch/transformers) in
separate virtualenvs is what lets each be installed and run independently.

So this bridge lives on the POLARIS side, where nats-py already is. It
subscribes read-only to `polaris.>`, keeps a rolling in-memory view, and serves
it as JSON. The NLA server proxies that to the browser so everything is on one
origin (one SSH tunnel, no CORS).

It is strictly an observer: it publishes nothing and can be started or stopped
at any point in a run without affecting the system it is watching.

Deliberately uses only the standard library for HTTP (no FastAPI/uvicorn) so
POLARIS's requirements.txt does not grow for a read-only debug view.

Usage:
    python src/scripts/dashboard_bridge.py
    python src/scripts/dashboard_bridge.py --nats nats://localhost:4222 --port 8090
"""

import argparse
import asyncio
import json
import signal
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from nats.aio.client import Client as NATS
from nats.aio.msg import Msg

# Subject prefix -> component id in the frontend diagram (data-agent attribute).
# First match wins, so more specific prefixes are listed first.
SUBJECT_COMPONENTS = [
    ("polaris.telemetry.events",        "metric-collector"),
    ("polaris.reasoner.kernel.requests", "reasoner"),
    ("polaris.execution.fast",          "reactive"),
    ("polaris.execution.decisions",     "kernel"),
    ("polaris.execution.actions",       "execution-adapter"),
    ("polaris.execution.results",       "execution-adapter"),
    ("polaris.execution.metrics",       "execution-adapter"),
    ("polaris.verification.",           "verifier"),
    ("polaris.knowledge.",              "kb"),
    ("polaris.digitaltwin.",            "wm"),
    ("polaris.meta_learner.",           "meta"),
]

# Which route the Kernel took, inferred from the subject it dispatched on.
ROUTE_SUBJECTS = {
    "polaris.reasoner.kernel.requests": "strategic",
    "polaris.execution.fast":           "stabilization",
}

# Metrics kept as a time series for the frontend sparklines. Others are still
# reported as latest-value only.
HISTORY_METRICS = {
    "average_response_time", "server_utilization", "dimmer",
    "active_servers", "arrival_rate",
}
HISTORY_LEN  = 120
ACTIVITY_LEN = 60

# A component counts as "working" if it produced traffic this recently.
ACTIVE_WINDOW_SEC = 12.0


def log(msg: str) -> None:
    """Print unbuffered -- stdout is a pipe when run from start.sh, and the
    default block buffering would hold these back until the process exits."""
    print(f"[bridge] {msg}", flush=True)


def component_for(subject: str) -> Optional[str]:
    for prefix, comp in SUBJECT_COMPONENTS:
        if subject.startswith(prefix):
            return comp
    return None


class BridgeState:
    """Rolling view of the run. Mutated from the asyncio loop, read from the
    HTTP threads, so every access is under one lock."""

    def __init__(self) -> None:
        self._lock     = threading.Lock()
        self.started   = time.time()
        self.messages  = 0
        self.nats_ok   = False
        self.metrics: Dict[str, Dict[str, Any]] = {}
        self.history: Dict[str, deque]          = {}
        self.components: Dict[str, Dict[str, Any]] = {}
        self.activity  = deque(maxlen=ACTIVITY_LEN)
        self.route: Optional[str] = None
        self.last_action: Optional[Dict[str, Any]] = None

    # ---------------------------------------------------------------- ingest
    def record(self, subject: str, payload: Any) -> None:
        now = time.time()
        with self._lock:
            self.messages += 1

            comp = component_for(subject)
            if comp:
                c = self.components.setdefault(comp, {"count": 0, "last_seen": 0.0})
                c["count"]    += 1
                c["last_seen"] = now

            if subject in ROUTE_SUBJECTS:
                self.route = ROUTE_SUBJECTS[subject]

            summary = None

            # Telemetry names arrive as "<system>.<metric>", but TelemetryEvent's
            # normalize_name validator lowercases and rewrites '_' as '.', so
            # "swim.average_response_time" is on the wire as
            # "swim.average.response.time". Split off the system prefix and put
            # the underscores back, giving keys that match the metric names in
            # extern/config.yaml (average_response_time, server_utilization, ...).
            if subject.startswith("polaris.telemetry.events") and isinstance(payload, dict):
                name = payload.get("name")
                if isinstance(name, str) and "." in name:
                    system, rest = name.split(".", 1)
                    metric = rest.replace(".", "_")
                    value  = payload.get("value")
                    self.metrics[metric] = {
                        "value":  value,
                        "unit":   payload.get("unit", ""),
                        "system": system,
                        "ts":     now,
                    }
                    # SWIM producing telemetry is what makes the managed system live.
                    s = self.components.setdefault("system", {"count": 0, "last_seen": 0.0})
                    s["count"] += 1
                    s["last_seen"] = now

                    if metric in HISTORY_METRICS and isinstance(value, (int, float)):
                        self.history.setdefault(metric, deque(maxlen=HISTORY_LEN)) \
                                    .append([now, float(value)])
                    summary = f"{name} = {value}"

            # Actions and results carry the adaptation decision itself.
            elif isinstance(payload, dict):
                action_type = payload.get("action_type") or payload.get("type")
                if action_type:
                    summary = str(action_type)
                    params = payload.get("parameters") or payload.get("params")
                    if isinstance(params, dict) and params:
                        summary += " " + json.dumps(params, default=str)[:80]
                    if subject.startswith("polaris.execution.actions"):
                        self.last_action = {
                            "action_type": action_type,
                            "params":      params if isinstance(params, dict) else None,
                            "ts":          now,
                        }
                elif payload.get("status") is not None:
                    summary = f"status={payload.get('status')}"

            self.activity.appendleft({
                "ts":        now,
                "iso":       datetime.fromtimestamp(now, timezone.utc).isoformat(),
                "subject":   subject,
                "component": comp,
                "summary":   summary,
            })

    def set_nats(self, ok: bool) -> None:
        with self._lock:
            self.nats_ok = ok

    # ---------------------------------------------------------------- export
    def snapshot(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            components = {
                cid: {
                    "count":     c["count"],
                    "last_seen": c["last_seen"],
                    "age_sec":   round(now - c["last_seen"], 2),
                    "status":    "working" if now - c["last_seen"] <= ACTIVE_WINDOW_SEC else "idle",
                }
                for cid, c in self.components.items()
            }
            return {
                "connected":   self.nats_ok,
                "uptime_sec":  round(now - self.started, 1),
                "messages":    self.messages,
                "server_time": now,
                "metrics":     dict(self.metrics),
                "history":     {k: list(v) for k, v in self.history.items()},
                "components":  components,
                "activity":    list(self.activity),
                "route":       self.route,
                "last_action": self.last_action,
            }


def make_handler(state: BridgeState):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):                                   # noqa: N802
            path = self.path.split("?")[0].rstrip("/") or "/"
            if path in ("/", "/state", "/health"):
                body = json.dumps(state.snapshot(), default=str).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                # Allow direct browser access too, not just the NLA proxy.
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def log_message(self, *args):                       # noqa: A003
            pass       # a polling dashboard would otherwise flood stdout

    return Handler


async def run(nats_url: str, port: int, subject: str) -> None:
    state = BridgeState()

    httpd = ThreadingHTTPServer(("0.0.0.0", port), make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    log(f"HTTP  http://0.0.0.0:{port}/state")

    nc = NATS()

    async def on_message(msg: Msg) -> None:
        try:
            payload = json.loads(msg.data.decode())
        except Exception:                                   # noqa: BLE001
            payload = None
        state.record(msg.subject, payload)

    async def disconnected_cb():
        state.set_nats(False)
        log(f"NATS disconnected")

    async def reconnected_cb():
        state.set_nats(True)
        log(f"NATS reconnected")

    async def error_cb(e):
        # nats-py's default error handler prints a full traceback for every
        # failed connection attempt (~37 lines). While waiting for POLARIS to
        # bring NATS up that is several hundred lines a minute, so collapse the
        # expected "not up yet" case to nothing and keep anything unexpected.
        if isinstance(e, (ConnectionRefusedError, OSError, asyncio.TimeoutError)):
            return
        log(f"NATS error: {type(e).__name__}: {e}")

    stop = asyncio.Event()

    async def connect_forever() -> None:
        """Keep trying until NATS appears, so the bridge can be started before
        POLARIS (which is what brings the NATS container up). Serving starts
        immediately either way -- the dashboard just shows 'not connected'."""
        announced = False
        while not stop.is_set():
            try:
                await nc.connect(
                    servers=[nats_url],
                    name="polaris-dashboard-bridge",
                    disconnected_cb=disconnected_cb,
                    reconnected_cb=reconnected_cb,
                    error_cb=error_cb,
                    max_reconnect_attempts=-1,
                )
            except Exception as e:                          # noqa: BLE001
                if not announced:
                    log(f"NATS not up at {nats_url} ({e}); retrying")
                    announced = True
                await asyncio.sleep(3)
                continue

            state.set_nats(True)
            await nc.subscribe(subject, cb=on_message)
            log(f"NATS  {nats_url}  subscribed to {subject}")
            return

    connector = asyncio.create_task(connect_forever())

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    await stop.wait()

    log("shutting down")
    connector.cancel()
    httpd.shutdown()
    if nc.is_connected:
        await nc.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--nats",    default="nats://localhost:4222")
    p.add_argument("--port",    type=int, default=8090)
    p.add_argument("--subject", default="polaris.>")
    a = p.parse_args()
    try:
        asyncio.run(run(a.nats, a.port, a.subject))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
