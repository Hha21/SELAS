"""LLM backends.

The controller asks a backend for two things, and only two:

``generate``
    continue a prompt (the reasoning pass), and

``score``
    give a probability for each single-token option at the next position (the
    decision).

Scoring rather than generate-and-parse is the central choice. It makes parse
failure structurally impossible, needs no tool-calling or chat-template support
so it works on base models, and hands back a full distribution over actions on
every decision instead of a single sampled string -- which is the readout the
interpretability analysis needs.

``StubBackend`` implements the same interface with no model at all, so the whole
loop can be exercised against a live SWIM before any GPU is involved.
"""

from __future__ import annotations

import logging
import math
import random
from typing import Protocol, runtime_checkable

log = logging.getLogger("controller.backend")

DEFAULT_TIMEOUT = 120.0


@runtime_checkable
class Backend(Protocol):
    name: str

    def generate(
        self, prompt: str, *, max_tokens: int = 160, temperature: float = 0.7,
        stop: list[str] | None = None,
    ) -> str: ...

    def score(self, prompt: str, options: list[str]) -> dict[str, float]: ...


def _softmax(logprobs: dict[str, float]) -> dict[str, float]:
    if not logprobs:
        return {}
    top = max(logprobs.values())
    exp = {k: math.exp(v - top) for k, v in logprobs.items()}
    total = sum(exp.values())
    return {k: v / total for k, v in exp.items()}


class StubBackend:
    """Deterministic stand-in with no model.

    Not a mock in the testing sense -- it really does return a distribution, and
    the loop cannot tell it apart from a served model. Its "reasoning" is
    templated from the state so traces have the right shape, and its scores come
    from the reactive rule with a little mass spread elsewhere, so downstream
    code that consumes distributions gets something non-degenerate to consume.
    """

    name = "stub"

    def __init__(self, seed: int = 0, sharpness: float = 4.0) -> None:
        self._rng = random.Random(seed)
        self.sharpness = sharpness
        self.preferred: str | None = None       # set by the policy each period

    def generate(
        self, prompt: str, *, max_tokens: int = 160, temperature: float = 0.7,
        stop: list[str] | None = None,
    ) -> str:
        return (
            " placeholder, no model attached.\n"
            "  Capacity: placeholder.\n"
            "  Trend: placeholder.\n"
            "  Therefore: stub backend, the scored distribution is what matters."
        )

    def score(self, prompt: str, options: list[str]) -> dict[str, float]:
        logits = {oid: self._rng.gauss(0.0, 0.5) for oid in options}
        if self.preferred in logits:
            logits[self.preferred] += self.sharpness
        return _softmax(logits)


class OpenAICompatBackend:
    """Any OpenAI-compatible completions endpoint -- the NLA server, vLLM, etc.

    Uses ``/v1/completions`` rather than ``/v1/chat/completions`` on purpose:
    the prompt is a single continuous stream whose exact token sequence we care
    about, and a chat wrapper would insert template tokens between the state and
    the position being scored, moving the probe points.
    """

    name = "openai-compat"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "local",
        timeout: float = DEFAULT_TIMEOUT,
        top_logprobs: int = 20,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.top_logprobs = top_logprobs
        # Which options the last score() had to price with a separate echo
        # request. Worth surfacing: if it is most of them every period, the
        # endpoint's top-k is too small and each decision costs N+1 round trips.
        self.last_fallback_ids: list[str] = []
        # vLLM has rejected max_tokens=0 on some versions. Settled on first use
        # rather than assumed, then remembered for the rest of the run.
        self._echo_max_tokens: int | None = None

    # -- transport ---------------------------------------------------------
    def _post(self, path: str, payload: dict) -> dict:
        import requests   # imported here so StubBackend needs no dependency

        resp = requests.post(
            f"{self.base_url}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    # -- interface ---------------------------------------------------------
    def generate(
        self, prompt: str, *, max_tokens: int = 160, temperature: float = 0.7,
        stop: list[str] | None = None,
    ) -> str:
        data = self._post("/completions", {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stop": stop or ["\nAction:", "\n---"],
        })
        return data["choices"][0]["text"]

    def score(self, prompt: str, options: list[str]) -> dict[str, float]:
        """Probability of each option as the next token.

        One request covers it when every option lands in the endpoint's top-k;
        otherwise the missing ones are scored exactly, one request each, by
        echoing ``prompt + option`` and reading the final token's logprob. The
        fallback matters: an option that is merely unlikely must come back with
        a small probability, not silently vanish from the distribution.
        """
        data = self._post("/completions", {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": 1,
            "temperature": 0.0,
            "logprobs": self.top_logprobs,
        })
        top = (data["choices"][0].get("logprobs") or {}).get("top_logprobs") or [{}]
        table = top[0] if top else {}

        logprobs: dict[str, float] = {}
        missing: list[str] = []
        self.last_fallback_ids = []
        for oid in options:
            # Tokenisers usually emit " A" rather than "A" after "Action:", so
            # both spellings count and the better one wins.
            candidates = [table.get(oid), table.get(f" {oid}")]
            found = [c for c in candidates if c is not None]
            if found:
                logprobs[oid] = max(found)
            else:
                missing.append(oid)

        for oid in missing:
            logprobs[oid] = self._echo_logprob(prompt, oid)
        self.last_fallback_ids = missing

        return _softmax(logprobs)

    def _echo_logprob(self, prompt: str, option_id: str) -> float:
        candidates = [self._echo_max_tokens] if self._echo_max_tokens is not None else [0, 1]
        data = None
        for max_tokens in candidates:
            try:
                data = self._post("/completions", {
                    "model": self.model,
                    "prompt": f"{prompt} {option_id}",
                    "max_tokens": max_tokens,
                    "echo": True,
                    "logprobs": 0,
                })
            except Exception as exc:
                if max_tokens == candidates[-1]:
                    raise
                log.info("echo scoring with max_tokens=%d rejected (%s); retrying with 1",
                         max_tokens, exc)
                continue
            self._echo_max_tokens = max_tokens
            break
        assert data is not None
        token_logprobs = (data["choices"][0].get("logprobs") or {}).get("token_logprobs") or []
        for value in reversed(token_logprobs):
            if value is not None:
                return float(value)
        log.warning("no echo logprob for option %r; treating as very unlikely", option_id)
        return -30.0


def build_backend(
    kind: str,
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str = "local",
    seed: int = 0,
) -> Backend:
    if kind == "stub":
        return StubBackend(seed=seed)
    if kind == "openai":
        if not base_url or not model:
            raise ValueError("--llm-base-url and --llm-model are required for the openai backend")
        return OpenAICompatBackend(base_url=base_url, model=model, api_key=api_key)
    raise ValueError(f"unknown backend {kind!r}")
