#!/usr/bin/env python3
"""
Check change percentage between original and transformed text.

Flags if >40% of words changed (may indicate over-editing).

Usage:
    python diff_check.py original.txt transformed.txt
"""

import sys
import json
import re
from difflib import SequenceMatcher
from typing import TypedDict


class DiffResult(TypedDict):
    original_word_count: int
    transformed_word_count: int
    similarity_ratio: float
    change_percentage: float
    words_added: int
    words_removed: int
    words_changed: int
    excessive_change: bool
    flags: list[str]


def split_words(text: str) -> list[str]:
    """Split text into words for comparison."""
    # Normalize whitespace and split
    text = re.sub(r'[^\w\s]', ' ', text.lower())
    return text.split()


def calculate_diff(original: str, transformed: str) -> DiffResult:
    """Calculate difference metrics between two texts."""
    original_words = split_words(original)
    transformed_words = split_words(transformed)

    # Use SequenceMatcher for word-level diff
    matcher = SequenceMatcher(None, original_words, transformed_words)
    similarity = matcher.ratio()

    # Count operations
    words_added = 0
    words_removed = 0
    words_changed = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            words_changed += max(i2 - i1, j2 - j1)
        elif tag == 'delete':
            words_removed += i2 - i1
        elif tag == 'insert':
            words_added += j2 - j1

    # Change percentage (relative to original)
    total_changes = words_added + words_removed + words_changed
    change_percentage = (
        (total_changes / len(original_words) * 100)
        if original_words else 0
    )

    # Flags
    flags: list[str] = []
    excessive = False

    if change_percentage > 40:
        flags.append(f"Excessive change ({change_percentage:.1f}% > 40% threshold)")
        excessive = True

    if len(transformed_words) < len(original_words) * 0.3:
        flags.append("Transformed text is less than 30% of original length")
        excessive = True

    if len(transformed_words) > len(original_words) * 1.5:
        flags.append("Transformed text is 50%+ longer than original")

    # Length change ratio
    length_ratio = len(transformed_words) / len(original_words) if original_words else 0
    if length_ratio < 0.5:
        flags.append(f"Significant condensation ({length_ratio:.0%} of original)")
    elif length_ratio > 1.2:
        flags.append(f"Text expanded ({length_ratio:.0%} of original)")

    return {
        "original_word_count": len(original_words),
        "transformed_word_count": len(transformed_words),
        "similarity_ratio": round(similarity, 3),
        "change_percentage": round(change_percentage, 1),
        "words_added": words_added,
        "words_removed": words_removed,
        "words_changed": words_changed,
        "excessive_change": excessive,
        "flags": flags
    }


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: diff_check.py <original.txt> <transformed.txt>")
        sys.exit(1)

    # Read original
    with open(sys.argv[1], 'r') as f:
        original = f.read()

    # Read transformed
    with open(sys.argv[2], 'r') as f:
        transformed = f.read()

    result = calculate_diff(original, transformed)
    print(json.dumps(result, indent=2))

    # Exit with 1 if excessive change
    sys.exit(1 if result["excessive_change"] else 0)


if __name__ == "__main__":
    main()
