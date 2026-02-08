#!/usr/bin/env python3
"""
Validate that all must-preserve constraints survived transformation.

Compares original text constraints against transformed text.
Exit code 0 = all constraints preserved, 1 = missing constraints.

Usage:
    python validate_preservation.py original.txt transformed.txt
    python validate_preservation.py original.txt transformed.txt constraints.json
"""

import sys
import json
import re
from typing import TypedDict

# Import constraint extraction
from extract_constraints import extract_constraints, Constraint


class ValidationResult(TypedDict):
    passed: bool
    total_constraints: int
    preserved: int
    missing: list[Constraint]
    warnings: list[str]


def normalize_value(value: str) -> str:
    """Normalize a constraint value for comparison."""
    # Remove extra whitespace
    normalized = re.sub(r'\s+', ' ', value.strip())
    # Lowercase for comparison (preserve original for display)
    return normalized.lower()


def find_constraint_in_text(constraint: Constraint, text: str) -> bool:
    """Check if a constraint value exists in text."""
    value = constraint["value"]
    normalized_value = normalize_value(value)
    normalized_text = normalize_value(text)

    # Direct match
    if normalized_value in normalized_text:
        return True

    # For numbers, try without formatting differences
    if constraint["type"] in ("currency", "percentage", "count", "measurement"):
        # Extract just the number
        numbers = re.findall(r'[\d,]+\.?\d*', value)
        for num in numbers:
            # Remove commas for comparison
            clean_num = num.replace(",", "")
            if clean_num in text.replace(",", ""):
                return True

    # For dates, try flexible matching
    if constraint["type"].startswith("date"):
        # Try to find year at minimum
        year_match = re.search(r'\d{4}', value)
        if year_match and year_match.group() in text:
            # Year present, check for month/quarter indicators
            return True

    # For quotes, check if core content is present (without surrounding quotes)
    if constraint["type"] == "quote":
        inner = value.strip('"\'')
        if inner.lower() in normalized_text:
            return True

    return False


def validate_preservation(
    original_text: str,
    transformed_text: str,
    constraints: list[Constraint] | None = None
) -> ValidationResult:
    """Validate that all constraints are preserved in transformed text."""

    if constraints is None:
        constraints = extract_constraints(original_text)

    missing: list[Constraint] = []
    warnings: list[str] = []

    for constraint in constraints:
        if not find_constraint_in_text(constraint, transformed_text):
            missing.append(constraint)

    # Generate warnings for near-misses
    for m in missing:
        if m["type"] == "percentage":
            # Check if number exists without %
            num = re.search(r'[\d.]+', m["value"])
            if num and num.group() in transformed_text:
                warnings.append(f"Number {num.group()} found but missing '%' symbol")

    preserved = len(constraints) - len(missing)

    return {
        "passed": len(missing) == 0,
        "total_constraints": len(constraints),
        "preserved": preserved,
        "missing": missing,
        "warnings": warnings
    }


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: validate_preservation.py <original.txt> <transformed.txt> [constraints.json]")
        sys.exit(1)

    # Read original text
    with open(sys.argv[1], 'r') as f:
        original_text = f.read()

    # Read transformed text
    with open(sys.argv[2], 'r') as f:
        transformed_text = f.read()

    # Optionally read pre-computed constraints
    constraints = None
    if len(sys.argv) > 3:
        with open(sys.argv[3], 'r') as f:
            data = json.load(f)
            constraints = data.get("constraints", [])

    result = validate_preservation(original_text, transformed_text, constraints)

    # Output result
    output = {
        "passed": result["passed"],
        "total_constraints": result["total_constraints"],
        "preserved": result["preserved"],
        "missing_count": len(result["missing"]),
        "missing": result["missing"],
        "warnings": result["warnings"]
    }

    print(json.dumps(output, indent=2))

    # Exit with appropriate code
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
