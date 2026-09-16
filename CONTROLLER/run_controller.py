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
    ReasoningStyle, SwimClient, Trajectory, build_backend,
)

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
    ctrl.add_argument("--policy", choices=["reactive", "reactive2", "llm"], default="reactive")
    ctrl.add_argument("--sla", type=float, default=0.75)
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

    return p.parse_args(argv)


def build_builder(args: argparse.Namespace) -> ContextBuilder:
    return ContextBuilder(
        sla=args.sla,
        period_seconds=int(args.period),
        dimmer_mode=DimmerMode(args.dimmer_mode),
        reasoning=ReasoningStyle(args.reasoning),
        window=args.window,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-7s %(name)-18s %(message)s",
        datefmt="%H:%M:%S",
    )

    client = SwimClient(host=args.host, port=args.port, timeout=args.timeout)

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
            prompt = build_builder(args).build(0, traj)
            print(prompt.text)
            print()
            print("-- options ------------------------------------------")
            for oid, action in prompt.options:
                print(f"  {oid}  {action}")
            print("-- probe offsets ------------------------------------")
            for name, offset in prompt.probes.items():
                print(f"  {name:20} char {offset}")
            return 0

    # -- policy ------------------------------------------------------------
    reactive = ReactivePolicy(sla=args.sla, require_spare=(args.policy != "reactive2"))
    if args.policy in ("reactive", "reactive2"):
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
