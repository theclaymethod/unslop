#!/usr/bin/env python3
"""Check that scanner dictionary phrases are documented in taboo-phrases.md."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.banned_phrase_scan import BANNED_PHRASES  # noqa: E402


CATALOG = (ROOT / "references" / "taboo-phrases.md").read_text().lower()

DOCUMENTED_FAMILIES = {
    "period.": "period\\.",
    "full stop.": "full stop\\.",
    "garnered significant attention": "garnered significant/considerable attention",
    "garnered considerable attention": "garnered significant/considerable attention",
    "let's dive in": "let's dive in",
    "let's unpack": "let's unpack",
    "tells a clear story": "the data tells a (clear) story",
}


def main() -> int:
    missing = []
    for phrase in sorted(BANNED_PHRASES):
        needle = DOCUMENTED_FAMILIES.get(phrase, phrase).lower()
        if needle not in CATALOG:
            missing.append(phrase)

    if missing:
        print("Missing taboo catalog entries:")
        for phrase in missing:
            print(f"- {phrase}")
        return 1

    print(f"taboo parity ok: {len(BANNED_PHRASES)} banned phrase keys documented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
