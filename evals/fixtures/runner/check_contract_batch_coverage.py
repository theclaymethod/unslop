#!/usr/bin/env python3
"""Prove family compaction cannot swallow new or strengthened eval rows."""

from __future__ import annotations

import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(EVALS))

from run_adversarial import (  # noqa: E402
    _active_contract_ids,
    _batched_pair_row,
    _batched_tool_row,
)
from _check_support import validate_contract_table  # noqa: E402
from eval_groups import REQUIRED_AGGREGATE_ROWS, validate_topology  # noqa: E402


def _rejected(name, table):
    try:
        validate_contract_table(name, table, "fixture")
    except RuntimeError:
        return True
    return False


def main() -> int:
    selected = {"MIMIC-LOOP-CONTRACT-01"}
    exact = {
        "command": ["python3", "evals/check_mimic.py", "--acceptance"],
        "assertions": [{"type": "exit_code", "equals": 0}],
    }
    strengthened = {
        **exact,
        "assertions": [
            {"type": "exit_code", "equals": 0},
            {"type": "stdout_contains", "value": "new evidence"},
        ],
    }
    new_flag = {
        "command": ["python3", "evals/check_mimic.py", "--new-case"],
        "assertions": [{"type": "exit_code", "equals": 0}],
    }
    pair_manifest = {"sample": {"kind": "phrase", "target": "throat_clearing"}}
    pair_exact = {
        "id": "PAIR-NEW-a",
        "command": [
            "python3", "scripts/banned_phrase_scan.py",
            "evals/fixtures/pairs/sample_with.txt",
        ],
        "assertions": [
            {"type": "json", "path": "total_violations", "gte": 1},
            {"type": "violation_category_equals", "value": "throat_clearing"},
        ],
    }
    pair_strengthened = {
        **pair_exact,
        "assertions": pair_exact["assertions"] + [
            {"type": "stdout_contains", "value": "new evidence"}
        ],
    }
    pair_missing = {
        **pair_exact,
        "command": [
            "python3", "scripts/banned_phrase_scan.py",
            "evals/fixtures/pairs/not_in_manifest_with.txt",
        ],
    }
    pair_wrong_directory = {
        **pair_exact,
        "command": [
            "python3", "scripts/banned_phrase_scan.py",
            "tmp/sample_with.txt",
        ],
    }
    pair_wrong_launcher = {
        **pair_exact,
        "command": [
            "python", "scripts/banned_phrase_scan.py",
            "evals/fixtures/pairs/sample_with.txt",
        ],
    }
    active = _active_contract_ids([])
    vacuous_scanner = {
        "version": 1,
        "exact_total": 1,
        "examples": [{
            "id": "X", "target": "script", "category": "scanner_recall",
            "stdin": "studies show", "assertions": [],
        }],
    }
    malformed_preservation = {
        "version": 1,
        "exact_total": 1,
        "examples": [{"id": "Y", "args": [], "assertions": [{"type": "exit_code", "equals": 0}]}],
    }
    irrelevant_scanner = {
        "version": 1,
        "exact_total": 1,
        "examples": [{
            "id": "Z", "target": "script", "category": "scanner_recall",
            "stdin": "studies show",
            "assertions": [{"type": "stdout_not_contains", "value": "impossible sentinel"}],
        }],
    }
    irrelevant_preservation = {
        "version": 1,
        "exact_total": 1,
        "examples": [{
            "id": "W", "args": ["missing-a", "missing-b"],
            "assertions": [{"type": "stdout_not_contains", "value": "Negation count dropped"}],
        }],
    }
    vacuous_maintenance = {
        "version": 1,
        "exact_total": 1,
        "examples": [{
            "id": "M", "target": "script", "category": "robustness",
            "title": "must not pass vacuously", "command": ["definitely-missing"],
            "assertions": [],
        }],
    }
    topology_rows = [
        {"id": case_id, **shape}
        for case_id, shape in REQUIRED_AGGREGATE_ROWS.items()
    ]
    scanner_row = next(
        row for row in topology_rows if row["id"] == "SCANNER-CONTRACT-01"
    )

    ok = (
        _batched_tool_row(exact, selected)
        and not _batched_tool_row(strengthened, selected)
        and not _batched_tool_row(new_flag, selected)
        and not _batched_tool_row(exact, set())
        and _batched_pair_row(pair_exact, {"DOC-08", "PAIR-NEW-a"}, pair_manifest)
        and not _batched_pair_row(
            pair_strengthened, {"DOC-08", "PAIR-NEW-a"}, pair_manifest
        )
        and not _batched_pair_row(pair_missing, {"DOC-08", "PAIR-NEW-a"}, pair_manifest)
        and not _batched_pair_row(
            pair_wrong_directory, {"DOC-08", "PAIR-NEW-a"}, pair_manifest
        )
        and not _batched_pair_row(
            pair_wrong_launcher, {"DOC-08", "PAIR-NEW-a"}, pair_manifest
        )
        and not _batched_pair_row(pair_exact, {"PAIR-NEW-a"}, pair_manifest)
        and active == set()
        and _rejected("scanner-examples", vacuous_scanner)
        and _rejected("preservation-examples", malformed_preservation)
        and _rejected("scanner-examples", irrelevant_scanner)
        and _rejected("preservation-examples", irrelevant_preservation)
        and _rejected("maintenance-examples", vacuous_maintenance)
        and any("missing required aggregate" in error for error in validate_topology(topology_rows[1:]))
        and any(
            "noncanonical shape" in error
            for error in validate_topology([
                *[row for row in topology_rows if row is not scanner_row],
                {**scanner_row, "assertions": [{"type": "exit_code", "equals": 0}]},
            ])
        )
        and any(
            "noncanonical shape" in error
            for error in validate_topology([
                *[row for row in topology_rows if row is not scanner_row],
                {**scanner_row, "target": "skill"},
            ])
        )
    )
    if ok:
        print("contract batch coverage: exact-only fallback ok")
        return 0
    print("contract batch coverage: unsafe filtering", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
