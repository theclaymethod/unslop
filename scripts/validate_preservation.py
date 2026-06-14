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


_MAGNITUDES = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "million": 1e6,
    "b": 1e9, "billion": 1e9,
}

_MONTHS = [
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
]


def normalize_value(value: str) -> str:
    """Normalize a constraint value for comparison."""
    # Remove extra whitespace
    normalized = re.sub(r'\s+', ' ', value.strip())
    # Lowercase for comparison (preserve original for display)
    return normalized.lower()


def parse_money(token: str) -> float | None:
    """Parse a currency token into an absolute amount, honoring magnitude words.

    '$47.3M' and '$47.3 million' -> 47_300_000; '$47.3 billion' -> 47_300_000_000.
    Magnitude is part of the fact, so the two must not compare equal.
    """
    m = re.search(
        r'([\d,]+\.?\d*)\s*(k|m|b|thousand|million|billion)?',
        token.lower().replace("$", ""),
    )
    if not m or not m.group(1).strip(","):
        return None
    amount = float(m.group(1).replace(",", ""))
    if m.group(2):
        amount *= _MAGNITUDES[m.group(2)]
    return amount


def _numbers_match_exactly(value: str, text: str, pattern: str) -> bool:
    """True iff the numeric value appears as a whole quantity in text.

    Guards against the substring trap where '12' is 'found' inside '120'.
    """
    want = re.findall(r'\d+\.?\d*', value)
    have = set(re.findall(pattern, text.lower()))
    return all(num in have for num in want) and bool(want)


def find_constraint_in_text(constraint: Constraint, text: str) -> bool:
    """Check if a constraint value exists in text."""
    value = constraint["value"]
    ctype = constraint["type"]
    normalized_value = normalize_value(value)
    normalized_text = normalize_value(text)

    # Direct match
    if normalized_value in normalized_text:
        return True

    # Currency: compare absolute amounts so a magnitude swap (M -> billion) fails.
    if ctype == "currency":
        target = parse_money(value)
        if target is None:
            return False
        for token in re.findall(
            r'\$?[\d,]+\.?\d*\s*(?:k|m|b|thousand|million|billion)?', text, re.IGNORECASE
        ):
            amount = parse_money(token)
            if amount is not None and abs(amount - target) < 0.01:
                return True
        return False

    # Percentage: require an exact numeric match (12% != 120%).
    if ctype == "percentage":
        return _numbers_match_exactly(value, text, r'(\d+\.?\d*)\s*(?:%|percent)')

    # Other quantities: match digits, comma-insensitive, but as whole tokens.
    if ctype in ("count", "measurement", "number"):
        for num in re.findall(r'[\d,]+\.?\d*', value):
            clean_num = num.replace(",", "")
            if re.search(r'(?<![\d.])' + re.escape(clean_num) + r'(?![\d.])',
                         text.replace(",", "")):
                return True
        return False

    # Dates: the year alone is not enough — a changed month is a changed fact.
    if ctype.startswith("date"):
        year_match = re.search(r'\d{4}', value)
        if not (year_match and year_match.group() in text):
            return False
        low = value.lower()
        month = next((mo for mo in _MONTHS if mo[:3] in low), None)
        if month and month[:3] not in text.lower():
            return False
        quarter = re.search(r'q[1-4]', low)
        if quarter and quarter.group() not in text.lower():
            return False
        return True

    # For quotes, check if core content is present (without surrounding quotes)
    if constraint["type"] == "quote":
        inner = value.strip('"\'')
        if inner.lower() in normalized_text:
            return True

    return False


_NEGATION_RE = re.compile(
    r"\b(?:not|never|no|cannot|can't|won't|don't|doesn't|didn't|isn't|aren't|"
    r"wasn't|weren't|without|neither|nor|none|fails?\s+to|rather\s+than)\b", re.I)
_SCOPE_RE = re.compile(
    r"\b(?:most|all|none|every|each|some|few|several|majority|minority|only|"
    r"always|usually|typically|rarely|approximately|roughly|about|nearly)\b", re.I)
_CONDITIONAL_RE = re.compile(
    r"\b(?:if|unless|provided\s+that|only\s+if|assuming|given\s+that|"
    r"in\s+the\s+event|contingent\s+on)\b", re.I)


def semantic_drift_warnings(original: str, transformed: str) -> list[str]:
    """Warn when meaning-bearing words present in the original vanish in the rewrite."""
    out: list[str] = []
    o, t = original.lower(), transformed.lower()

    on, tn = len(_NEGATION_RE.findall(o)), len(_NEGATION_RE.findall(t))
    if on > tn:
        out.append(
            f"Negation count dropped {on}->{tn}. Verify no claim was inverted or "
            "weakened (e.g. 'does not support' -> 'supports').")

    missing_scope = sorted({w for w in _SCOPE_RE.findall(o)} - {w for w in _SCOPE_RE.findall(t)})
    for w in missing_scope:
        out.append(f"Scope/precision word '{w}' not in output. Verify the claim's scope is unchanged.")

    oc, tc = len(_CONDITIONAL_RE.findall(o)), len(_CONDITIONAL_RE.findall(t))
    if oc > tc:
        out.append(
            f"Conditional count dropped {oc}->{tc}. Verify a conditional claim "
            "wasn't turned into an unconditional one.")

    return out


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

    # Semantic drift warnings. These are NOT numbers/names — they are the
    # meaning-bearing words (negations, scope, conditionals) that the skill's
    # de-hedging rules are most likely to delete and that pure fact-matching
    # cannot see. Surfaced as warnings so the rewrite gets a human re-check;
    # de-slopping legitimately removes some, so they don't hard-fail on their own.
    warnings.extend(semantic_drift_warnings(original_text, transformed_text))

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

    # Read inputs
    try:
        with open(sys.argv[1], 'r') as f:
            original_text = f.read()
        with open(sys.argv[2], 'r') as f:
            transformed_text = f.read()
    except OSError as e:
        print(json.dumps({"error": f"Could not read input: {e}"}))
        sys.exit(2)

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
