#!/usr/bin/env python3
"""Directory scans must not read files reached through a symlink."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_samples  # noqa: E402
import voice_profile  # noqa: E402


def paragraph(marker: str) -> str:
    sentence = (
        f"{marker} sat in the margin while I rewrote the same paragraph again. "
    )
    return sentence * 4


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="unslop-symlink-") as raw:
        tmp = Path(raw)
        scan = tmp / "scan"
        scan.mkdir()
        secret = tmp / "secret.txt"
        secret.write_text(paragraph("SYMLINK_SECRET_MARKER"), encoding="utf-8")
        (scan / "real.txt").write_text(paragraph("REAL_MARKER_VISIBLE"), encoding="utf-8")
        (scan / "leak.txt").symlink_to(secret)
        output, _code = harvest_samples.harvest(
            argparse.Namespace(
                sources=[str(scan)],
                min_words=40,
                max_candidates=20,
                since=None,
                self_check_determinism=False,
            )
        )
        voice_blob = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in voice_profile.iter_docs(scan)
        )
    harvest_blob = json.dumps(output)
    harvest_ok = (
        "SYMLINK_SECRET_MARKER" not in harvest_blob
        and "REAL_MARKER_VISIBLE" in harvest_blob
    )
    voice_ok = (
        "SYMLINK_SECRET_MARKER" not in voice_blob
        and "REAL_MARKER_VISIBLE" in voice_blob
    )
    print(
        "symlink "
        f"harvest={'contained' if harvest_ok else 'escaped'} "
        f"voice={'contained' if voice_ok else 'escaped'}"
    )
    return 0 if harvest_ok and voice_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
