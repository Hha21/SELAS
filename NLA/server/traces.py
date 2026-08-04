"""
Runtime activation traces.

A trace is one LLM call made by the managing system (POLARIS) against this
server, plus the residual-stream activation at the probe layer for *every*
token of that call -- prompt and completion alike.

Why files rather than explaining in-process: at 12B the target (24GB) and the
AV/AR pair (40GB) do not fit on the workstation's 48GB together, so collecting
activations and explaining them have to be separate passes. The trace file is
the interface between them. It is also the interface between two codebases with
incompatible dependencies -- POLARIS needs nats/grpc, this needs torch -- which
is why they share no Python imports, only HTTP one way and these files back.

Layout:

    traces/<run_id>/
        <request_id>.npz    activations, float16 (seq, d_model)
        <request_id>.json   messages, completion, tokens, usage, config

Activations are float16: the residual stream was computed in fp16/bf16 anyway,
so this is lossless in practice and halves the file. At 12B (d=3840) a
2500-token reasoning step is ~19MB.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


class TraceWriter:
    """Writes one trace per LLM call into traces/<run_id>/.

    Thread-safe: FastAPI serves sync routes from a worker threadpool, so two
    requests can land concurrently even though generation itself serialises.
    """

    def __init__(self, root: Path, run_id: str = "", enabled: bool = True):
        self.enabled = enabled
        self.run_id  = run_id or datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S")
        self.dir     = Path(root) / self.run_id
        self._lock   = threading.Lock()
        self._n      = 0

        if self.enabled:
            self.dir.mkdir(parents=True, exist_ok=True)

    def next_request_id(self) -> str:
        with self._lock:
            self._n += 1
            return f"req-{self._n:05d}"

    @property
    def count(self) -> int:
        return self._n

    def write(
        self,
        request_id: str,
        activations: Optional[np.ndarray],
        *,
        messages:              List[Dict[str, str]],
        completion:            str,
        tokens:                List[str],
        token_ids:             List[int],
        is_special:            List[bool],
        assistant_token_start: int,
        usage:                 Dict[str, int],
        config:                Dict[str, Any],
        source:                str = "unknown",
    ) -> Optional[Path]:
        """Persist one call. Returns the JSON sidecar path, or None if disabled.

        Never raises: a failed trace write must not take down the LLM call the
        managing system is waiting on. Failures are recorded in the sidecar's
        `error` field where possible.
        """
        if not self.enabled:
            return None

        meta = {
            "request_id":            request_id,
            "run_id":                self.run_id,
            "timestamp":             datetime.now(timezone.utc).isoformat(),
            "source":                source,
            "messages":              messages,
            "completion":            completion,
            "tokens":                tokens,
            "token_ids":             token_ids,
            "is_special":            is_special,
            "assistant_token_start": assistant_token_start,
            "n_tokens":              len(token_ids),
            "usage":                 usage,
            "config":                config,
        }

        try:
            if activations is not None:
                np.savez_compressed(
                    self.dir / f"{request_id}.npz",
                    activations=activations.astype(np.float16),
                )
                meta["activations_file"]  = f"{request_id}.npz"
                meta["activations_shape"] = list(activations.shape)
            else:
                meta["activations_file"] = None
        except Exception as e:                                   # noqa: BLE001
            meta["activations_file"] = None
            meta["error"] = f"activation write failed: {e}"

        path = self.dir / f"{request_id}.json"
        try:
            path.write_text(json.dumps(meta, indent=2))
        except Exception:                                        # noqa: BLE001
            return None
        return path


def load_trace(json_path: Path) -> Dict[str, Any]:
    """Read a trace back, with its activations as a float32 (seq, d) array.

    The counterpart to TraceWriter.write() -- used by the offline explanation
    pass, which runs separately (and possibly on a different machine) from the
    run that produced the trace.
    """
    json_path = Path(json_path)
    meta = json.loads(json_path.read_text())

    acts = None
    if meta.get("activations_file"):
        npz = json_path.parent / meta["activations_file"]
        with np.load(npz) as z:
            acts = z["activations"].astype(np.float32)

    meta["activations"] = acts
    return meta
