#!/usr/bin/env python3
"""Deterministic stand-in for ``--generate-cmd`` in the structure climb.

The live path pipes an assembled prompt on stdin and sets ``MOCK_ROUND`` to the
current round index. This mock ignores the prompt content for SELECTION (keying
off ``MOCK_ROUND`` so the loop's converge/capped/preservation behavior is
reproducible) but still reads stdin so the subprocess contract matches a real
generator. It emits the canned per-round fixture for the chosen ``--scenario``,
clamping to the last available round so a run past the fixture set is stable.

  --scenario converge      rounds get progressively cleaner; round 2 is clean.
  --scenario capped        every round stays dirty (the loop never wins).
  --scenario preservation  round 1 drops a fact present in round 0 (abort).
"""

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", required=True)
    args = p.parse_args(argv)

    sys.stdin.read()  # honor the subprocess contract; content unused for selection

    env = os.environ.get("MOCK_ROUND", "0")
    index = int(env) if env.isdigit() else 0
    scenario_dir = HERE / args.scenario
    while index >= 0:
        cand = scenario_dir / f"round{index}.md"
        if cand.exists():
            sys.stdout.write(cand.read_text())
            return 0
        index -= 1
    sys.stderr.write(f"mock_generate: no canned round for scenario {args.scenario!r}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
