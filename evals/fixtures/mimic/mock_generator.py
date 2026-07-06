#!/usr/bin/env python3
"""Deterministic stand-in for ``--generate-cmd`` in the mimic refine loop.

The live path pipes an assembled prompt on stdin and sets ``MOCK_ITER`` to the
current iteration index in the environment. This mock ignores the prompt's
content for candidate SELECTION (keying off ``MOCK_ITER`` so the loop's
accept/patience/stop behavior is reproducible), but still reads stdin so the
subprocess contract matches a real generator. When ``MOCK_ITER`` is absent it
falls back to a stable hash of the prompt. It emits the canned ``accept`` fixture
candidate for that iteration, so the live path reproduces the DEV-improvement
trajectory the dry-run ``--acceptance`` row pins.
"""

import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ACCEPT = ROOT / "evals" / "fixtures" / "mimic" / "candidates" / "accept"


def iteration_index(prompt):
    env = os.environ.get("MOCK_ITER")
    if env is not None and env.isdigit():
        return int(env)
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return int(digest, 16) % 3


def main():
    prompt = sys.stdin.read()  # honor the subprocess contract; content unused
    index = iteration_index(prompt)
    # Clamp to the last available canned iteration.
    while index >= 0:
        cand = ACCEPT / f"iter{index}" / "cand01.md"
        if cand.exists():
            sys.stdout.write(cand.read_text())
            return 0
        index -= 1
    sys.stderr.write("mock_generator: no canned candidate found\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
