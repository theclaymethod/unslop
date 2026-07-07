#!/usr/bin/env python3
"""Contract gates for co-writer suggestions.

Reads a suggestions file — the JSON emitted by suggest.py, i.e. an object with a
``document`` string and a ``suggestions`` list — and enforces four blocking
contracts. Each failure is named so a caller can act on it:

  span-minimality      Every suggested_replacement edits only its own span:
                       span.text matches document[start:end], the replacement
                       differs from the span text, and it shares no leading or
                       trailing whole word with the span (which would mean the
                       span grabbed unchanged text and could be shrunk — the
                       signature of a whole-sentence rewrite).
  replacement-scanner  Every suggested_replacement passes both scanners in
                       isolation AND introduces no new violation in context.
  accept-all           Applying every replacement yields a document that passes
                       both scanners with validate_preservation exit 0 vs the
                       original.
  span-overlap         Suggestion spans must not overlap.

Exit 0 when all gates pass, 1 otherwise. Failures (with the offending gate) are
reported as JSON on stdout.

Usage:
    python3 scripts/check_suggestions.py suggestions.json
    python3 scripts/check_suggestions.py < suggestions.json
"""

import argparse
import json
import sys
from pathlib import Path

from banned_phrase_scan import scan_for_violations
from structure_scan import scan as structure_scan
from validate_preservation import validate_preservation


def _leading_shared_words(a: str, b: str) -> int:
    """Number of identical leading whole words shared by two strings."""
    n = 0
    for x, y in zip(a.split(), b.split()):
        if x == y:
            n += 1
        else:
            break
    return n


def _trailing_shared_words(a: str, b: str) -> int:
    ra = " ".join(reversed(a.split()))
    rb = " ".join(reversed(b.split()))
    return _leading_shared_words(ra, rb)


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def violation_spans(text: str) -> list[tuple[int, int]]:
    """Absolute (start, end) offsets of every banned-phrase/structural violation."""
    starts = _line_starts(text)
    out = []
    for v in scan_for_violations(text):
        s = starts[v["line_number"] - 1] + v["column"] - 1
        out.append((s, s + len(v["phrase"])))
    return out


def _scanners_clean(text: str) -> bool:
    return not scan_for_violations(text) and not structure_scan(text).get("flags")


def apply_all(document: str, suggestions: list[dict]) -> str:
    """Apply every non-null replacement, right-to-left so offsets stay valid."""
    out = document
    for s in sorted(suggestions, key=lambda s: s["span"]["start"], reverse=True):
        rep = s.get("suggested_replacement")
        if rep is None:
            continue
        st, en = s["span"]["start"], s["span"]["end"]
        out = out[:st] + rep + out[en:]
    return out


def check(document: str, suggestions: list[dict]) -> list[dict]:
    failures: list[dict] = []

    # span-overlap: spans must be disjoint.
    order = sorted(range(len(suggestions)),
                   key=lambda i: (suggestions[i]["span"]["start"], suggestions[i]["span"]["end"]))
    last_end = None
    last_i = None
    for i in order:
        st, en = suggestions[i]["span"]["start"], suggestions[i]["span"]["end"]
        if last_end is not None and st < last_end:
            failures.append({
                "gate": "span-overlap",
                "suggestions": [last_i, i],
                "detail": f"span {st}-{en} overlaps the previous span ending at {last_end}",
            })
        last_end, last_i = en, i

    # span-minimality: span accuracy + tight, local replacements.
    for i, s in enumerate(suggestions):
        st, en = s["span"]["start"], s["span"]["end"]
        span_text = document[st:en]
        if span_text != s["span"]["text"]:
            failures.append({
                "gate": "span-minimality",
                "suggestion": i,
                "detail": "span.text does not match document[start:end]",
            })
        rep = s.get("suggested_replacement")
        if rep is None:
            continue
        if rep == span_text:
            failures.append({
                "gate": "span-minimality",
                "suggestion": i,
                "detail": "replacement is identical to the span text (no change)",
            })
            continue
        if _leading_shared_words(span_text, rep) > 0 or _trailing_shared_words(span_text, rep) > 0:
            failures.append({
                "gate": "span-minimality",
                "suggestion": i,
                "detail": "replacement shares leading/trailing whole words with the span; "
                          "shrink the span so the edit is minimal",
            })

    # replacement-scanner: each replacement is clean alone and in context.
    for i, s in enumerate(suggestions):
        rep = s.get("suggested_replacement")
        if rep is None:
            continue
        if not _scanners_clean(rep):
            failures.append({
                "gate": "replacement-scanner",
                "suggestion": i,
                "detail": "replacement does not pass both scanners in isolation",
            })
        st, en = s["span"]["start"], s["span"]["end"]
        ctx = document[:st] + rep + document[en:]
        new_start, new_end = st, st + len(rep)
        if any(a < new_end and new_start < b for (a, b) in violation_spans(ctx)):
            failures.append({
                "gate": "replacement-scanner",
                "suggestion": i,
                "detail": "replacement introduces a violation in context",
            })

    # accept-all: applying everything yields a clean, constraint-preserving doc.
    unresolved = [i for i, s in enumerate(suggestions) if s.get("suggested_replacement") is None]
    if unresolved:
        failures.append({
            "gate": "accept-all",
            "detail": f"suggestions {unresolved} have no replacement; cannot accept-all",
        })
    applied = apply_all(document, suggestions)
    if not _scanners_clean(applied):
        failures.append({
            "gate": "accept-all",
            "detail": "the accept-all document still fails a scanner",
        })
    preservation = validate_preservation(document, applied)
    if not preservation["passed"]:
        failures.append({
            "gate": "accept-all",
            "detail": "validate_preservation failed against the original",
            "missing": preservation["missing"],
        })

    return failures


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Contract gates for co-writer suggestions.")
    parser.add_argument(
        "path", nargs="?", help="Path to a suggestions JSON file (default: read stdin)"
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.path:
        path = Path(args.path)
        if not path.exists():
            print(f"Missing file: {path}", file=sys.stderr)
            return 2
        raw = path.read_text()
    else:
        raw = sys.stdin.read()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"passed": False, "error": f"invalid JSON: {e}"}, indent=2))
        return 1

    document = data.get("document")
    suggestions = data.get("suggestions", [])
    if not isinstance(document, str):
        print(json.dumps({"passed": False, "error": "missing 'document' string"}, indent=2))
        return 1

    failures = check(document, suggestions)
    result = {
        "passed": not failures,
        "failure_gates": sorted({f["gate"] for f in failures}),
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
