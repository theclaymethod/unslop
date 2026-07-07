#!/usr/bin/env python3
"""Eval entry point for detector pack integrity."""

import runpy

from _check_support import ROOT  # noqa: E402

runpy.run_path(str(ROOT / "scripts" / "check_packs.py"), run_name="__main__")
