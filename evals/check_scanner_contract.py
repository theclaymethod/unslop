#!/usr/bin/env python3
"""Run the stdin scanner matrix as one parallel, table-driven contract."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import os
import sys
import time
from types import SimpleNamespace

from _check_support import ROOT, run, load_evals  # noqa: E402,F401
from _check_support import load_contract_examples  # noqa: E402

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from run_adversarial import check_assertion  # noqa: E402
from scripts.banned_phrase_scan import (  # noqa: E402
    is_probably_english,
    scan_for_violations,
)


EXPECTED_XFAIL: set[str] = set()


def _scanner_result(text: str) -> SimpleNamespace:
    if not text.strip():
        payload = {"error": "No input provided", "violations": []}
        return SimpleNamespace(returncode=1, stdout=json.dumps(payload) + "\n", stderr="")

    violations = scan_for_violations(text)
    if not violations and not is_probably_english(text):
        payload = {"non_english": True, "total_violations": 0, "violations": []}
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload, indent=2) + "\n",
            stderr="note: input appears non-English; scanner declined (English-only).\n",
        )

    categories: dict[str, int] = {}
    by_severity: dict[str, int] = {"hard": 0, "soft": 0}
    for violation in violations:
        category = violation["category"]
        severity = violation["severity"]
        categories[category] = categories.get(category, 0) + 1
        by_severity[severity] = by_severity.get(severity, 0) + 1
    payload = {
        "total_violations": len(violations),
        "by_severity": by_severity,
        "by_category": categories,
        "violations": violations,
    }
    return SimpleNamespace(
        returncode=1 if violations else 0,
        stdout=json.dumps(payload, indent=2) + "\n",
        stderr="",
    )


def _evaluate(row: dict) -> tuple[str, bool, bool, str]:
    result = _scanner_result(row.get("stdin", ""))
    checks = [check_assertion(assertion, result) for assertion in row["assertions"]]
    ok = all(passed for passed, _ in checks)
    detail = "; ".join(message for _, message in checks)
    return row["id"], ok, bool(row.get("xfail")), detail


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--jobs",
        type=int,
        default=min(4, max(1, os.cpu_count() or 1)),
        help="persistent scanner workers (default: up to 4)",
    )
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")

    try:
        rows = load_contract_examples("scanner-examples")
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"scanner contract setup error: {exc}", file=sys.stderr)
        return 2
    if not rows:
        print("scanner contract contains no examples", file=sys.stderr)
        return 2

    started = time.perf_counter()
    workers = min(args.jobs, len(rows))
    if workers == 1:
        results = [_evaluate(row) for row in rows]
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(_evaluate, rows, chunksize=max(1, len(rows) // (workers * 4))))

    unexpected: list[str] = []
    observed_xfail: set[str] = set()
    passed = 0
    for case_id, ok, xfail, detail in results:
        if ok and not xfail:
            passed += 1
        elif not ok and xfail:
            observed_xfail.add(case_id)
        elif ok and xfail:
            unexpected.append(f"{case_id}: XPASS; remove xfail")
        else:
            unexpected.append(f"{case_id}: FAIL; {detail}")

    row_ids = {row["id"] for row in rows}
    missing_xfail = EXPECTED_XFAIL - row_ids
    if missing_xfail:
        unexpected.append(f"missing required XFAIL rows: {sorted(missing_xfail)}")
    expected = EXPECTED_XFAIL
    if observed_xfail != expected:
        unexpected.append(
            f"XFAIL set {sorted(observed_xfail)} != expected {sorted(expected)}"
        )
    for problem in unexpected:
        print(problem, file=sys.stderr)

    elapsed = time.perf_counter() - started
    print(
        f"scanner contract: examples={len(rows)} pass={passed} "
        f"xfail={len(observed_xfail)} unexpected={len(unexpected)} "
        f"workers={workers} elapsed={elapsed:.2f}s"
    )
    return 1 if unexpected else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
