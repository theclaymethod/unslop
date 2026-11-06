#!/usr/bin/env python3
"""Harvest tag stripping must stay linear and still drop closed tags."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_samples  # noqa: E402


def main() -> int:
    cleaned = harvest_samples.strip_transcript_noise(
        "Note <system-reminder>hidden</system-reminder> stays."
    )
    stripped = "hidden" not in cleaned and "Note" in cleaned and "stays" in cleaned
    payload = "<" + ("a" * 40000)
    started = time.perf_counter()
    harvest_samples.strip_transcript_noise(payload)
    elapsed = time.perf_counter() - started
    print(f"tag-strip={'ok' if stripped else 'broken'} elapsed={elapsed:.4f}")
    return 0 if stripped and elapsed < 0.15 else 1


if __name__ == "__main__":
    raise SystemExit(main())
