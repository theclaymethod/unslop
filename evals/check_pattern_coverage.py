#!/usr/bin/env python3
"""Enforce that every scanner pattern is exercised and every category FP-protected.

Two structural checks, both derived live from the scanner and the eval suite:

  coverage    - every STRUCTURAL_PATTERNS regex must match at least one eval corpus
                text, and every BANNED_PHRASES key must appear (case-insensitive) in
                at least one corpus text. The corpus is every script-case stdin plus
                the contents of every fixture file referenced by a script row.
  protections - every violation category the scanner can emit must be claimed by at
                least one scanner_false_positive row carrying `"protects": "<cat>"`.

A grandfather list is deliberately absent: an uncovered structural pattern or an
unprotected category is a hard failure, so a new scanner entry cannot land with zero
eval coverage while every other gate stays green. Run from the skill root:

  python3 evals/check_pattern_coverage.py              # both checks
  python3 evals/check_pattern_coverage.py --coverage   # pattern coverage only
  python3 evals/check_pattern_coverage.py --protections # category protection only
  python3 evals/check_pattern_coverage.py --no-performance-guard # correctness only
"""
import argparse
import re
import sys
import time
from pathlib import Path

from _check_support import ROOT, load_contract_examples, load_evals  # noqa: E402

sys.path.insert(0, str(ROOT))

from scripts.banned_phrase_scan import BANNED_PHRASES, STRUCTURAL_PATTERNS  # noqa: E402


def load_corpus(evals):
    """Return [(source_id, lowercased_text)] for every script-row input."""
    corpus = []
    fixture_refs = {}
    for e in evals:
        if e.get("target") != "script":
            continue
        stdin = e.get("stdin")
        if stdin:
            corpus.append((f"{e['id']}:stdin", stdin.lower()))
        for part in e.get("command", []):
            if isinstance(part, str) and "fixtures" in part:
                fixture_refs.setdefault((ROOT / part).resolve(), e["id"])

    # Many eval rows reference the same fixture directory. Read each fixture
    # once instead of walking and reopening that directory for every row.
    files = {}
    for path, case_id in fixture_refs.items():
        if path.is_dir():
            for sub in path.rglob("*"):
                if sub.is_file():
                    files.setdefault(sub.resolve(), case_id)
        elif path.exists():
            files.setdefault(path, case_id)
    for path, case_id in sorted(files.items(), key=lambda item: str(item[0])):
        try:
            text = path.read_text().lower()
        except (UnicodeDecodeError, OSError):
            continue
        corpus.append((f"{case_id}:{path.relative_to(ROOT)}", text))
    return corpus


def check_coverage(corpus):
    """Return (ok, lines) for pattern/phrase coverage."""
    lines = []
    ok = True

    # Structural patterns: compile once, match against the lowercased corpus.
    struct_uncovered = []
    struct_covered = 0
    for pat in STRUCTURAL_PATTERNS:
        regex = re.compile(pat["pattern"])
        if any(regex.search(text) for _, text in corpus):
            struct_covered += 1
        else:
            struct_uncovered.append(pat)
    if struct_uncovered:
        ok = False
        lines.append(f"Uncovered structural patterns ({len(struct_uncovered)}):")
        for pat in struct_uncovered:
            lines.append(f"  - [{pat['category']}] {pat['pattern']}")
        lines.append("  Add a row whose stdin triggers each pattern (no grandfathering).")

    # Banned phrases: literal key must appear somewhere in the corpus.
    phrase_uncovered = [k for k in BANNED_PHRASES if not any(k.lower() in text for _, text in corpus)]
    phrase_covered = len(BANNED_PHRASES) - len(phrase_uncovered)
    if phrase_uncovered:
        ok = False
        lines.append(f"Uncovered banned phrases ({len(phrase_uncovered)}):")
        for k in phrase_uncovered:
            lines.append(f"  - {k!r}")
        lines.append("  Add a REC-style coverage pack that packs these into eval stdins.")

    lines.append(
        f"coverage: {struct_covered}/{len(STRUCTURAL_PATTERNS)} structural patterns, "
        f"{phrase_covered}/{len(BANNED_PHRASES)} banned phrases exercised."
    )
    return ok, lines


def check_protections(evals):
    """Return (ok, lines) for per-category FP protection."""
    lines = []
    ok = True
    categories = set(v["category"] for v in BANNED_PHRASES.values())
    categories |= set(p["category"] for p in STRUCTURAL_PATTERNS)

    claimed = {}
    for e in evals:
        if e.get("category") != "scanner_false_positive":
            continue
        cat = e.get("protects")
        if cat:
            claimed.setdefault(cat, []).append(e["id"])

    unknown = sorted(set(claimed) - categories)
    if unknown:
        ok = False
        lines.append(f"FP rows claim categories the scanner never emits: {unknown}")

    unprotected = sorted(categories - set(claimed))
    if unprotected:
        ok = False
        lines.append(f"Unprotected categories ({len(unprotected)}):")
        for cat in unprotected:
            lines.append(f"  - {cat}")
        lines.append('  Add an FP row asserting total_violations == 0 with "protects": "<category>".')

    lines.append(
        f"protections: {len(categories - set(unprotected))}/{len(categories)} categories "
        f"claimed by a protects FP row."
    )
    return ok, lines


def main(argv):
    parser = argparse.ArgumentParser(description="Scanner pattern-coverage gate.")
    parser.add_argument("--coverage", action="store_true", help="run only the coverage check")
    parser.add_argument("--protections", action="store_true", help="run only the protection check")
    parser.add_argument(
        "--no-performance-guard",
        action="store_true",
        help="check correctness without the maintenance-lane wall-time budget",
    )
    args = parser.parse_args(argv)
    run_coverage = args.coverage
    run_protections = args.protections
    if not run_coverage and not run_protections:
        run_coverage = run_protections = True

    start = time.perf_counter()
    evals = load_evals()
    scanner_examples = load_contract_examples("scanner-examples")
    corpus = load_corpus(evals + scanner_examples)

    ok = True
    out = []
    if run_coverage:
        c_ok, c_lines = check_coverage(corpus)
        ok = ok and c_ok
        out += c_lines
    if run_protections:
        p_ok, p_lines = check_protections(scanner_examples)
        ok = ok and p_ok
        out += p_lines

    elapsed = time.perf_counter() - start
    print("\n".join(out))
    print(f"pattern-coverage gate {'OK' if ok else 'FAILED'} ({elapsed:.2f}s over {len(corpus)} corpus texts)")
    if elapsed > 10 and not args.no_performance_guard:
        print("performance guard tripped: check exceeded 10s", file=sys.stderr)
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
