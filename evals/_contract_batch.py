"""Run a named checker family once and keep successful output compact."""

from __future__ import annotations

import contextlib
import io
import traceback
from collections.abc import Callable, Mapping
from typing import Optional


Check = Callable[[], Optional[int]]


def run_contract(label: str, checks: Mapping[str, Check]) -> int:
    """Run every named check, showing captured details only when it fails."""
    failed: list[str] = []
    for name, check in checks.items():
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = check()
            return_code = 0 if result is None else int(result)
        except SystemExit as exc:
            return_code = exc.code if isinstance(exc.code, int) else 1
        except Exception:  # noqa: BLE001  # pragma: no cover - failure evidence
            return_code = 1
            traceback.print_exc(file=stderr)

        if return_code:
            failed.append(name)
            print(f"FAIL {label}/{name} (exit {return_code})")
            details = (stdout.getvalue() + stderr.getvalue()).rstrip()
            if details:
                print(details)

    passed = len(checks) - len(failed)
    print(f"{label} contract: {passed}/{len(checks)} passed")
    if failed:
        print(f"failed: {', '.join(failed)}")
        return 1
    return 0
