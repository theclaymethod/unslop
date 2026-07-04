#!/usr/bin/env python3
"""Eval entry point for detector pack integrity."""

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

runpy.run_path(str(ROOT / "scripts" / "check_packs.py"), run_name="__main__")
