#!/usr/bin/env python3
"""Edit and patch: is the NLA explanation at the action cue causally faithful?

The RQ2 logic applied to NLA. At P_action (the position the action letter is
read after) the AV's explanation names the letter the model is about to choose
("... requiring the letter "C" to complete ..."). Edit that text to name another
legal option, reconstruct both texts with the AR, and move the model's layer-41
state by the difference the words imply:

    h' = h + alpha * |h| * (unit(AR(E')) - unit(AR(E)))

At alpha = 1 this keeps everything the explanation does not capture
(h - |h| unit(AR(E))) and swaps what it does. Layers 42-61 are then re-run at
that position only (the prefix is cached) and the letter is read as the
controller reads it: the larger of "X" and " X" per option, softmax over the
options, masked to the legal ones. If the words carry the decision, the choice
should move to the letter the edit names.

Directions, each scaled to the norm of the NLA direction at the same alpha, so
that only the direction differs:

``nla``       the edit above.
``meandiff``  mean P_action activation of decisions that chose the target minus
              that of decisions that chose the original action, from the other
              runs (leave-one-run-out); the supervised reference. Skipped when
              either class has fewer than ``--min-class`` decisions elsewhere.
``random``    a random direction (seeded per decision and target); the null.

The edit is exact: the chosen letter is replaced where the explanation names it
as a choice (in quotes, or after "letter", "option", "button", "label", "= ");
explanations that never name it that way are recorded and skipped.

Needs a finished pilot (pilot.py) on the same runs. One GPU, two phases: the AR
reconstructs every original and edited explanation, then the target replays
each decision.

    python edit_patch.py PILOT_DIR -o OUT [--alphas 1 2 4 8] [--limit N]

Output in OUT: edits.jsonl (one row per decision and target, with the edited
text), patched.jsonl (one row per decision, target, direction and alpha, plus
an ``unpatched`` row per decision as the control).
"""

from __future__ import annotations

import argparse
import copy
import gc
import hashlib
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "activations"))

TARGET = "google/gemma-3-27b-it"
LAYER = 41                       # output of block 41, as in nla_pair / pilot
_CUE = r"(?:(?<=[\"'])|(?<=letter )|(?<=option )|(?<=button )|(?<=label )|(?<== ))"


def letter_swap(text: str, old: str, new: str) -> tuple[str, int]:
    """Replace the letter ``old`` where the text names it as a choice."""
    return re.subn(_CUE + re.escape(old) + r"(?![A-Za-z])", new, text)


def unit(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return x / max(float(np.linalg.norm(x)), 1e-12)


def seeded_direction(d: int, *key) -> np.ndarray:
    seed = int.from_bytes(hashlib.sha256(repr(key).encode()).digest()[:8], "little")
    return unit(np.random.default_rng(seed).standard_normal(d))


def letter_of(options: list[list[str]], action: str) -> str | None:
    return next((oid for oid, label in options if label == action), None)


def masked_softmax(logp: dict[str, float], legal: list[str]) -> dict[str, float]:
    m = {k: v for k, v in logp.items() if k in legal}
    if not m:
        return {}
    top = max(m.values())
    z = {k: np.exp(v - top) for k, v in m.items()}
    s = sum(z.values())
    return {k: float(v / s) for k, v in z.items()}


# -- the target model, patched at one layer and position ----------------------
def decoder_layers(model):
    """The language model's block list; the multimodal checkpoint also has a
    vision tower with its own ``layers``, told apart by length."""
    import torch
    n_layers = model.config.get_text_config().num_hidden_layers
    found = [(n, m) for n, m in model.named_modules()
             if isinstance(m, torch.nn.ModuleList) and n.endswith("layers") and len(m) == n_layers]
    if len(found) != 1:
        raise AssertionError(f"expected one decoder layer list, found {[n for n, _ in found]}")
    return found[0][1]


class Patcher:
    """Cache the prompt up to its last token, then re-run the last token with
    an optional vector added to the output of ``layer`` at that position."""

    def __init__(self, model, tok, layer: int = LAYER):
        import torch
        self.torch = torch
        self.model, self.tok = model, tok
        self.dev = model.get_input_embeddings().weight.device
        self.delta = None
        self.seen = None
        layers = decoder_layers(model)
        self.handle = layers[layer].register_forward_hook(self._hook)
        self.letter_ids: dict[str, list[int]] = {}

    def _hook(self, _module, _inputs, output):
        hs = output[0] if isinstance(output, tuple) else output
        if self.delta is not None:
            hs = hs.clone()
            hs[:, -1, :] += self.delta.to(hs.dtype)
        self.seen = hs[0, -1, :].float().cpu().numpy()
        if self.delta is None:
            return None
        return (hs,) + tuple(output[1:]) if isinstance(output, tuple) else hs

    def ids_for(self, letter: str) -> list[int]:
        if letter not in self.letter_ids:
            ids = []
            for form in (letter, " " + letter):
                enc = self.tok(form, add_special_tokens=False)["input_ids"]
                if len(enc) == 1:
                    ids.append(enc[0])
            if not ids:
                raise ValueError(f"no single-token form of {letter!r}")
            self.letter_ids[letter] = ids
        return self.letter_ids[letter]

    def prefix(self, ids: list[int]):
        with self.torch.no_grad():
            self.delta = None
            out = self.model(input_ids=self.torch.tensor([ids[:-1]], device=self.dev), use_cache=True)
        return out.past_key_values

    def last(self, cache, last_id: int, letters: list[str], delta: np.ndarray | None = None
             ) -> tuple[dict[str, float], np.ndarray]:
        """Log-probabilities of each letter's best form, and the layer output
        at the last position (after the patch, if any)."""
        torch = self.torch
        self.delta = None if delta is None else torch.as_tensor(delta, device=self.dev)
        try:
            with torch.no_grad():
                out = self.model(input_ids=torch.tensor([[last_id]], device=self.dev),
                                 past_key_values=copy.deepcopy(cache), use_cache=True)
        finally:
            self.delta = None
        lp = torch.log_softmax(out.logits[0, -1].float(), dim=-1)
        return ({L: max(float(lp[i]) for i in self.ids_for(L)) for L in letters}, self.seen)


# -- phases -------------------------------------------------------------------
def load_pilot(pilot: Path):
    index = [json.loads(l) for l in (pilot / "index.jsonl").read_text().splitlines()]
    expl = [json.loads(l) for l in (pilot / "explanations.jsonl").read_text().splitlines()]
    V = np.load(pilot / "vectors.npy", mmap_mode="r")
    rows = [(k, i, e) for k, (i, e) in enumerate(zip(index, expl))
            if i["source"] == "run" and i["probe"] == "P_action"]
    return rows, V


def build_edits(rows) -> tuple[list[dict], dict[str, int]]:
    edits, skipped = [], defaultdict(int)
    for k, i, e in rows:
        chosen = letter_of(i["options"], i["action"])
        if chosen is None:
            skipped["no letter for the recorded action"] += 1
            continue
        targets = [L for L in i["legal_ids"] if L != chosen]
        named = 0
        for t in targets:
            new, n = letter_swap(e["explanation"], chosen, t)
            if n == 0:
                continue
            named = n
            edits.append({"row": k, "run": i["run"], "period": i["period"], "action": i["action"],
                          "chosen": chosen, "target": t, "replacements": n,
                          "explanation": e["explanation"], "edited": new})
        if not named:
            skipped["explanation never names the chosen letter"] += 1
    return edits, dict(skipped)


def class_means(rows, V) -> tuple[dict, dict]:
    """Per run and action: sum and count of P_action vectors, for
    leave-one-run-out means."""
    sums: dict = defaultdict(lambda: 0.0)
    counts: dict = defaultdict(int)
    for k, i, _ in rows:
        sums[(i["run"], i["action"])] = sums[(i["run"], i["action"])] + np.asarray(V[k], np.float64)
        counts[(i["run"], i["action"])] += 1
    return sums, counts


def loo_mean(sums, counts, run: str, action: str, min_class: int):
    s = [v for (r, a), v in sums.items() if a == action and r != run]
    n = sum(c for (r, a), c in counts.items() if a == action and r != run)
    return (sum(s) / n) if n >= min_class else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pilot", type=Path, help="pilot.py output directory")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--results-root", type=Path, default=Path.home() / "selas-results")
    ap.add_argument("--alphas", type=float, nargs="+", default=[1.0, 2.0, 4.0, 8.0])
    ap.add_argument("--min-class", type=int, default=3)
    ap.add_argument("--limit", type=int, default=None, help="first N decisions (smoke test)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    import torch
    from nla_pair import AR_REPO, Reconstructor
    from render import render_chat

    rows, V = load_pilot(args.pilot)
    if args.limit:
        rows = rows[: args.limit]
    edits, skipped = build_edits(rows)
    print(f"{len(rows)} decisions at P_action, {len(edits)} edits; skipped: {skipped}", flush=True)

    # Phase 1: reconstruct every distinct text.
    t0 = time.time()
    texts = sorted({x for e in edits for x in (e["explanation"], e["edited"])})
    ar = Reconstructor(AR_REPO)
    R = ar.reconstruct(texts)
    del ar
    gc.collect(); torch.cuda.empty_cache()
    rec = {t: unit(R[n]) for n, t in enumerate(texts)}
    for e in edits:
        e["nla_dir_norm"] = float(np.linalg.norm(rec[e["edited"]] - rec[e["explanation"]]))
    (args.out / "edits.jsonl").write_text("".join(json.dumps(e) + "\n" for e in edits))
    print(f"reconstruct: {len(texts)} texts in {time.time() - t0:.0f}s", flush=True)

    # Phase 2: replay each decision with the patches.
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(TARGET)
    model = AutoModelForCausalLM.from_pretrained(TARGET, dtype=torch.bfloat16, device_map="cuda")
    model.eval().requires_grad_(False)
    P = Patcher(model, tok)
    sums, counts = class_means(rows, V)
    by_row = defaultdict(list)
    for e in edits:
        by_row[e["row"]].append(e)
    decisions: dict[str, dict[int, dict]] = {}

    t1 = time.time()
    with (args.out / "patched.jsonl").open("w") as fh:
        for n, (k, i, _) in enumerate(rows):
            if k not in by_row:
                continue
            run = i["run"]
            if run not in decisions:
                f = next(iter(sorted((args.results_root / run).rglob("decisions.jsonl"))))
                decisions[run] = {r["period"]: r for r in map(json.loads, f.read_text().splitlines())}
            r = decisions[run][i["period"]]
            text = render_chat(tok, r["messages"])
            ids = tok(text, add_special_tokens=False)["input_ids"]
            if len(ids) - 1 != i["pos"]:
                raise AssertionError(f"{run} period {i['period']}: P_action at {i['pos']}, "
                                     f"last token at {len(ids) - 1}")
            letters = [oid for oid, _ in i["options"]]
            cache = P.prefix(ids)
            logp, h = P.last(cache, ids[-1], letters)
            dist0 = masked_softmax(logp, i["legal_ids"])
            hn = float(np.linalg.norm(h))
            base = {"run": run, "period": i["period"], "action": i["action"],
                    "chosen": letter_of(i["options"], i["action"])}
            fh.write(json.dumps({**base, "cond": "unpatched", "h_norm": hn,
                                 "h_cos_captured": float(unit(h) @ unit(V[k])),
                                 "dist": dist0, "recorded": i["distribution"]}) + "\n")
            for e in by_row[k]:
                d_nla = rec[e["edited"]] - rec[e["explanation"]]
                mt = loo_mean(sums, counts, run, dict(i["options"])[e["target"]], args.min_class)
                mc = loo_mean(sums, counts, run, i["action"], args.min_class)
                dirs = {"nla": unit(d_nla),
                        "random": seeded_direction(len(h), run, i["period"], e["target"])}
                if mt is not None and mc is not None:
                    dirs["meandiff"] = unit(mt - mc)
                for alpha in args.alphas:
                    size = alpha * hn * float(np.linalg.norm(d_nla))
                    for cond, u in dirs.items():
                        logp, _ = P.last(cache, ids[-1], letters, (size * u).astype(np.float32))
                        dist = masked_softmax(logp, i["legal_ids"])
                        fh.write(json.dumps({**base, "target": e["target"], "cond": cond,
                                             "alpha": alpha, "delta_norm": size,
                                             "replacements": e["replacements"], "dist": dist}) + "\n")
            del cache
            if (n + 1) % 25 == 0:
                print(f"  {n + 1}/{len(rows)} decisions, {time.time() - t1:.0f}s", flush=True)
    print(f"done in {time.time() - t0:.0f}s -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
