#!/usr/bin/env python3
"""Deterministic probe for the stdin judge cache."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _write_fake_judge(path: Path, counter: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import os
import sys
from pathlib import Path

counter = Path(os.environ['CACHE_PROBE_COUNTER'])
count = int(counter.read_text() or '0') if counter.exists() else 0
count += 1
counter.write_text(str(count))
prompt = sys.stdin.read()
if 'malformed' in prompt:
    print('not-json')
    raise SystemExit(0)
if 'nonzero' in prompt:
    print('provider failure', file=sys.stderr)
    raise SystemExit(7)
if 'error-json' in prompt:
    print('{"error": "rate limited"}')
    raise SystemExit(0)
print('{"passed": true, "rationale": "fake judge"}')
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _call(wrapper: Path, fake: Path, cache: Path, identity: str, prompt: str, env: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sys.executable,
            str(wrapper),
            "--cache-dir",
            str(cache),
            "--identity",
            identity,
            "--judge-cmd",
            str(fake),
        ],
        cwd=ROOT,
        env=env,
        input=prompt.encode("utf-8"),
        capture_output=True,
        check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="unslop-cache-judge-") as raw:
        tmp = Path(raw)
        counter = tmp / "counter"
        fake = tmp / "fake-judge"
        _write_fake_judge(fake, counter)
        env = dict(os.environ, CACHE_PROBE_COUNTER=str(counter))
        cache = tmp / "cache"
        wrapper = ROOT / "evals/cache_judge.py"

        first = _call(wrapper, fake, cache, "judge-v1", "valid prompt", env)
        second = _call(wrapper, fake, cache, "judge-v1", "valid prompt", env)
        if first.returncode != 0 or second.returncode != 0:
            raise AssertionError(f"valid judge calls failed: {first.returncode}, {second.returncode}")
        if first.stdout != second.stdout:
            raise AssertionError("judge cache hit changed the cached stdout")
        valid_total = int(counter.read_text())

        _call(wrapper, fake, cache, "judge-v2", "valid prompt", env)
        identity_delta = int(counter.read_text()) - valid_total

        malformed_before = int(counter.read_text())
        malformed_a = _call(wrapper, fake, cache, "judge-v2", "malformed prompt", env)
        malformed_b = _call(wrapper, fake, cache, "judge-v2", "malformed prompt", env)
        malformed_delta = int(counter.read_text()) - malformed_before
        if malformed_a.returncode != 0 or malformed_b.returncode != 0:
            raise AssertionError("malformed provider response should relay zero exit")

        error_before = int(counter.read_text())
        error_a = _call(wrapper, fake, cache, "judge-v2", "error-json prompt", env)
        error_b = _call(wrapper, fake, cache, "judge-v2", "error-json prompt", env)
        error_delta = int(counter.read_text()) - error_before
        if error_a.returncode != 0 or error_b.returncode != 0:
            raise AssertionError("error-shaped JSON should relay provider exit")

        nonzero_before = int(counter.read_text())
        nonzero_a = _call(wrapper, fake, cache, "judge-v2", "nonzero prompt", env)
        nonzero_b = _call(wrapper, fake, cache, "judge-v2", "nonzero prompt", env)
        nonzero_delta = int(counter.read_text()) - nonzero_before
        if nonzero_a.returncode != 7 or nonzero_b.returncode != 7:
            raise AssertionError("nonzero provider response should relay its exit code")

        records = list((cache / "judge-v1").glob("*.json"))
        if len(records) != 2:
            raise AssertionError(f"expected only two valid judge records, found {len(records)}")
        print(
            f"valid={valid_total} identity={identity_delta} "
            f"malformed={malformed_delta} error_json={error_delta} nonzero={nonzero_delta}"
        )
        print("cached_valid_output=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
