#!/usr/bin/env python3
"""Prove serial subprocess cases finish before the parallel pool starts."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _write(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="unslop-runner-isolation-") as raw:
        tmp = Path(raw)
        shared = tmp / "shared"
        shared.mkdir()
        serial = tmp / "serial.py"
        watcher = tmp / "watcher.py"
        noop = tmp / "noop.py"
        _write(
            serial,
            "import pathlib, shutil, sys, time\n"
            "path = pathlib.Path(sys.argv[1])\n"
            "shutil.rmtree(path)\n"
            "time.sleep(0.2)\n"
            "path.mkdir()\n",
        )
        _write(
            watcher,
            "import pathlib, sys, time\n"
            "path = pathlib.Path(sys.argv[1])\n"
            "deadline = time.monotonic() + 0.5\n"
            "while time.monotonic() < deadline:\n"
            "    if not path.exists(): raise SystemExit('observed serial mutation')\n"
            "    time.sleep(0.005)\n",
        )
        _write(noop, "import time; time.sleep(0.1)\n")

        def row(case_id: str, command: list[str], *, serial_case: bool = False) -> dict:
            item = {
                "id": case_id,
                "title": case_id,
                "target": "script",
                "command": command,
                "assertions": [{"type": "exit_code", "equals": 0}],
            }
            if serial_case:
                item["serial"] = True
            return item

        suite = tmp / "suite.json"
        suite.write_text(
            json.dumps(
                {
                    "evals": [
                        row("ISO-01", [sys.executable, str(serial), str(shared)], serial_case=True),
                        row("ISO-02", [sys.executable, str(watcher), str(shared)]),
                        row("ISO-03", [sys.executable, str(noop)]),
                    ]
                }
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "evals/run_adversarial.py"),
                "--eval-file",
                str(suite),
                "--only",
                "ISO-",
                "--jobs",
                "2",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return 1
        if "parallel dispatch: 2 subprocess cases via 2 workers" not in proc.stdout:
            raise AssertionError(proc.stdout)
        print("serial_before_parallel=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
