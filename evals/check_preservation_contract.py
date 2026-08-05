#!/usr/bin/env python3
"""Run all preservation fixtures as one table-driven API contract."""

from __future__ import annotations

import json
import sys
import time
from types import SimpleNamespace

from _check_support import ROOT, run, load_evals  # noqa: E402,F401
from _check_support import load_contract_examples  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "evals"))

from run_adversarial import check_assertion  # noqa: E402
from validate_preservation import validate_preservation  # noqa: E402


def _run(row: dict) -> tuple[str, bool, str]:
    args = list(row["args"])
    strict = bool(args and args[0] == "--strict")
    if strict:
        args = args[1:]
    try:
        original = (ROOT / args[0]).read_text()
        transformed = (ROOT / args[1]).read_text()
        constraints = None
        if len(args) > 2:
            constraints = json.loads((ROOT / args[2]).read_text()).get("constraints", [])
    except (IndexError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        proc = SimpleNamespace(
            returncode=2,
            stdout=json.dumps({"error": f"Could not read input: {exc}"}) + "\n",
            stderr="",
        )
    else:
        result = validate_preservation(original, transformed, constraints)
        payload = {
            "passed": result["passed"],
            "total_constraints": result["total_constraints"],
            "preserved": result["preserved"],
            "missing_count": len(result["missing"]),
            "missing": result["missing"],
            "warnings": result["warnings"],
        }
        proc = SimpleNamespace(
            returncode=0 if result["passed"] and not (strict and result["warnings"]) else 1,
            stdout=json.dumps(payload, indent=2) + "\n",
            stderr="",
        )
    checks = [check_assertion(assertion, proc) for assertion in row["assertions"]]
    return (
        row["id"],
        all(passed for passed, _ in checks),
        "; ".join(message for _, message in checks),
    )


def main() -> int:
    try:
        rows = load_contract_examples("preservation-examples")
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"preservation contract setup error: {exc}", file=sys.stderr)
        return 2
    if not rows:
        print("preservation contract contains no examples", file=sys.stderr)
        return 2

    started = time.perf_counter()
    unexpected = []
    for row in rows:
        case_id, ok, detail = _run(row)
        if not ok:
            unexpected.append(f"{case_id}: FAIL; {detail}")
    for problem in unexpected:
        print(problem, file=sys.stderr)
    print(
        f"preservation contract: examples={len(rows)} "
        f"pass={len(rows) - len(unexpected)} unexpected={len(unexpected)} "
        f"elapsed={time.perf_counter() - started:.2f}s"
    )
    return 1 if unexpected else 0


if __name__ == "__main__":
    raise SystemExit(main())
