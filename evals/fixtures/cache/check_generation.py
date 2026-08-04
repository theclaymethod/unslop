#!/usr/bin/env python3
"""Deterministic probe for the run_local generation cache."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _write_fake_claude(bin_dir: Path, counter: Path) -> None:
    fake = bin_dir / "claude"
    fake.write_text(
        """#!/usr/bin/env python3
import os
import sys
from pathlib import Path

counter = Path(os.environ['CACHE_PROBE_COUNTER'])
with counter.open('a') as fh:
    fh.write('1\\n')
prompt = sys.argv[-1]
arm = 'with' if 'Use the skill under test' in prompt else 'without'
print(f'<final>{arm}-{os.getpid()}</final>\\nDiagnosis: fake model')
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)


def _write_tasks(path: Path, *, prompt: str = "cache probe") -> None:
    rows = [
        {
            "case_id": "CACHE-PROBE",
            "split": "tune",
            "kind": "harness_cache",
            "variant": "without_skill",
            "run_number": 1,
            "skill_name": "unslop",
            "instruction": "Do not use the skill.",
            "prompt": prompt,
            "run_dir": "CACHE-PROBE/without_skill",
            "input_files": [],
            "tags": [],
        },
        {
            "case_id": "CACHE-PROBE",
            "split": "tune",
            "kind": "harness_cache",
            "variant": "with_skill",
            "run_number": 1,
            "skill_name": "unslop",
            "instruction": "Use the skill under test (unslop).",
            "prompt": prompt,
            "run_dir": "CACHE-PROBE/with_skill",
            "input_files": [],
            "tags": [],
        },
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _write_race_tasks(path: Path) -> None:
    row = {
        "case_id": "CACHE-RACE",
        "split": "tune",
        "kind": "harness_cache",
        "variant": "without_skill",
        "run_number": 1,
        "skill_name": "unslop",
        "instruction": "Do not use the skill.",
        "prompt": "same-key race probe",
        "input_files": [],
        "tags": [],
    }
    rows = [dict(row, run_dir=f"CACHE-RACE/{index}") for index in range(8)]
    path.write_text("".join(json.dumps(item) + "\n" for item in rows), encoding="utf-8")


def _count_calls(counter: Path) -> int:
    return len(counter.read_text(encoding="utf-8").splitlines()) if counter.exists() else 0


def _run(
    tasks: Path,
    cache: Path,
    identity: str,
    env: dict[str, str],
    *,
    mode: str = "read-write",
    jobs: int = 1,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "evals/run_local.py"),
            str(tasks),
            "--jobs",
            str(jobs),
            "--cache-dir",
            str(cache),
            "--cache-mode",
            mode,
            "--cache-identity",
            identity,
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="unslop-cache-generation-") as raw:
        tmp = Path(raw)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        counter = tmp / "counter"
        _write_fake_claude(bin_dir, counter)
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ.get('PATH', '')}", CACHE_PROBE_COUNTER=str(counter))
        tasks = tmp / "tasks.jsonl"
        cache = tmp / "cache"
        _write_tasks(tasks)

        _run(tasks, cache, "fake-model-v1", env)
        first_total = _count_calls(counter)
        baseline = (tmp / "CACHE-PROBE/without_skill/output.md").read_bytes()
        second = _run(tasks, cache, "fake-model-v1", env)
        second_delta = _count_calls(counter) - first_total
        if (tmp / "CACHE-PROBE/without_skill/output.md").read_bytes() != baseline:
            raise AssertionError("cache hit changed without_skill output")
        if second.stderr.count("cache-hit") != 1:
            raise AssertionError(f"expected one baseline cache hit, got: {second.stderr}")

        identity_before = _count_calls(counter)
        _run(tasks, cache, "fake-model-v2", env)
        identity_delta = _count_calls(counter) - identity_before

        _write_tasks(tasks, prompt="changed cache probe")
        prompt_before = _count_calls(counter)
        _run(tasks, cache, "fake-model-v2", env)
        prompt_delta = _count_calls(counter) - prompt_before

        off_before = _count_calls(counter)
        _run(tasks, cache, "fake-model-v2", env, mode="off")
        off_delta = _count_calls(counter) - off_before

        race_tasks = tmp / "race-tasks.jsonl"
        race_cache = tmp / "race-cache"
        _write_race_tasks(race_tasks)
        _run(race_tasks, race_cache, "fake-model-v1", env, jobs=8)
        race_entries = list((race_cache / "generation-v1").glob("*/record.json"))
        if len(race_entries) != 1:
            raise AssertionError(f"same cache key produced {len(race_entries)} records")

        entries = list((cache / "generation-v1").glob("*/record.json"))
        if len(entries) < 3:
            raise AssertionError(f"expected separate content/identity cache entries, found {len(entries)}")
        print(
            f"first={first_total} second={second_delta} identity={identity_delta} "
            f"prompt={prompt_delta} off={off_delta}"
        )
        print("without_skill cache hit=1")
        print("concurrent_same_key=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
