#!/usr/bin/env python3
"""Judge and rewrite explanations with an LLM, for the holistic NLA tests.

Three jobs, each resumable (one JSONL per job in OUT; ids already there are
skipped):

  judge    Which option does each text say the controller is about to choose?
           The judge sees the text and the option list only -- not the state,
           not the decision. Texts: the NLA explanation at the action cue for
           every decision, and the written reasoning where there is one, so
           both kinds of explanation are read by the same reader. A text may
           say "raise the dimmer" without a level, so the judge may answer that
           instead of a letter; agreement is scored by the kind of action (add,
           remove, do nothing, raise or lower the dimmer, the direction taken
           from the dimmer before the decision), and exactly by letter.
  rewrite  Two rewrites of each NLA explanation. ``counterfactual``: edited to
           say the controller will choose the target option (a no-op -> add a
           server; an action -> do nothing), changing what indicates the
           choice and nothing else. ``paraphrase``: the same meaning and the
           same choice in other words (the control for "any rewrite moves the
           activation").
  verify   Judge every rewrite. A counterfactual is usable if it is judged to
           say the target; a paraphrase if it is judged to say what the
           original was judged to say.

After the jobs, OUT/<pilot>/edits.jsonl holds the usable rewrites in
edit_patch.py's --edits format.

The calls go through the Claude Code CLI (``claude -p --model haiku``, the
user's plan), several texts per call with a JSON schema, a few calls at once.

    python judge_rewrite.py PILOT_DIR [PILOT_DIR ...] -o OUT [--jobs judge rewrite verify]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

MODEL = "haiku"
UNCLEAR = "unclear"
RAISE, LOWER = "raise the dimmer (level not stated)", "lower the dimmer (level not stated)"


def describe(label: str) -> str:
    if label == "add_server":
        return "add a server"
    if label == "remove_server":
        return "remove a server"
    if label == "no_op":
        return "do nothing (keep the current configuration)"
    if label.startswith("set_dimmer"):
        return f"set the dimmer to {label.split()[1]}"
    raise ValueError(label)


def option_block(options: list[list[str]]) -> str:
    lines = [f"{oid} = {describe(lab)}" for oid, lab in options]
    return ("At each step the controller picks exactly one of these options:\n"
            + "\n".join(lines)
            + "\n(The dimmer is the fraction of requests served with optional content: a higher "
              "dimmer gives users more content and puts more load on the servers.)")


def judge_system(options) -> str:
    return (
        "You read texts about an automated controller that manages a web application.\n"
        + option_block(options) + "\n\n"
        "Each text is about the moment the controller is about to choose. Some are the "
        "controller's own written reasoning; others are machine-generated descriptions of its "
        "internal state, which can be oddly worded, mention unrelated things, or list several "
        "candidates. For each text, decide which option the text most strongly indicates the "
        "controller is about to choose, judging the text as a whole: what it says the action "
        "is, and any option letter it names as the choice. If it says the dimmer goes up or "
        f'down without fixing a level, answer "{RAISE}" or "{LOWER}". Answer "{UNCLEAR}" only '
        "if the text favours no option over the others. Answer only from the text.")


def rewrite_system(options) -> str:
    return (
        "You edit texts about an automated controller that manages a web application.\n"
        + option_block(options) + "\n\n"
        "Each text is a machine-generated description of the controller's internal state at the "
        "moment it is about to choose; it can be oddly worded. For each text you are given a "
        "target option. Return two versions of the text:\n"
        "counterfactual: the same text, edited so that it indicates the controller is about to "
        "choose the target option. Change every part that indicates which option is chosen -- "
        "the description of the action and any option letter named as the choice -- and leave "
        "everything else word for word.\n"
        "paraphrase: the same text in different words, with exactly the same meaning and the "
        "same indicated choice; keep any option letters as they are.\n"
        "Keep each version about as long as the original and in the same style. Return only "
        "the texts.")


def schema(options, kind: str) -> dict:
    if kind == "judge":
        item = {"type": "object", "properties": {
                    "id": {"type": "integer"},
                    "option": {"type": "string",
                               "enum": [o for o, _ in options] + [RAISE, LOWER, UNCLEAR]}},
                "required": ["id", "option"]}
    else:
        item = {"type": "object", "properties": {
                    "id": {"type": "integer"},
                    "counterfactual": {"type": "string"},
                    "paraphrase": {"type": "string"}},
                "required": ["id", "counterfactual", "paraphrase"]}
    return {"type": "object", "properties": {"items": {"type": "array", "items": item}},
            "required": ["items"]}


def call(system: str, prompt: str, sch: dict, cwd: Path, n_items: int, tries: int = 4) -> dict:
    """One CLI call; the structured output's items by id (1..n_items), or an
    exception. An answer that leaves items out is retried like a failed call."""
    cmd = ["claude", "-p", "--model", MODEL, "--output-format", "json", "--tools", "",
           "--no-session-persistence", "--system-prompt", system,
           "--json-schema", json.dumps(sch)]
    err = None
    for attempt in range(tries):
        try:
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd,
                               timeout=600)
            d = json.loads(p.stdout)
            if d.get("is_error") or not d.get("structured_output"):
                raise RuntimeError(f"{d.get('subtype')}: {str(d.get('result'))[:200]}")
            got = {it["id"]: it for it in d["structured_output"]["items"]}
            missing = [n for n in range(1, n_items + 1) if n not in got]
            if missing:
                raise RuntimeError(f"answer left out items {missing}")
            return got
        except Exception as e:  # noqa: BLE001 -- retried, then re-raised
            err = e
            time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"gave up after {tries} tries: {err}")


class Store:
    """An append-only JSONL keyed by id, safe across threads."""

    def __init__(self, path: Path):
        self.path = path
        self.rows = {}
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.rows[r["id"]] = r
        self.lock = threading.Lock()

    def add(self, rows: list[dict]):
        with self.lock, self.path.open("a") as fh:
            for r in rows:
                self.rows[r["id"]] = r
                fh.write(json.dumps(r) + "\n")


def load_decisions(pilot: Path) -> list[dict]:
    index = [json.loads(l) for l in (pilot / "index.jsonl").read_text().splitlines()]
    expl = [json.loads(l) for l in (pilot / "explanations.jsonl").read_text().splitlines()]
    out = []
    for i, e in zip(index, expl):
        if i["source"] == "run" and i["probe"] == "P_action":
            out.append({"pilot": pilot.name, "run": i["run"], "period": i["period"],
                        "action": i["action"], "options": i["options"],
                        "legal_ids": i["legal_ids"], "nla": e["explanation"],
                        "dimmer": float(i["observation"]["dimmer"]),
                        "reasoning": (i.get("reasoning") or "").strip()})
    return out


def kind_of(answer: str, options, dimmer: float) -> str | None:
    """The kind of action an answer (a letter or a judge category) stands
    for, given the dimmer before the decision."""
    if answer == RAISE:
        return "raise dimmer"
    if answer == LOWER:
        return "lower dimmer"
    label = dict(options).get(answer)
    if label is None:
        return None
    if label.startswith("set_dimmer"):
        level = float(label.split()[1])
        return "raise dimmer" if level > dimmer else "lower dimmer" if level < dimmer else "dimmer unchanged"
    return label


def key(d: dict, kind: str) -> str:
    return f"{d['pilot']}|{d['run']}|{d['period']}|{kind}"


def run_batches(items: list, size: int, workers: int, work) -> int:
    """Run ``work`` on batches of ``items`` in parallel; count failed batches."""
    batches = [items[n:n + size] for n in range(0, len(items), size)]
    failed, done, t0 = 0, 0, time.time()
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(work, b) for b in batches]
        for f in as_completed(futs):
            try:
                f.result()
            except Exception as e:  # noqa: BLE001 -- reported, the job is resumable
                failed += 1
                print(f"  batch failed: {e}", file=sys.stderr, flush=True)
            done += 1
            if done % 10 == 0 or done == len(batches):
                print(f"  {done}/{len(batches)} calls, {time.time() - t0:.0f}s", flush=True)
    return failed


def judge_texts(texts: list[tuple[str, str]], options, store: Store, size: int, workers: int,
                cwd: Path) -> int:
    todo = [(k, t) for k, t in texts if k not in store.rows]
    print(f"judge: {len(todo)} of {len(texts)} texts to do", flush=True)
    system, sch = judge_system(options), schema(options, "judge")

    def work(batch):
        prompt = "\n\n".join(f"Text {n + 1}:\n<<<\n{t}\n>>>" for n, (_, t) in enumerate(batch))
        got = call(system, prompt, sch, cwd, len(batch))
        store.add([{"id": k, "option": got[n + 1]["option"]} for n, (k, _) in enumerate(batch)])

    return run_batches(todo, size, workers, work)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pilots", type=Path, nargs="+")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--jobs", nargs="+", default=["judge", "rewrite", "verify"],
                    choices=["judge", "rewrite", "verify"])
    ap.add_argument("--judge-batch", type=int, default=20)
    ap.add_argument("--rewrite-batch", type=int, default=5)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None, help="first N decisions per pilot (trial)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cwd = args.out          # not the repository: no CLAUDE.md or project memory in the calls

    decs = []
    for p in args.pilots:
        d = load_decisions(p)
        decs += d[: args.limit] if args.limit else d
    layouts = {json.dumps(d["options"]) for d in decs}
    if len(layouts) != 1:
        raise SystemExit(f"expected one option layout, found {len(layouts)}")
    options = decs[0]["options"]
    letter = {lab: oid for oid, lab in options}
    for d in decs:
        d["chosen"] = letter[d["action"]]
        # The counterfactual's option: a no-op is rewritten to add a server (to
        # remove one while a server boots and adding is not allowed); an
        # action to doing nothing.
        if d["action"] != "no_op":
            d["target"] = letter["no_op"]
        else:
            d["target"] = next((letter[a] for a in ("add_server", "remove_server")
                                if letter[a] in d["legal_ids"]), None)
        d["kind"] = kind_of(d["chosen"], options, d["dimmer"])

    judged = Store(args.out / "judgements.jsonl")
    rewrites = Store(args.out / "rewrites.jsonl")

    if "judge" in args.jobs:
        texts = [(key(d, "nla"), d["nla"]) for d in decs]
        texts += [(key(d, "reasoning"), d["reasoning"]) for d in decs if d["reasoning"]]
        judge_texts(texts, options, judged, args.judge_batch, args.workers, cwd)

    if "rewrite" in args.jobs:
        todo = [d for d in decs if key(d, "rewrite") not in rewrites.rows
                and d["target"] is not None]
        print(f"rewrite: {len(todo)} decisions to do", flush=True)
        system, sch = rewrite_system(options), schema(options, "rewrite")

        def work(batch):
            prompt = "\n\n".join(
                f"Text {n + 1} (target option: {d['target']} = {describe(dict(options)[d['target']])}):"
                f"\n<<<\n{d['nla']}\n>>>" for n, d in enumerate(batch))
            got = call(system, prompt, sch, cwd, len(batch))
            rewrites.add([{"id": key(d, "rewrite"), "target": d["target"],
                           "counterfactual": got[n + 1]["counterfactual"].strip(),
                           "paraphrase": got[n + 1]["paraphrase"].strip()}
                          for n, d in enumerate(batch)])

        run_batches(todo, args.rewrite_batch, args.workers, work)

    if "verify" in args.jobs:
        texts = []
        for d in decs:
            r = rewrites.rows.get(key(d, "rewrite"))
            if r:
                texts += [(key(d, "cf"), r["counterfactual"]), (key(d, "para"), r["paraphrase"])]
        judge_texts(texts, options, judged, args.judge_batch, args.workers, cwd)

    # The usable rewrites, per pilot, for edit_patch.py --edits; and a tally.
    tally = Counter()
    by_pilot: dict[str, list[dict]] = {}
    for d in decs:
        split = "no_op" if d["action"] == "no_op" else "action"
        j = judged.rows.get(key(d, "nla"))
        for name, jj in (("nla", j), ("reasoning", judged.rows.get(key(d, "reasoning")))):
            if jj:
                tally[(d["pilot"], split, f"{name} judged: same letter")] += jj["option"] == d["chosen"]
                tally[(d["pilot"], split, f"{name} judged: same kind")] += \
                    kind_of(jj["option"], options, d["dimmer"]) == d["kind"]
                tally[(d["pilot"], split, f"{name} judged: unclear")] += jj["option"] == UNCLEAR
                tally[(d["pilot"], split, f"{name} judged: n")] += 1
        tally[(d["pilot"], split, "decisions")] += 1
        r = rewrites.rows.get(key(d, "rewrite"))
        jc, jp = judged.rows.get(key(d, "cf")), judged.rows.get(key(d, "para"))
        if not (r and jc and jp and j):
            continue
        rows = by_pilot.setdefault(d["pilot"], [])
        base = {"run": d["run"], "period": d["period"], "target": d["target"]}
        if jc["option"] == d["target"]:
            rows.append({**base, "kind": "rewrite", "edited": r["counterfactual"]})
            tally[(d["pilot"], split, "counterfactual usable")] += 1
        if jp["option"] == j["option"]:
            rows.append({**base, "kind": "paraphrase", "edited": r["paraphrase"]})
            tally[(d["pilot"], split, "paraphrase usable")] += 1
    for pilot, rows in by_pilot.items():
        (args.out / pilot).mkdir(exist_ok=True)
        (args.out / pilot / "edits.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    for k in sorted(tally):
        print(" | ".join(k), tally[k])
    (args.out / "tally.json").write_text(json.dumps({" | ".join(k): v for k, v in sorted(tally.items())},
                                                    indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
