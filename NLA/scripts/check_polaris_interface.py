"""
Verify the NLA server satisfies POLARIS's LLM client contract.

Imports POLARIS's *actual* OpenAICompatibleClient rather than hand-rolling a
request, so this tests the code path that will really run -- including the
fields it reads back off the response (choices[0].message.content, and
usage.prompt_tokens / usage.completion_tokens, which it returns as a tuple).

POLARIS lives in a separate venv (nats/grpc), but llm_clients.py only imports
`openai`, which is in this venv too -- so the module can be loaded directly.

Usage:
    ./.venv/bin/python scripts/check_polaris_interface.py
    ./.venv/bin/python scripts/check_polaris_interface.py --url http://localhost:8000/v1
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import TRACE_DIR          # must precede HF imports (sets HF_HOME)

import argparse
import asyncio
import importlib.util
import json
import urllib.request

REPO      = Path(__file__).resolve().parent.parent
POLARIS   = REPO.parent / "POLARIS" / "polaris_poc" / "src" / "polaris" / "agents" / "llm_clients.py"

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8000/v1")
parser.add_argument("--model", default="local-nla")
args = parser.parse_args()

base = args.url.rstrip("/")
root = base[:-3].rstrip("/") if base.endswith("/v1") else base


def load_polaris_client_module():
    if not POLARIS.exists():
        raise SystemExit(f"POLARIS llm_clients.py not found at {POLARIS}")
    spec = importlib.util.spec_from_file_location("polaris_llm_clients", POLARIS)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get_json(path):
    with urllib.request.urlopen(f"{root}{path}", timeout=30) as r:
        return json.load(r)


# ---------------------------------------------------------------- run
mod = load_polaris_client_module()
print(f"loaded POLARIS client from {POLARIS.relative_to(REPO.parent)}")

health = get_json("/api/health")
print(f"server     {health['model']}  L{health['probe_layer']}  "
      f"{health['dtype']} on {health['device']}")
print(f"max_tokens cap {health['max_new_tokens']}")
print(f"traces     enabled={health['traces']['enabled']}  "
      f"run={health['traces']['run_id']}  written={health['traces']['written']}")
print()

client = mod.create_llm_client(
    provider="openai_compatible",
    api_key="not-needed",      # the local server does not authenticate
    model=args.model,
    base_url=base,
)
print(f"client     {type(client).__name__} -> {base}")

# The message shape POLARIS's agentic reasoner actually builds: a system turn
# establishing the role, then a user turn carrying the telemetry context.
messages = [
    {"role": "system", "content":
     "You are an adaptation controller for a web server system. "
     "Respond with TOOL_CALL: <name> or a JSON action."},
    {"role": "user", "content":
     "Context: response_time=912ms, server_util=0.86, servers=2/3, dimmer=1.0. "
     "Decide the next adaptation action."},
]

text, n_in, n_out = asyncio.run(
    client.generate(messages, temperature=0.3, max_tokens=64)
)

print(f"\ngenerate() -> ({len(text)} chars, in={n_in}, out={n_out})")
print(f"  completion: {text[:200]!r}")

assert isinstance(text, str) and text, "empty completion"
assert n_in  > 0, "prompt_tokens not reported -- POLARIS logs token usage from this"
assert n_out > 0, "completion_tokens not reported"

after = get_json("/api/health")["traces"]
print(f"\ntraces     written {health['traces']['written']} -> {after['written']}"
      f"  (last_error={after['last_error']})")
assert after["written"] > health["traces"]["written"], "no trace was written"

trace_dir = Path(after["dir"])
latest = sorted(trace_dir.glob("*.json"))[-1]
meta   = json.loads(latest.read_text())
print(f"  {latest.name}: {meta['n_tokens']} tokens, "
      f"activations {meta.get('activations_shape')} -> {meta.get('activations_file')}")

assert meta["activations_shape"][0] == meta["n_tokens"], \
    "one activation per token expected"

print("\nPASS: POLARIS's client drives the NLA server and traces are captured.")
