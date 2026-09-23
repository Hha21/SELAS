#!/usr/bin/env python3
"""Write the run list for the built-in baseline campaign.

Fixed before any result is seen, so neither trace nor start state is chosen
after the fact: both traces, both starting pools, both built-in managers, ten
seeds each. Plus the one run that reproduces SWIM's published reactive result
(ClarkNet, 180 s boot, 12 servers starting from 3, 10 levels, seed-set 0,
utility -5254.019030358571), which is the check that everything below it is
measured the way SWIM's own results were.
"""

TRACES = {"worldcup": 3, "clarknet": 8}     # run index -> trace at 180 s boot
CONFIGS = ("Reactive", "Reactive2")
INITIAL = (1, 3)
SEEDS = range(1, 11)
MAX_SERVERS, LEVELS = 12, 10

print("# label config run seed initialServers maxServers levels")
print("repro_published Reactive 8 0 3 12 10")
for config in CONFIGS:
    for trace, run in TRACES.items():
        for init in INITIAL:
            for seed in SEEDS:
                print(f"{config}_{trace}_i{init}_s{seed:02d} {config} {run} {seed} "
                      f"{init} {MAX_SERVERS} {LEVELS}")
