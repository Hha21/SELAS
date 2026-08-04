"""FastAPI server for the NLA web demo.

Run from the repo root:
    uvicorn server.main:app --host 0.0.0.0 --port 8000

Then open http://localhost:8000/ in a browser.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import (
    AR_CHECKPOINT, AV_CHECKPOINT, CAPTURE_TRACES, DEVICE, DTYPE, MODEL_ID,
    PROBE_LAYER, RUN_ID, TRACE_DIR,
)
from server.inference import NLAInference
from server.traces import TraceWriter


ROOT     = Path(__file__).parent.parent
FRONTEND = ROOT / "frontend"

# Hard ceiling on generation length, overridable per deployment. POLARIS's SWIM
# config asks for max_tokens=4096; a 0.5B base model with no EOS discipline will
# generate all of it, which is minutes per call on a small GPU.
MAX_NEW_TOKENS_CAP = int(os.getenv("NLA_MAX_NEW_TOKENS", "256"))

# POLARIS's dashboard bridge (src/scripts/dashboard_bridge.py). Optional --
# everything else works without it; the architecture view just stays static.
POLARIS_BRIDGE_URL = os.getenv("POLARIS_BRIDGE_URL", "http://127.0.0.1:8090").rstrip("/")

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["nla"]    = NLAInference()
    state["traces"] = TraceWriter(TRACE_DIR, RUN_ID, enabled=CAPTURE_TRACES)
    yield
    state.clear()


app = FastAPI(title="NLA demo", lifespan=lifespan)


# --------------------------------------------------------------------- schemas
class TokenizeRequest(BaseModel):
    text: str


class AnalyzeRequest(BaseModel):
    """Either supply pre-tokenised IDs (preferred, used by the chat flow) or
    raw text (used by the standalone tokenise flow)."""
    text:      str | None       = None
    token_ids: list[int] | None = None
    position:  int              = -1


class ChatMessage(BaseModel):
    role:    Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    messages:       list[ChatMessage]
    max_new_tokens: int   = Field(200, ge=1, le=1024)
    temperature:    float = Field(0.7, ge=0.0, le=2.0)
    top_p:          float = Field(0.9, gt=0.0, le=1.0)


# --------------------------------------------------------------------- routes
@app.get("/api/health")
def health():
    """Report the live configuration, so the UI never has to hardcode it.

    The frontend renders the backbone, probe layer and checkpoint paths from
    this response: a mismatched AV/AR pair or a wrong probe layer still produces
    plausible-looking output, so the values actually in use need to be visible.
    """
    nla = state.get("nla")
    w   = state.get("traces")
    return {
        "status":        "ok" if nla else "loading",
        "model":         MODEL_ID,
        "probe_layer":   PROBE_LAYER,
        "d_model":       nla.d_model if nla else None,
        "dtype":         str(DTYPE).replace("torch.", ""),
        "device":        DEVICE,
        "checkpoint_av": str(AV_CHECKPOINT),
        "checkpoint_ar": str(AR_CHECKPOINT),
        "fve_baseline":  ("corpus mean" if nla and nla.corpus_mean is not None
                          else "unavailable"),
        "max_new_tokens": MAX_NEW_TOKENS_CAP,
        "traces": {
            "enabled":     bool(w and w.enabled),
            "run_id":      w.run_id if w else None,
            "dir":         str(w.dir) if w else None,
            "written":     w.count if w else 0,
            "last_error":  state.get("trace_error"),
        },
    }


@app.post("/api/tokenize")
def tokenize(req: TokenizeRequest):
    return {"tokens": state["nla"].tokenize(req.text)}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    nla = state["nla"]
    try:
        if req.token_ids is not None:
            return nla.analyze_ids(req.token_ids, req.position)
        if req.text is not None:
            return nla.analyze_text(req.text, req.position)
        raise ValueError("must provide either 'text' or 'token_ids'")
    except (ValueError, IndexError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/chat")
def chat(req: ChatRequest):
    try:
        return state["nla"].chat(
            [m.model_dump() for m in req.messages],
            max_new_tokens = req.max_new_tokens,
            temperature    = req.temperature,
            top_p          = req.top_p,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --------------------------------------------------------- POLARIS dashboard
# The browser cannot speak NATS, and this server deliberately does not depend on
# nats-py (POLARIS keeps nats/grpc, NLA keeps torch -- separate virtualenvs).
# So POLARIS runs src/scripts/dashboard_bridge.py, and we proxy it here purely
# so the frontend has a single origin: one SSH tunnel, no CORS.
@app.get("/api/polaris/state")
def polaris_state():
    """Proxy the POLARIS dashboard bridge. Never fails -- if the bridge is not
    running, report that plainly so the UI can say 'not connected' rather than
    showing stale or invented numbers."""
    try:
        with urllib.request.urlopen(f"{POLARIS_BRIDGE_URL}/state", timeout=2.0) as r:
            payload = json.loads(r.read().decode())
        payload["bridge"] = {"reachable": True, "url": POLARIS_BRIDGE_URL}
        return payload
    except Exception as e:                                        # noqa: BLE001
        return {
            "connected": False,
            "bridge": {
                "reachable": False,
                "url":       POLARIS_BRIDGE_URL,
                "error":     f"{type(e).__name__}: {e}",
            },
            "metrics": {}, "history": {}, "components": {},
            "activity": [], "route": None, "last_action": None,
        }


# ------------------------------------------------- OpenAI-compatible endpoint
# POLARIS's OpenAICompatibleClient already speaks this schema, so pointing its
# LLM_BASE_URL here needs no code change on that side. It sends only
# messages/temperature/max_tokens and reads choices[0].message.content plus
# usage -- no `tools` parameter, because POLARIS parses tool calls out of the
# response text itself (TOOL_CALL:/PARAMETERS: lines).
class OAIMessage(BaseModel):
    role:    Literal["user", "assistant", "system"]
    content: str | None = None


class OAIChatRequest(BaseModel):
    model:       str | None      = None
    messages:    list[OAIMessage]
    temperature: float           = Field(0.7, ge=0.0, le=2.0)
    max_tokens:  int | None      = None
    # Accepted and ignored, so a client sending them does not 422.
    top_p:       float           = Field(0.9, gt=0.0, le=1.0)
    stream:      bool            = False


@app.post("/v1/chat/completions")
def chat_completions(req: OAIChatRequest):
    nla = state["nla"]
    if req.stream:
        raise HTTPException(status_code=400, detail="streaming is not supported")

    # A base model with no EOS discipline will happily run to any limit it is
    # given, so cap rather than honour a caller's 4096/8192 default.
    max_new = min(req.max_tokens or MAX_NEW_TOKENS_CAP, MAX_NEW_TOKENS_CAP)

    messages = [
        {"role": m.role, "content": m.content or ""} for m in req.messages
    ]
    try:
        out = nla.chat(
            messages,
            max_new_tokens = max_new,
            temperature    = req.temperature,
            top_p          = req.top_p,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    prompt_tokens     = out["assistant_token_start"]
    completion_tokens = len(out["token_ids"]) - prompt_tokens

    request_id = _capture_trace(out, messages, prompt_tokens, completion_tokens)

    return {
        "id":      f"chatcmpl-{request_id or uuid.uuid4().hex[:12]}",
        "object":  "chat.completion",
        "created": int(time.time()),
        "model":   req.model or MODEL_ID,
        "choices": [{
            "index":         0,
            "message":       {"role": "assistant", "content": out["assistant_text"]},
            "finish_reason": "length" if completion_tokens >= max_new else "stop",
        }],
        "usage": {
            "prompt_tokens":     prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens":      len(out["token_ids"]),
        },
    }


def _capture_trace(out, messages, prompt_tokens, completion_tokens) -> str | None:
    """Persist activations for every token of this call. Best-effort.

    A failure here must never fail the LLM call the managing system is waiting
    on, so everything is caught and reported through /api/health instead.
    """
    writer = state.get("traces")
    if writer is None or not writer.enabled:
        return None

    request_id = writer.next_request_id()
    acts = None
    try:
        acts = state["nla"].activations_for(out["token_ids"])
    except Exception as e:                                        # noqa: BLE001
        state["trace_error"] = f"{type(e).__name__}: {e}"

    writer.write(
        request_id, acts,
        messages              = messages,
        completion            = out["assistant_text"],
        tokens                = out["tokens"],
        token_ids             = out["token_ids"],
        is_special            = out["is_special"],
        assistant_token_start = out["assistant_token_start"],
        usage                 = {
            "prompt_tokens":     prompt_tokens,
            "completion_tokens": completion_tokens,
        },
        config = {
            "model":       MODEL_ID,
            "probe_layer": PROBE_LAYER,
            "dtype":       str(DTYPE).replace("torch.", ""),
            "device":      DEVICE,
        },
        source = "openai_compatible",
    )
    return request_id


# Static frontend served at the root path. Must be mounted last so it does
# not shadow the /api/* routes above.
app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
