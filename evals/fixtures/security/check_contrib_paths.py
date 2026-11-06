#!/usr/bin/env python3
"""Contribution writes must stay inside .unslop/contrib and must not follow symlinks."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts import contribute  # noqa: E402


def main() -> int:
    snippet = ROOT / "evals" / "fixtures" / "contrib" / "uncaught-snippet.txt"
    slug = "sec-symlink-probe"
    bundle = contribute.CONTRIB_ROOT / slug
    symlink_ok = False
    outside_ok = False
    with tempfile.TemporaryDirectory(prefix="unslop-contrib-") as raw:
        tmp = Path(raw)
        victim = tmp / "victim.txt"
        victim.write_text("SAFE-TARGET", encoding="utf-8")
        if bundle.exists():
            shutil.rmtree(bundle)
        bundle.mkdir(parents=True)
        try:
            (bundle / "manifest.json").symlink_to(victim)
            contribute.cmd_scaffold(
                argparse.Namespace(
                    pattern_name=slug,
                    snippet=str(snippet),
                    tell="durable bridge",
                    category="significance_inflation",
                    redact=None,
                    date="2026-01-01",
                )
            )
            symlink_ok = victim.read_text(encoding="utf-8") == "SAFE-TARGET"
        finally:
            if bundle.exists():
                shutil.rmtree(bundle)

        outside = tmp / "outside-bundle"
        outside.mkdir()
        snippet_text = "ORIGINAL"
        (outside / "snippet.txt").write_text(snippet_text, encoding="utf-8")
        (outside / "report.md").write_text("ORIGINAL", encoding="utf-8")
        (outside / "manifest.json").write_text(
            json.dumps(
                {
                    "pattern_name": "x",
                    "tell": "x",
                    "category": "x",
                    "date": "2026-01-01",
                }
            ),
            encoding="utf-8",
        )
        (outside / "row_fn.json").write_text(
            json.dumps({"stdin": snippet_text, "assertions": []}),
            encoding="utf-8",
        )
        code = contribute.cmd_verify(
            argparse.Namespace(bundle=str(outside), no_gates=True)
        )
        outside_ok = code == 2 and (outside / "report.md").read_text(encoding="utf-8") == "ORIGINAL"

    print(
        "contrib "
        f"symlink={'preserved' if symlink_ok else 'overwritten'} "
        f"outside={'preserved' if outside_ok else 'written'}"
    )
    return 0 if symlink_ok and outside_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
