#!/usr/bin/env python3
"""
Extract must-preserve constraints from input text.

Identifies facts, names, dates, URLs, numbers that must survive transformation.
Outputs JSON with constraint spans for validation.

Usage:
    python extract_constraints.py < input.txt
    python extract_constraints.py input.txt
    echo "Text here" | python extract_constraints.py
"""

import sys
import re
import json
from typing import TypedDict


class Constraint(TypedDict):
    type: str
    value: str
    start: int
    end: int


PATTERNS: dict[str, str] = {
    # Currency with amounts
    "currency": r"\$[\d,]+\.?\d*[KMBkmb]?(?:\s*(?:million|billion|thousand))?",

    # Percentages
    "percentage": r"\d+\.?\d*%",

    # ISO dates
    "date_iso": r"\d{4}-\d{2}-\d{2}",

    # Quarter dates
    "date_quarter": r"Q[1-4]\s+\d{4}",

    # Natural dates
    "date_natural": r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}",

    # Years (standalone, 1900-2099)
    "year": r"\b(?:19|20)\d{2}\b",

    # Times
    "time": r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm|UTC|PST|EST|CST|MST|GMT)?",

    # Measurements with units
    "measurement": r"\d+\.?\d*\s*(?:ms|s|sec|min|hr|hour|day|week|month|year|KB|MB|GB|TB|PB|kg|g|lb|oz|m|km|mi|ft|in|cm|mm|px|em|rem|%)",

    # Ranges (numeric)
    "range": r"\d+\.?\d*\s*[-–]\s*\d+\.?\d*(?:\s*(?:K|M|B|%|years?|months?|days?))?",

    # URLs
    "url": r"https?://[^\s\)\]\>\"\']+",

    # Email addresses
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",

    # Code references (backticked)
    "code": r"`[^`]+`",

    # Direct quotes (longer than 10 chars)
    "quote": r'"[^"]{10,}"',

    # Version numbers
    "version": r"v?\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9]+)?",

    # API endpoints
    "api_endpoint": r"/(?:api/)?v?\d*/?\w+(?:/\w+)*",

    # Numeric counts with context
    "count": r"\b\d+(?:,\d{3})*\s+(?:users?|customers?|employees?|companies?|teams?|people|engineers?|developers?|items?|products?|orders?|transactions?|requests?|queries?|rows?|records?)\b",
}

# Proper noun patterns (simplified - real implementation would use NER)
PROPER_NOUN_INDICATORS = [
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b",  # Multi-word capitalized (John Smith)
    r"\b[A-Z][a-z]+\s+(?:Inc|Corp|LLC|Ltd|Co)\b\.?",  # Company suffixes
    r"\b(?:Dr|Mr|Ms|Mrs|Prof)\.?\s+[A-Z][a-z]+\b",  # Titles with names
]


def extract_constraints(text: str) -> list[Constraint]:
    """Extract all must-preserve constraints from text."""
    constraints: list[Constraint] = []
    seen_spans: set[tuple[int, int]] = set()

    # Extract pattern-based constraints
    for constraint_type, pattern in PATTERNS.items():
        for match in re.finditer(pattern, text, re.IGNORECASE if constraint_type.startswith("date") else 0):
            span = (match.start(), match.end())
            if span not in seen_spans:
                seen_spans.add(span)
                constraints.append({
                    "type": constraint_type,
                    "value": match.group(),
                    "start": match.start(),
                    "end": match.end()
                })

    # Extract proper nouns (simplified)
    for pattern in PROPER_NOUN_INDICATORS:
        for match in re.finditer(pattern, text):
            span = (match.start(), match.end())
            # Don't add if overlapping with existing constraint
            overlaps = any(
                not (span[1] <= existing[0] or span[0] >= existing[1])
                for existing in seen_spans
            )
            if not overlaps:
                seen_spans.add(span)
                constraints.append({
                    "type": "proper_noun",
                    "value": match.group(),
                    "start": match.start(),
                    "end": match.end()
                })

    # Sort by position
    constraints.sort(key=lambda c: c["start"])

    return constraints


def main() -> None:
    # Read input
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    if not text.strip():
        print(json.dumps({"error": "No input provided", "constraints": []}))
        sys.exit(1)

    constraints = extract_constraints(text)

    output = {
        "input_length": len(text),
        "constraint_count": len(constraints),
        "constraints": constraints
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
