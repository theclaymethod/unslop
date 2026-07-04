#!/usr/bin/env python3
"""Check that the gate matrix embedded in evals/CHECKS.md matches --list-gates."""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_adversarial import list_gates  # noqa: E402


def main() -> int:
    doc = (HERE / "CHECKS.md").read_text()
    m = re.search(r"```json\n(.*?)```", doc, re.S)
    if not m:
        print("No ```json block found in CHECKS.md")
        return 1
    documented = json.loads(m.group(1))
    live = list_gates()
    if documented != live:
        doc_ids = [g.get("id") for g in documented]
        live_ids = [g.get("id") for g in live]
        print("CHECKS.md gate matrix is out of sync with --list-gates.")
        print(f"  documented ids: {doc_ids}")
        print(f"  live ids:       {live_ids}")
        print("Regenerate the block: python3 evals/run_adversarial.py --list-gates")
        return 1
    print(f"gate matrix ok: {len(live)} gates documented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
