#!/usr/bin/env python3
"""Entry point for the SWIM LLM controller.

Wiring checks, cheapest first -- each needs strictly less than the next:

    ./run_controller.py --probe                 # can we talk to SWIM at all?
    ./run_controller.py --print-prompt          # what does the model actually see?
    ./run_controller.py --policy reactive       # the oracle, no model
    ./run_controller.py --policy llm --backend stub     # the full loop, no GPU
    ./run_controller.py --policy llm --backend openai \\
        --llm-base-url http://localhost:8000/v1 --llm-model local-nla
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from controller import (
    ContextBuilder, ControlLoop, DimmerMode, LLMPolicy, ReactivePolicy,
    ReasoningStyle, SwimClient, Trajectory, build_backend, synthetic_observation,
)
from controller import NullPolicy
from controller.actions import is_legal

ROOT = Path(__file__).resolve().parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="LLM controller for SWIM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    swim = p.add_argument_group("SWIM")
    swim.add_argument("--host", default="localhost")
    swim.add_argument("--port", type=int, default=4242)
    swim.add_argument("--timeout", type=float, default=10.0)

    ctrl = p.add_argument_group("controller")
    ctrl.add_argument("--policy", choices=["reactive", "reactive2", "llm", "null"],
                      default="reactive",
                      help="null never acts -- the control for whether acting helped at all")
    ctrl.add_argument("--sla", type=float, default=0.75)
    ctrl.add_argument("--boot-delay", type=int, default=60, metavar="S",
                      help="seconds a new server takes to boot. SWIM does not "
                           "expose this over the socket, so it has to be told: "
                           "the prompt states it as a constraint, and at the "
                           "published configuration's 180 s a stale 60 would "
                           "understate how long scaling blocks by three periods")
    ctrl.add_argument("--period", type=float, default=60.0)
    ctrl.add_argument("--max-periods", type=int, default=None)
    ctrl.add_argument("--window", type=int, default=5)
    ctrl.add_argument("--dimmer-mode", choices=[m.value for m in DimmerMode],
                      default=DimmerMode.LEVELS.value,
                      help="levels: 5 absolute settings. step: +/- one step, "
                           "matching the reactive baseline's action space.")
    ctrl.add_argument("--dry-run", action="store_true",
                      help="decide and log, but never send an action to SWIM")

    llm = p.add_argument_group("LLM")
    llm.add_argument("--backend", choices=["stub", "openai"], default="stub")
    llm.add_argument("--llm-base-url", default=None)
    llm.add_argument("--llm-model", default=None)
    llm.add_argument("--llm-api-key", default="local")
    llm.add_argument("--reasoning", choices=[r.value for r in ReasoningStyle],
                     default=ReasoningStyle.SCAFFOLD.value)
    llm.add_argument("--temperature", type=float, default=0.7)
    llm.add_argument("--max-reasoning-tokens", type=int, default=200)
    llm.add_argument("--exemplars", type=int, default=None, metavar="N",
                     help="use the first N of the built-in exemplars "
                          "(0 for zero-shot; default: all of them)")
    llm.add_argument("--prompt-format", choices=["chat", "completion"], default="chat",
                     help="chat uses system/user/assistant turns, which is the format "
                          "these instruction-tuned checkpoints were post-trained on and "
                          "the one the released NLA pairs saw. completion is the earlier "
                          "flat few-shot form, kept so older runs remain reproducible.")

    out = p.add_argument_group("output")
    out.add_argument("--run-dir", default=str(ROOT / "runs"))
    out.add_argument("--run-id", default=None)
    out.add_argument("--log-level", default="INFO",
                     choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    modes = p.add_argument_group("one-shot modes")
    modes.add_argument("--probe", action="store_true",
                       help="read SWIM once, print the observation, exit")
    modes.add_argument("--print-prompt", action="store_true",
                       help="read SWIM once, print the prompt the model would see, exit")
    modes.add_argument("--check-backend", action="store_true",
                       help="score one synthetic decision against the LLM backend "
                            "and exit. Needs no SWIM -- run this before starting the "
                            "simulation, not after.")

    return p.parse_args(argv)


def build_builder(args: argparse.Namespace) -> ContextBuilder:
    return ContextBuilder(
        sla=args.sla,
        period_seconds=int(args.period),
        dimmer_mode=DimmerMode(args.dimmer_mode),
        reasoning=ReasoningStyle(args.reasoning),
        boot_delay=args.boot_delay,
        window=args.window,
        # A prefix of the bank rather than a separate set, so that a sweep over
        # exemplar count varies the count and nothing else. The builder picks
        # which bank -- scaffolded or free-form -- from the reasoning style, so
        # the count is passed rather than the slice.
        n_exemplars=args.exemplars,
    )


def check_backend(args: argparse.Namespace) -> int:
    """Exercise the model end to end on a synthetic state, with no simulator.

    SWIM is the only component with a clock: once it starts, its 105 minutes of
    wall time run whether or not anything is controlling it. So the endpoint is
    proved first, on a state invented here, and SWIM is started only afterwards.
    """
    import time

    backend = build_backend(
        args.backend, base_url=args.llm_base_url, model=args.llm_model,
        api_key=args.llm_api_key,
    )
    builder = build_builder(args)
    obs = synthetic_observation()
    traj = Trajectory(window=args.window)
    traj.record_observation(0, obs)

    policy = LLMPolicy(
        backend=backend, builder=builder, dimmer_mode=DimmerMode(args.dimmer_mode),
        max_reasoning_tokens=args.max_reasoning_tokens, temperature=args.temperature,
        chat=(args.prompt_format == "chat"),
    )

    print(f"format       {args.prompt_format}")
    print(f"backend      {backend.name}"
          + (f" -> {args.llm_base_url} ({args.llm_model})" if args.llm_base_url else ""))
    print(f"state        synthetic: rt={obs.avg_rt:.3f}s util={obs.total_utilization:.2f} "
          f"servers={obs.active_servers}/{obs.max_servers} dimmer={obs.dimmer:.2f}")

    started = time.perf_counter()
    result = policy(0, obs, traj)
    elapsed = time.perf_counter() - started

    if result.policy.endswith("fallback"):
        print(f"\nFAILED   the backend did not answer: {result.notes}")
        print("         the reactive fallback was used, so a real run would adapt")
        print("         without the model. Fix this before starting SWIM.")
        return 1

    if result.messages:
        print(f"\nprompt       {len(result.messages)} chat turns "
              f"({sum(len(m['content']) for m in result.messages)} chars), "
              f"{len(result.options)} options")
    else:
        print(f"\nprompt       {len(result.prompt or '')} chars, "
              f"{len(result.options)} options")
    if result.reasoning is not None:
        text = result.reasoning.strip()
        print(f"reasoning    {len(text)} chars")
        for line in text.splitlines()[:6]:
            print(f"  | {line}")
    print(f"\nlatency      {elapsed:.2f}s"
          + ("   WARNING: exceeds the 60s period" if elapsed > 60 else ""))

    fallback = getattr(backend, "last_fallback_ids", None)
    if fallback is None:
        pass                      # backend does not do top-k scoring (e.g. the stub)
    elif fallback:
        print(f"echo fallback used for {fallback} -- these were absent from the "
              f"endpoint's top-{getattr(backend, 'top_logprobs', '?')}; each costs "
              f"an extra round trip")
    else:
        print("echo fallback not needed: every option was in the endpoint's top-k")

    print("\naction distribution   (* = legal this period)")
    by_id = dict(builder.options_for(obs))
    for oid, label in builder.legend_entries(builder.options_for(obs)):
        raw = result.raw_distribution.get(oid, 0.0)
        masked = result.distribution.get(oid)
        mark = "*" if is_legal(by_id[oid], obs) else " "
        chosen = "  <-- chosen" if by_id[oid] == result.action else ""
        masked_s = f"{masked:.4f}" if masked is not None else "  masked"
        print(f"  {mark} {oid}  {label:<26} raw={raw:.4f}  legal={masked_s}{chosen}")

    print(f"\nOK       chose {result.action}. SWIM can be started now.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-7s %(name)-18s %(message)s",
        datefmt="%H:%M:%S",
    )

    client = SwimClient(host=args.host, port=args.port, timeout=args.timeout)

    # -- backend check: deliberately before any SWIM contact ---------------
    if args.check_backend:
        return check_backend(args)

    # -- one-shot modes ----------------------------------------------------
    if args.probe or args.print_prompt:
        with client:
            obs = client.sense()
            if args.probe:
                for key, value in obs.as_dict().items():
                    print(f"{key:20} {value}")
                return 0
            traj = Trajectory(window=args.window)
            traj.record_observation(0, obs)
            builder = build_builder(args)
            if args.prompt_format == "chat":
                messages, options = builder.build_messages(0, traj)
                for m in messages:
                    print(f"----- {m['role']} " + "-" * (58 - len(m['role'])))
                    print(m["content"])
                print("-" * 64)
                print("(the model generates the next assistant turn; it is then re-sent")
                print(" with 'Action:' appended, and one token is scored there)")
            else:
                prompt = builder.build(0, traj)
                print(prompt.text)
                options = prompt.options
                print("\n-- probe offsets ------------------------------------")
                for name, offset in prompt.probes.items():
                    print(f"  {name:20} char {offset}")
            print("\n-- options ------------------------------------------")
            for oid, action in options:
                print(f"  {oid}  {action}")
            return 0

    # -- policy ------------------------------------------------------------
    reactive = ReactivePolicy(sla=args.sla, require_spare=(args.policy != "reactive2"))
    if args.policy == "null":
        policy = NullPolicy()
    elif args.policy in ("reactive", "reactive2"):
        policy = reactive
    else:
        backend = build_backend(
            args.backend,
            base_url=args.llm_base_url,
            model=args.llm_model,
            api_key=args.llm_api_key,
        )
        policy = LLMPolicy(
            backend=backend,
            builder=build_builder(args),
            dimmer_mode=DimmerMode(args.dimmer_mode),
            max_reasoning_tokens=args.max_reasoning_tokens,
            temperature=args.temperature,
            fallback=ReactivePolicy(sla=args.sla),
            chat=(args.prompt_format == "chat"),
        )

    run_id = args.run_id or datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S")
    loop = ControlLoop(
        client=client,
        policy=policy,
        trajectory=Trajectory(window=args.window),
        run_dir=Path(args.run_dir) / run_id,
        run_id=run_id,
        period_seconds=args.period,
        max_periods=args.max_periods,
        shadow=reactive,
        dry_run=args.dry_run,
    )
    loop.install_signal_handlers()

    with client:
        loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
