#!/usr/bin/env python3
"""Shared helpers for evals/check_*.py scripts.

Every check_*.py that shells out to a scripts/*.py CLI used to carry its own
copy-pasted ``run()`` helper. Only check_contrib.py's copy carried a
``timeout=60`` safety net (a hung scanner subprocess fails the check instead of
hanging the whole suite); the others silently dropped it on copy. This module
is the one place that safety net lives now, so every caller gets it.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd, timeout=60):
    """Run `cmd` from ROOT, capturing text stdout/stderr, with a timeout."""
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout)


def load_evals():
    """Return the parsed "evals" list from evals/adversarial-evals.json."""
    suite_path = ROOT / "evals" / "adversarial-evals.json"
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    return suite["evals"]
