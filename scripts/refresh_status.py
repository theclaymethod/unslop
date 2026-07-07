#!/usr/bin/env python3
"""
Report staleness of the three inputs the adversarial-refresh promise depends
on: the Wikipedia wiki-sync state, the model-parity bench, and the newest
adversarial-eval row. Pure stdlib, network-free, always exits 0 — this is a
reporter an agent reads before deciding what to run next
(see references/refresh.md), not a gate that blocks anything itself.

Usage:
    python3 scripts/refresh_status.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI_STATE_FILE = ROOT / "scripts" / ".wiki_sync_state.json"
PIPELINE_DOC = ROOT / "references" / "pipeline.md"
ADVERSARIAL_EVALS = ROOT / "evals" / "adversarial-evals.json"

# Guidance thresholds, not hard limits -- the numbers below are the point at
# which an agent should proactively check, not a required cadence. Every
# field is a plain reporter value; nothing here fails the build.
#
# Wikipedia's "Signs of AI writing" page is a slow-moving reference page;
# quarterly is enough to catch drift without chasing noise.
WIKI_STALE_DAYS = 90
# The GPT/Anthropic model spectrums shift on the order of months, and the
# rule in references/pipeline.md already forces a re-run on any co-writer,
# mimic, or detector-pack change regardless of this threshold -- this is a
# backstop for the case where no such change happened but time still passed.
BENCH_STALE_DAYS = 180
# The adversarial-eval catalog is the product's growth signal (docs/PRODUCT.md,
# Growth); a two-month gap with no new row is worth a look even if nothing
# else prompted one.
ROW_STALE_DAYS = 60

# The convention this script relies on in references/pipeline.md: the
# recorded parity date is written as "Live matrix recorded **YYYY-MM-DD**."
# If that sentence's wording changes, this regex needs to change with it.
PIPELINE_DATE_RE = re.compile(
    r"Live matrix recorded \*\*(\d{4}-\d{2}-\d{2})\*\*"
)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _days_since(d: date | None) -> int | None:
    if d is None:
        return None
    return (_today() - d).days


def _status(last: date | None, stale_days: int) -> dict:
    days = _days_since(last)
    stale = days is None or days > stale_days
    return {
        "last": last.isoformat() if last else None,
        "days": days,
        "stale": stale,
    }


def _parse_iso_date(value: str) -> date | None:
    """Best-effort parse of an ISO-8601 timestamp (MediaWiki style, 'Z'
    suffix included) down to a plain date."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


def wiki_sync_status() -> dict:
    if not WIKI_STATE_FILE.exists():
        # Never synced. Treat as stale so it surfaces for attention.
        return _status(None, WIKI_STALE_DAYS)

    last: date | None = None
    try:
        state = json.loads(WIKI_STATE_FILE.read_text())
        last = _parse_iso_date(state.get("last_timestamp", ""))
    except (json.JSONDecodeError, OSError):
        last = None

    if last is None:
        # Content didn't parse; fall back to the state file's mtime.
        try:
            mtime = WIKI_STATE_FILE.stat().st_mtime
            last = datetime.fromtimestamp(mtime, tz=timezone.utc).date()
        except OSError:
            last = None

    return _status(last, WIKI_STALE_DAYS)


def parity_bench_status() -> dict:
    last: date | None = None
    try:
        text = PIPELINE_DOC.read_text()
        match = PIPELINE_DATE_RE.search(text)
        if match:
            last = date.fromisoformat(match.group(1))
    except OSError:
        last = None

    return _status(last, BENCH_STALE_DAYS)


def newest_pattern_row_status() -> dict:
    last: date | None = None
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                "-1",
                "--format=%cs",
                "--",
                str(ADVERSARIAL_EVALS),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        out = result.stdout.strip()
        if result.returncode == 0 and out:
            last = date.fromisoformat(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        last = None

    return _status(last, ROW_STALE_DAYS)


def main() -> None:
    output = {
        "wiki_sync": wiki_sync_status(),
        "parity_bench": parity_bench_status(),
        "newest_pattern_row": newest_pattern_row_status(),
    }
    print(json.dumps(output, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
