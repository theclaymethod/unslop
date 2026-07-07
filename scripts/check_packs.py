#!/usr/bin/env python3
"""Validate tiered detector pack integrity."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = ROOT / "references" / "packs"
MANIFEST = PACK_DIR / "manifest.json"

JUDGE_ONLY_MACROS = {
    "macro_both_sidesism",
    "macro_redemption_arc",
    "macro_preview_recap",
    "macro_over_determination",
    "macro_emotional_flatness",
}


def scanner_categories() -> set[str]:
    sys.path.insert(0, str(ROOT))
    from scripts.banned_phrase_scan import BANNED_PHRASES, STRUCTURAL_PATTERNS

    return {v["category"] for v in BANNED_PHRASES.values()} | {
        v["category"] for v in STRUCTURAL_PATTERNS
    }


def main() -> int:
    failures: list[str] = []
    data = json.loads(MANIFEST.read_text())
    packs: dict[str, list[str]] = data["packs"]
    category_to_pack: dict[str, str] = {}

    for pack, categories in packs.items():
        path = PACK_DIR / f"{pack}.md"
        if not path.exists():
            failures.append(f"missing pack file: {path}")
            continue
        text = path.read_text()
        line_count = len(text.splitlines())
        if line_count > 120:
            failures.append(f"{path} has {line_count} lines; max 120")
        if "## Emit" not in text:
            failures.append(f"{path} missing ## Emit section")
        for category in categories:
            if category in category_to_pack:
                failures.append(
                    f"category {category} mapped to both {category_to_pack[category]} and {pack}"
                )
            category_to_pack[category] = pack

    scanner = scanner_categories()
    missing = scanner - set(category_to_pack)
    extra_scanner = (set(category_to_pack) - scanner) - JUDGE_ONLY_MACROS
    if missing:
        failures.append(f"scanner categories missing from packs: {sorted(missing)}")
    if extra_scanner:
        failures.append(f"unknown non-macro categories in manifest: {sorted(extra_scanner)}")

    macro_hits = {m: category_to_pack.get(m) for m in JUDGE_ONLY_MACROS}
    missing_macros = [m for m, pack in macro_hits.items() if pack is None]
    if missing_macros:
        failures.append(f"judge-only macro families missing: {sorted(missing_macros)}")
    for macro, pack in macro_hits.items():
        if pack and pack != "pack-structure":
            failures.append(f"{macro} must live in pack-structure, found {pack}")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"pack integrity ok: {len(packs)} packs, {len(scanner)} scanner categories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
