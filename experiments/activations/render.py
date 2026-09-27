"""Rebuild the exact token sequence a chat-format decision was scored on, and
find the positions worth explaining in it.

String manipulation only (no torch), so it can be tested without a model and
shared by capture.py and the NLA pilot. The failure mode is silent: a probe off
by one token still yields activations and explanations, and every number
downstream is quietly about the wrong position.
"""

from __future__ import annotations


SCAFFOLD_FIELDS = ("SLA", "Capacity", "Trend", "Therefore")
ACTION_CUE = "Action:"


def render_chat(tok, messages: list[dict]) -> str:
    """Rebuild the exact string the server scored, from the recorded messages.

    Built as ``template(all but the final assistant turn, add_generation_prompt)
    + that turn's content`` rather than by handing the whole list to the
    template. That is what `continue_final_message` does server-side -- open the
    assistant turn, then place our text inside it -- but done explicitly, so it
    does not depend on a template flag behaving identically across transformers
    versions. The alternative, rendering the final assistant turn normally,
    appends an end-of-turn marker that the scored sequence does not contain, and
    would shift every probe position by a token.
    """
    head = tok.apply_chat_template(messages[:-1], tokenize=False,
                                   add_generation_prompt=True)
    return head + messages[-1]["content"]


def locate_probes(rendered: str, messages: list[dict]) -> dict[str, int]:
    """Character offsets of the positions worth explaining.

    Recomputed here rather than carried from the controller: in chat form the
    controller never sees the rendered string, so offsets it emitted would be
    into a different text.
    """
    probes: dict[str, int] = {}
    live_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), None)
    if live_user:
        idx = rendered.rfind(live_user)
        if idx != -1:
            probes["P0_state_end"] = idx + len(live_user)

    tail_start = len(rendered) - len(messages[-1]["content"])
    # The model's own turn opened, nothing of the reasoning yet: the last
    # position before it writes anything.
    probes["P0_turn"] = tail_start
    for name in SCAFFOLD_FIELDS:
        marker = f"\n  {name}:"
        idx = rendered.find(marker, tail_start)
        if idx == -1:
            continue
        end = rendered.find("\n", idx + len(marker))
        probes[f"P_{name.lower()}"] = end if end != -1 else len(rendered)

    if rendered.rstrip().endswith(ACTION_CUE):
        probes["P_action"] = len(rendered)
    return probes


def probe_token_indices(offsets: list[tuple[int, int]], probes_char: dict[str, int]) -> dict[str, int]:
    """Map character offsets to the token that ends there.

    A probe at offset ``off`` explains the text ``rendered[:off]``, so its token
    is the last one starting before ``off`` -- the one holding character
    ``off - 1``. Taken from the tokenizer's offset mapping of the full sequence
    rather than by re-tokenising the prefix, which can split differently at the
    cut.
    """
    out = {}
    for name, off in probes_char.items():
        idx = [i for i, (a, b) in enumerate(offsets) if a < off and b > a]
        if idx:
            out[name] = idx[-1]
    return out

