#!/usr/bin/env python3
"""Validate canonical rewrite example outputs against shipping gates."""
import re
import subprocess
import sys

from _check_support import ROOT  # noqa: E402

EXAMPLES = ROOT / "references" / "rewrite-examples.md"


def example_outputs(text):
    blocks = re.findall(r"\*\*Output[^:]*:\*\*\n> (?P<output>[^\n]+)", text)
    if not blocks:
        raise RuntimeError("No documented output examples found")
    return [block.strip() for block in blocks]


def run_gate(command, text):
    return subprocess.run(
        command,
        input=text,
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=30,
    )


def main():
    failures = []
    for idx, output in enumerate(example_outputs(EXAMPLES.read_text()), 1):
        for command in (
            ["python3", "scripts/banned_phrase_scan.py"],
            ["python3", "scripts/readability_metrics.py"],
        ):
            proc = run_gate(command, output)
            if proc.returncode != 0:
                failures.append(
                    f"example {idx} failed {' '.join(command)}: {proc.stdout or proc.stderr}"
                )
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("skill examples pass scanner and readability gates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
