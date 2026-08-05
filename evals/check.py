#!/usr/bin/env python3
"""Run the canonical UNSLOP repository checks once, without duplicate slices."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

from _check_support import ROOT
from eval_groups import CORE_CONTRACT_EXAMPLE_BUDGET


CORE_ADVERSARIAL_COMMAND = [
    "python3", "evals/run_adversarial.py", "--compact", "--jobs", "4",
    "--timeout", "60", "--lane", "core-contract",
]

MAINTENANCE_ADVERSARIAL_COMMAND = [
    "python3", "evals/run_adversarial.py", "--compact", "--jobs", "8",
    "--timeout", "60", "--lane", "maintenance",
]

PHASES = [
    {
        # Keep the long-standing phase id for check.py --list consumers while
        # labeling this honestly as offline contract plumbing.
        "id": "adversarial-suite",
        "command": CORE_ADVERSARIAL_COMMAND,
        "lane": "core-contract",
        "budget": {"max_examples": CORE_CONTRACT_EXAMPLE_BUDGET},
    },
]

MAINTENANCE_PHASES = [
    {
        "id": "maintenance-matrix",
        "command": MAINTENANCE_ADVERSARIAL_COMMAND,
        "lane": "maintenance",
        "budget": {"max_examples": None},
    },
]

BEHAVIORAL_INTEGRITY_PHASES = [
    {
        "id": "shared-benchmark-check",
        "command": ["python3", "evals/build_shared_benchmark.py", "--check"],
    },
    {
        "id": "strict-leakage-validate",
        "command": [
            "skill-benchmark",
            "validate",
            "evals/shared-benchmark.json",
            "--strict-leakage",
        ],
    },
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the canonical deterministic phases as JSON and exit",
    )
    parser.add_argument(
        "--behavioral",
        choices=("tune", "holdout", "holdback"),
        help="run one behavioral split after all deterministic phases pass",
    )
    parser.add_argument(
        "--maintenance",
        action="store_true",
        help="run the bounded deterministic maintenance matrix only",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="run the extended mimic, voice, calibration, and maintenance suite too",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.maintenance and (args.full or args.behavioral):
        raise SystemExit("--maintenance cannot be combined with --full or --behavioral")
    if args.list:
        print(json.dumps({
            "core_contract_budget": CORE_CONTRACT_EXAMPLE_BUDGET,
            "maintenance": MAINTENANCE_PHASES,
            "count": len(PHASES),
            "phases": PHASES,
        }, indent=2))
        return 0

    started = time.perf_counter()
    if args.maintenance:
        phases = [dict(phase) for phase in MAINTENANCE_PHASES]
    else:
        phases = [dict(phase) for phase in PHASES]
    if args.full:
        phases.extend(dict(phase) for phase in MAINTENANCE_PHASES)
        phases.extend(dict(phase) for phase in BEHAVIORAL_INTEGRITY_PHASES)
    elif args.behavioral:
        phases.extend(dict(phase) for phase in BEHAVIORAL_INTEGRITY_PHASES)
    for phase in phases:
        phase_started = time.perf_counter()
        print(f"RUN  {phase['id']}", flush=True)
        try:
            proc = subprocess.run(phase["command"], cwd=ROOT)
        except FileNotFoundError as exc:
            print(f"FAIL {phase['id']}: {exc}", file=sys.stderr)
            return 2
        elapsed = time.perf_counter() - phase_started
        if proc.returncode:
            print(
                f"FAIL {phase['id']} ({elapsed:.2f}s, exit {proc.returncode})",
                file=sys.stderr,
            )
            return proc.returncode
        print(f"OK   {phase['id']} ({elapsed:.2f}s)", flush=True)

    if args.behavioral:
        phase_started = time.perf_counter()
        print(f"RUN  behavioral-{args.behavioral}", flush=True)
        proc = subprocess.run(
            ["evals/run_behavioral.sh", args.behavioral], cwd=ROOT
        )
        elapsed = time.perf_counter() - phase_started
        if proc.returncode:
            print(
                f"FAIL behavioral-{args.behavioral} "
                f"({elapsed:.2f}s, exit {proc.returncode})",
                file=sys.stderr,
            )
            return proc.returncode
        print(f"OK   behavioral-{args.behavioral} ({elapsed:.2f}s)", flush=True)

    print(f"PASS all checks ({time.perf_counter() - started:.2f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
