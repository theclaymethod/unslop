#!/usr/bin/env python3
"""
Scan text for AI-isms and banned phrases.

Checks against taboo phrases list and returns violations with line numbers.
Provides suggested replacements where available.

Usage:
    python banned_phrase_scan.py < input.txt
    python banned_phrase_scan.py input.txt
    python banned_phrase_scan.py input.txt --taboo-file custom_taboo.md
"""

import sys
import re
import json
from pathlib import Path
from typing import TypedDict


class Violation(TypedDict):
    phrase: str
    category: str
    line_number: int
    column: int
    context: str
    suggestion: str | None


# Banned phrases with categories and suggestions
BANNED_PHRASES: dict[str, dict[str, str | None]] = {
    # Throat-clearing openers
    "here's the thing:": {"category": "throat_clearing", "suggestion": None},
    "the uncomfortable truth is": {"category": "throat_clearing", "suggestion": None},
    "it turns out": {"category": "throat_clearing", "suggestion": None},
    "the real": {"category": "throat_clearing", "suggestion": None},
    "let me be clear": {"category": "throat_clearing", "suggestion": None},
    "the truth is": {"category": "throat_clearing", "suggestion": None},
    "i'll say it again": {"category": "throat_clearing", "suggestion": None},
    "i'm going to be honest": {"category": "throat_clearing", "suggestion": None},
    "can we talk about": {"category": "throat_clearing", "suggestion": None},
    "here's what i find interesting": {"category": "throat_clearing", "suggestion": None},
    "here's the problem though": {"category": "throat_clearing", "suggestion": None},
    "let's be real": {"category": "throat_clearing", "suggestion": None},
    "here's the deal": {"category": "throat_clearing", "suggestion": None},
    "here's what nobody tells you": {"category": "throat_clearing", "suggestion": None},

    # Emphasis crutches
    "full stop.": {"category": "emphasis_crutch", "suggestion": None},
    "period.": {"category": "emphasis_crutch", "suggestion": None},
    "let that sink in": {"category": "emphasis_crutch", "suggestion": None},
    "this matters because": {"category": "emphasis_crutch", "suggestion": None},
    "make no mistake": {"category": "emphasis_crutch", "suggestion": None},
    "here's why that matters": {"category": "emphasis_crutch", "suggestion": None},
    "read that again": {"category": "emphasis_crutch", "suggestion": None},
    "this is important": {"category": "emphasis_crutch", "suggestion": None},
    "this cannot be overstated": {"category": "emphasis_crutch", "suggestion": None},

    # Business jargon
    "navigate": {"category": "jargon", "suggestion": "handle, address, manage"},
    "unpack": {"category": "jargon", "suggestion": "explain, examine"},
    "lean into": {"category": "jargon", "suggestion": "accept, embrace"},
    "landscape": {"category": "jargon", "suggestion": "situation, field, market"},
    "game-changer": {"category": "jargon", "suggestion": "significant, important"},
    "game changer": {"category": "jargon", "suggestion": "significant, important"},
    "double down": {"category": "jargon", "suggestion": "commit, increase"},
    "deep dive": {"category": "jargon", "suggestion": "analysis, examination"},
    "take a step back": {"category": "jargon", "suggestion": "reconsider, pause"},
    "moving forward": {"category": "jargon", "suggestion": "next, from now"},
    "circle back": {"category": "jargon", "suggestion": "return to, revisit"},
    "on the same page": {"category": "jargon", "suggestion": "aligned, agreed"},
    "level up": {"category": "jargon", "suggestion": "improve, advance"},
    "bandwidth": {"category": "jargon", "suggestion": "capacity, time"},
    "synergy": {"category": "jargon", "suggestion": "cooperation, collaboration"},
    "low-hanging fruit": {"category": "jargon", "suggestion": "easy wins"},
    "pivot": {"category": "jargon", "suggestion": "change, shift"},
    "disrupt": {"category": "jargon", "suggestion": "change, challenge"},
    "leverage": {"category": "jargon", "suggestion": "use, apply"},
    "scalable": {"category": "jargon", "suggestion": "expandable, growable"},
    "actionable": {"category": "jargon", "suggestion": "practical, usable"},
    "ecosystem": {"category": "jargon", "suggestion": "environment, system"},
    "stakeholder": {"category": "jargon", "suggestion": "people involved"},
    "touch base": {"category": "jargon", "suggestion": "talk, connect"},
    "value-add": {"category": "jargon", "suggestion": "benefit, contribution"},
    "thought leader": {"category": "jargon", "suggestion": "expert"},
    "best-in-class": {"category": "jargon", "suggestion": "leading, top-tier"},
    "cutting-edge": {"category": "jargon", "suggestion": "modern, advanced"},

    # Filler phrases
    "at its core": {"category": "filler", "suggestion": None},
    "in today's": {"category": "filler", "suggestion": None},
    "it's worth noting": {"category": "filler", "suggestion": None},
    "interestingly,": {"category": "filler", "suggestion": None},
    "importantly,": {"category": "filler", "suggestion": None},
    "crucially,": {"category": "filler", "suggestion": None},
    "at the end of the day": {"category": "filler", "suggestion": None},
    "when it comes to": {"category": "filler", "suggestion": "for"},
    "in a world where": {"category": "filler", "suggestion": None},
    "the reality is": {"category": "filler", "suggestion": None},
    "with that said": {"category": "filler", "suggestion": None},
    "that being said": {"category": "filler", "suggestion": None},
    "all things considered": {"category": "filler", "suggestion": None},
    "by and large": {"category": "filler", "suggestion": None},
    "for the most part": {"category": "filler", "suggestion": None},
    "to be fair": {"category": "filler", "suggestion": None},
    "to be honest": {"category": "filler", "suggestion": None},
    "needless to say": {"category": "filler", "suggestion": None},
    "it goes without saying": {"category": "filler", "suggestion": None},

    # Meta-commentary
    "hint:": {"category": "meta", "suggestion": None},
    "plot twist:": {"category": "meta", "suggestion": None},
    "spoiler:": {"category": "meta", "suggestion": None},
    "you already know this, but": {"category": "meta", "suggestion": None},
    "but that's another post": {"category": "meta", "suggestion": None},
    "is a feature, not a bug": {"category": "meta", "suggestion": None},
    "dressed up as": {"category": "meta", "suggestion": None},
    "let me explain": {"category": "meta", "suggestion": None},
    "to put it simply": {"category": "meta", "suggestion": None},
    "in other words": {"category": "meta", "suggestion": None},
    "if you think about it": {"category": "meta", "suggestion": None},

    # Performative emphasis
    "creeps in": {"category": "performative", "suggestion": "appears, emerges"},
    "i promise": {"category": "performative", "suggestion": None},
    "they exist, i promise": {"category": "performative", "suggestion": None},
    "this is genuinely": {"category": "performative", "suggestion": None},
    "actually looks like": {"category": "performative", "suggestion": None},
    "trust me": {"category": "performative", "suggestion": None},
    "believe me": {"category": "performative", "suggestion": None},
}

# Structural patterns (regex)
STRUCTURAL_PATTERNS: list[dict[str, str]] = [
    {
        "pattern": r"not because .+?\. because",
        "category": "binary_contrast",
        "suggestion": "State the actual reason directly"
    },
    {
        "pattern": r"isn't the problem\. .+ is\.",
        "category": "binary_contrast",
        "suggestion": "State the problem directly"
    },
    {
        "pattern": r"feels like .+?\. it's actually",
        "category": "binary_contrast",
        "suggestion": "State the reality directly"
    },
    {
        "pattern": r"\. that's it\. that's the",
        "category": "dramatic_fragment",
        "suggestion": "Use complete sentences"
    },
    {
        "pattern": r"what if i told you",
        "category": "rhetorical_setup",
        "suggestion": "Make the point directly"
    },
    {
        "pattern": r"here's what i mean:",
        "category": "rhetorical_setup",
        "suggestion": "Remove and state directly"
    },
    {
        "pattern": r"think about it:",
        "category": "rhetorical_setup",
        "suggestion": "Remove - condescending"
    },
    {
        "pattern": r"and that's okay\.",
        "category": "unnecessary_permission",
        "suggestion": "Remove - unnecessary reassurance"
    },
]


def scan_for_violations(text: str) -> list[Violation]:
    """Scan text for banned phrases and structural patterns."""
    violations: list[Violation] = []
    lines = text.split('\n')
    text_lower = text.lower()

    # Check banned phrases
    for phrase, info in BANNED_PHRASES.items():
        start = 0
        while True:
            pos = text_lower.find(phrase, start)
            if pos == -1:
                break

            # Calculate line number and column
            line_num = text[:pos].count('\n') + 1
            line_start = text.rfind('\n', 0, pos) + 1
            column = pos - line_start + 1

            # Get context (the line containing the phrase)
            line_end = text.find('\n', pos)
            if line_end == -1:
                line_end = len(text)
            context = text[line_start:line_end].strip()

            violations.append({
                "phrase": phrase,
                "category": info["category"],
                "line_number": line_num,
                "column": column,
                "context": context[:100] + "..." if len(context) > 100 else context,
                "suggestion": info["suggestion"]
            })

            start = pos + 1

    # Check structural patterns
    for pattern_info in STRUCTURAL_PATTERNS:
        for match in re.finditer(pattern_info["pattern"], text_lower):
            pos = match.start()
            line_num = text[:pos].count('\n') + 1
            line_start = text.rfind('\n', 0, pos) + 1
            column = pos - line_start + 1

            line_end = text.find('\n', pos)
            if line_end == -1:
                line_end = len(text)
            context = text[line_start:line_end].strip()

            violations.append({
                "phrase": match.group(),
                "category": pattern_info["category"],
                "line_number": line_num,
                "column": column,
                "context": context[:100] + "..." if len(context) > 100 else context,
                "suggestion": pattern_info["suggestion"]
            })

    # Sort by line number, then column
    violations.sort(key=lambda v: (v["line_number"], v["column"]))

    return violations


def main() -> None:
    # Read input
    if len(sys.argv) > 1 and not sys.argv[1].startswith('--'):
        with open(sys.argv[1], 'r') as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    if not text.strip():
        print(json.dumps({"error": "No input provided", "violations": []}))
        sys.exit(1)

    violations = scan_for_violations(text)

    # Group by category for summary
    categories: dict[str, int] = {}
    for v in violations:
        categories[v["category"]] = categories.get(v["category"], 0) + 1

    output = {
        "total_violations": len(violations),
        "by_category": categories,
        "violations": violations
    }

    print(json.dumps(output, indent=2))

    # Exit with 1 if violations found
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
