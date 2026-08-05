#!/usr/bin/env python3
"""Shared helpers for evals/check_*.py scripts.

Every check_*.py that shells out to a scripts/*.py CLI used to carry its own
copy-pasted ``run()`` helper. Only check_contrib.py's copy carried a
``timeout=60`` safety net (a hung scanner subprocess fails the check instead of
hanging the whole suite); the others silently dropped it on copy. This module
is the one place that safety net lives now, so every caller gets it.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSERTION_TYPES = {
    "exit_code", "json", "stderr_not_contains", "stdout_contains",
    "stdout_not_contains", "violation_category_equals",
    "violation_phrase_contains",
}


def run(cmd, timeout=60):
    """Run `cmd` from ROOT, capturing text stdout/stderr, with a timeout."""
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout)


def load_evals():
    """Return the parsed "evals" list from evals/adversarial-evals.json."""
    suite_path = ROOT / "evals" / "adversarial-evals.json"
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    return suite["evals"]


def validate_contract_table(name, table, label="contract table"):
    """Reject vacuous or malformed compact examples before they can pass."""
    examples = table.get("examples")
    expected = table.get("exact_total")
    if table.get("version") != 1 or not isinstance(examples, list):
        raise RuntimeError(f"{label}: expected version 1 example table")
    if expected != len(examples):
        raise RuntimeError(
            f"{label}: exact_total={expected!r}, examples={len(examples)}"
        )
    ids = [row.get("id") for row in examples]
    if any(not isinstance(case_id, str) or not case_id for case_id in ids):
        raise RuntimeError(f"{label}: every example needs a string id")
    if len(ids) != len(set(ids)):
        raise RuntimeError(f"{label}: duplicate example id")
    for row in examples:
        case_id = row["id"]
        assertions = row.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            raise RuntimeError(f"{label}: {case_id} needs nonempty assertions")
        for assertion in assertions:
            if (
                not isinstance(assertion, dict)
                or assertion.get("type") not in ASSERTION_TYPES
            ):
                raise RuntimeError(f"{label}: {case_id} has an invalid assertion")
            kind = assertion["type"]
            if kind == "exit_code" and not isinstance(assertion.get("equals"), int):
                raise RuntimeError(f"{label}: {case_id} exit_code needs integer equals")
            if kind == "json" and (
                not isinstance(assertion.get("path"), str)
                or sum(key in assertion for key in ("equals", "gte", "lte")) != 1
            ):
                raise RuntimeError(f"{label}: {case_id} has an invalid json assertion")
            if kind not in {"exit_code", "json"} and not isinstance(
                assertion.get("value"), str
            ):
                raise RuntimeError(f"{label}: {case_id} {kind} needs string value")
        if name == "scanner-examples":
            if (
                row.get("target") != "script"
                or not isinstance(row.get("category"), str)
                or not isinstance(row.get("stdin"), str)
                or ("xfail" in row and not isinstance(row["xfail"], bool))
                or ("protects" in row and not isinstance(row["protects"], str))
            ):
                raise RuntimeError(f"{label}: malformed scanner example {case_id}")
            detects = any(
                assertion["type"] in {
                    "violation_category_equals", "violation_phrase_contains"
                }
                or (
                    assertion["type"] == "json"
                    and (
                        assertion.get("path", "").startswith("violations.")
                        or (
                            assertion.get("path") == "total_violations"
                            and (
                                assertion.get("gte", 0) >= 1
                                or (
                                    isinstance(assertion.get("equals"), int)
                                    and assertion["equals"] >= 1
                                )
                            )
                        )
                    )
                )
                for assertion in assertions
            )
            if row["category"] in {
                "anti_slop_register", "scanner_detection",
                "scanner_false_negative", "scanner_recall",
            } and not detects:
                raise RuntimeError(f"{label}: {case_id} has no positive detection assertion")
            if row.get("protects") and not any(
                assertion["type"] == "json"
                and assertion.get("path") == "total_violations"
                and assertion.get("equals") == 0
                for assertion in assertions
            ):
                raise RuntimeError(f"{label}: {case_id} protection is not pinned clean")
        elif name == "preservation-examples":
            args = row.get("args")
            payload_args = args[1:] if isinstance(args, list) and args[:1] == ["--strict"] else args
            if (
                not isinstance(args, list)
                or not all(isinstance(arg, str) and arg for arg in args)
                or not isinstance(payload_args, list)
                or len(payload_args) not in {2, 3}
            ):
                raise RuntimeError(f"{label}: malformed preservation example {case_id}")
            preservation_outcome = any(
                assertion["type"] == "exit_code"
                or (
                    assertion["type"] == "json"
                    and assertion.get("path", "").startswith(
                        ("passed", "missing", "preserved", "total_constraints", "warnings")
                    )
                )
                for assertion in assertions
            )
            if not preservation_outcome:
                raise RuntimeError(f"{label}: {case_id} has no preservation outcome assertion")
        elif name == "maintenance-examples":
            command = row.get("command")
            if (
                row.get("target") != "script"
                or not isinstance(row.get("category"), str)
                or not isinstance(row.get("title"), str)
                or not isinstance(command, list)
                or not command
                or not all(isinstance(arg, str) and arg for arg in command)
            ):
                raise RuntimeError(f"{label}: malformed maintenance example {case_id}")
        else:
            raise RuntimeError(f"{label}: unknown contract family {name!r}")
    return examples


def load_contract_examples(name):
    """Load and integrity-check one compact deterministic example table."""
    path = ROOT / "evals" / "fixtures" / "contracts" / f"{name}.json"
    table = json.loads(path.read_text(encoding="utf-8"))
    return validate_contract_table(name, table, str(path))
