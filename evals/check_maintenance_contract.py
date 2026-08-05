#!/usr/bin/env python3
"""Run the detailed deterministic matrix behind one maintenance contract."""

from __future__ import annotations

import json
import sys

from _check_support import ROOT, run, load_evals  # noqa: E402,F401
from _check_support import load_contract_examples  # noqa: E402

sys.path.insert(0, str(ROOT / "evals"))

from run_adversarial import _execute


def main() -> int:
    try:
        rows = load_contract_examples("maintenance-examples")
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"maintenance contract setup error: {exc}", file=sys.stderr)
        return 2

    rc, outcomes = _execute(
        rows,
        [],
        strict_xfail=True,
        use_subprocess=False,
        quiet=True,
        compact=True,
        jobs=8,
        timeout=60,
        expected_xfail=set(),
        lane="maintenance-contract",
    )
    unexpected = [
        {"id": case_id, "status": status}
        for case_id, status in outcomes
        if status != "PASS"
    ]
    print(
        "maintenance contract: {}/{} passed unexpected={}".format(
            len(rows) - len(unexpected), len(rows), len(unexpected)
        )
    )
    for row in unexpected:
        print("{} {}".format(row["status"], row["id"]))
    return rc or bool(unexpected)


if __name__ == "__main__":
    raise SystemExit(main())
