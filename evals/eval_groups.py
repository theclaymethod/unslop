"""Small gate topology for the larger table of regression examples.

An eval row is evidence inside one gate; it is not itself a top-level product
gate.  Keep this module declarative so adding a new family requires one obvious
classification decision instead of another command in the canonical loop.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


GATE_ORDER = (
    "core-outcome",
    "deterministic-safety",
    "integrity-and-tools",
    "behavioral",
)

# Core-contract plumbing checks are intentionally small and stable. They prove
# that the offline runner, scorer, evidence, and acceptance interfaces agree;
# only a live paired benchmark can establish product quality.
CORE_CONTRACT_GATE = "core-outcome"
CORE_CONTRACT_EXAMPLE_BUDGET = 5
MAINTENANCE_GATES = (
    "deterministic-safety",
    "integrity-and-tools",
)
LANE_ORDER = ("core-contract", "maintenance", "behavioral")
GATE_LANES = {
    CORE_CONTRACT_GATE: "core-contract",
    **{gate: "maintenance" for gate in MAINTENANCE_GATES},
    "behavioral": "behavioral",
}
REQUIRED_AGGREGATE_ROWS = {
    "MAINTENANCE-CONTRACT-01": {
        "target": "script",
        "category": "contract_batch",
        "command": ["python3", "evals/check_maintenance_contract.py"],
        "assertions": [
            {"type": "exit_code", "equals": 0},
            {
                "type": "stdout_contains",
                "value": "maintenance contract: 11/11 passed",
            },
            {"type": "stdout_contains", "value": "unexpected=0"},
        ],
    },
    "COMPLEXITY-BUDGET-01": {
        "target": "script",
        "category": "complexity_budget",
        "command": ["python3", "evals/check_complexity_budget.py"],
        "assertions": [
            {"type": "exit_code", "equals": 0},
            {"type": "stdout_contains", "value": "executable examples <= 80"},
            {
                "type": "stdout_contains",
                "value": "expanded outcome predicates <= 400",
            },
        ],
    },
    "SCANNER-CONTRACT-01": {
        "target": "script",
        "category": "scanner_detection",
        "command": ["python3", "evals/check_scanner_contract.py"],
        "assertions": [
            {"type": "exit_code", "equals": 0},
            {"type": "stdout_contains", "value": "scanner contract:"},
            {"type": "stdout_contains", "value": "unexpected=0"},
        ],
    },
    "PRES-CONTRACT-01": {
        "target": "script",
        "category": "fact_preservation",
        "command": ["python3", "evals/check_preservation_contract.py"],
        "assertions": [
            {"type": "exit_code", "equals": 0},
            {"type": "stdout_contains", "value": "preservation contract:"},
            {"type": "stdout_contains", "value": "unexpected=0"},
        ],
    },
}

SAFETY_PREFIXES = frozenset(
    {
        "AS", "DET", "ENC", "EXT", "FN", "FP", "LANG", "OWNER",
        "PAIR", "PAIRM", "PRES", "QE", "REC", "REGX", "ROB", "SCANNER",
        "SEM", "SIL", "SPAN", "STRUCT",
    }
)

TOOLS_PREFIXES = frozenset(
    {
        "BEHAVIOR", "CACHE", "CAL", "CARD", "CLIMB", "CONTRIB", "DOC",
        "COMPLEXITY", "HARV", "MAINTENANCE", "MIMIC", "PARITY", "RUN", "SLUG", "SUGG",
        "VOICE", "WIKI",
    }
)


def _prefix(case_id: str) -> str:
    return case_id.split("-", 1)[0]


def classify_eval(row: Mapping[str, Any]) -> str:
    """Return the one top-level gate containing *row*, or raise clearly."""
    case_id = row.get("id")
    target = row.get("target")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("eval row has no valid id")
    if target == "skill":
        return "behavioral"
    if target != "script":
        raise ValueError(f"{case_id}: unknown target {target!r}")
    if case_id == "DOC-09" or _prefix(case_id) == "CORE":
        return "core-outcome"
    if case_id == "DOC-08":
        return "deterministic-safety"
    if case_id == "SPAN-03":
        return "integrity-and-tools"
    prefix = _prefix(case_id)
    if prefix in SAFETY_PREFIXES:
        return "deterministic-safety"
    if prefix in TOOLS_PREFIXES:
        return "integrity-and-tools"
    raise ValueError(f"{case_id}: unclassified eval prefix {prefix!r}")


def select_group(rows: Iterable[Mapping[str, Any]], gate: str) -> list[Mapping[str, Any]]:
    if gate not in GATE_ORDER:
        raise ValueError(f"unknown eval gate {gate!r}")
    return [row for row in rows if classify_eval(row) == gate]


def select_lane(rows: Iterable[Mapping[str, Any]], lane: str) -> list[Mapping[str, Any]]:
    """Return rows in an explicit core-contract, maintenance, or behavioral lane."""
    if lane not in LANE_ORDER:
        raise ValueError(f"unknown eval lane {lane!r}")
    return [row for row in rows if GATE_LANES[classify_eval(row)] == lane]


def validate_core_contract_budget(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Reject accidental growth of the core-contract plumbing gate.

    The five examples are distinct interface regressions. Spent-corpus
    validators and maintenance rows remain separate and are constrained by the
    expanded atomic budget.
    """
    core = [row for row in rows if classify_eval(row) == CORE_CONTRACT_GATE]
    if len(core) == CORE_CONTRACT_EXAMPLE_BUDGET:
        return []
    return [
        f"{CORE_CONTRACT_GATE}: expected exactly {CORE_CONTRACT_EXAMPLE_BUDGET} "
        f"core-contract examples, found {len(core)}"
    ]


def validate_topology(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    counts = {gate: 0 for gate in GATE_ORDER}
    for row in rows:
        case_id = row.get("id")
        if isinstance(case_id, str):
            if case_id in seen:
                errors.append(f"duplicate eval id {case_id}")
            seen.add(case_id)
        try:
            counts[classify_eval(row)] += 1
        except ValueError as exc:
            errors.append(str(exc))
    for gate, count in counts.items():
        if count == 0:
            errors.append(f"empty eval gate {gate}")
    by_id = {row.get("id"): row for row in rows}
    for case_id, shape in REQUIRED_AGGREGATE_ROWS.items():
        row = by_id.get(case_id)
        if row is None:
            errors.append(f"missing required aggregate {case_id}")
        elif any(row.get(field) != value for field, value in shape.items()):
            errors.append(f"required aggregate {case_id} has noncanonical shape")
    return errors
