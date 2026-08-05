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


def _write_fake_codex(bin_dir: Path, counter: Path, invocations: Path) -> None:
    fake = bin_dir / "codex"
    fake.write_text(
        """#!/usr/bin/env python3
import os
import sys
from pathlib import Path

counter = Path(os.environ['CACHE_PROBE_COUNTER'])
invocations = Path(os.environ['CACHE_PROBE_INVOCATIONS'])
with counter.open('a') as fh:
    fh.write('1\\n')
with invocations.open('a') as fh:
    fh.write(' '.join(sys.argv[1:]) + '\\n')
if sys.argv[1:3] != ['exec', '--skip-git-repo-check']:
    raise SystemExit('fake codex: unexpected command')
if '-m' not in sys.argv or sys.argv[sys.argv.index('-m') + 1] != 'gpt-5.6-luna':
    raise SystemExit('fake codex: expected -m gpt-5.6-luna')
if '-o' in sys.argv:
    output_path = Path(sys.argv[sys.argv.index('-o') + 1])
elif '--output-last-message' in sys.argv:
    output_path = Path(sys.argv[sys.argv.index('--output-last-message') + 1])
else:
    raise SystemExit('fake codex: missing output path')
prompt = sys.stdin.read()
arm = 'with' if 'Use the skill under test' in prompt else 'without'
output_path.write_text(
    f'<final>{arm}-clean</final>\\nDiagnosis: fake codex\\n',
    encoding='utf-8',
)
print('codex transcript noise: this must not appear in output.md')
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)

    # A successful fake Claude must never be needed by this probe. If the
    # runner regresses to its old hard-coded provider, fail loudly and leave a
    # count for the final assertion below.
    claude = bin_dir / "claude"
    claude.write_text(
        """#!/usr/bin/env python3
import os
from pathlib import Path

counter = Path(os.environ['CACHE_PROBE_CLAUDE'])
with counter.open('a') as fh:
    fh.write('1\\n')
raise SystemExit('fake claude must not be called')
""",
        encoding="utf-8",
    )
    claude.chmod(0o755)


def _write_tasks(path: Path, skill_dir: Path, *, prompt: str = "cache probe") -> None:
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
            "skill_paths": [str(skill_dir)],
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
            "skill_paths": [str(skill_dir)],
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
            "--model",
            "gpt-5.6-luna",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from evals.run_local import extract_output

    audit_output = extract_output(
        {"kind": "skill_behavior", "prompt": "Audit this. Do not rewrite."},
        "<final>unchanged source</final>\n\n[{\"span\":\"arguably\"}]",
    )
    if audit_output != '[{"span":"arguably"}]':
        raise AssertionError(f"report-only evidence was not extracted: {audit_output!r}")
    with tempfile.TemporaryDirectory(prefix="unslop-cache-generation-") as raw:
        tmp = Path(raw)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        counter = tmp / "counter"
        invocations = tmp / "invocations"
        claude_calls = tmp / "claude-calls"
        _write_fake_codex(bin_dir, counter, invocations)
        env = dict(
            os.environ,
            PATH=f"{bin_dir}:{os.environ.get('PATH', '')}",
            CACHE_PROBE_COUNTER=str(counter),
            CACHE_PROBE_INVOCATIONS=str(invocations),
            CACHE_PROBE_CLAUDE=str(claude_calls),
        )
        tasks = tmp / "tasks.jsonl"
        cache = tmp / "cache"
        skill_dir = tmp / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("version one\n", encoding="utf-8")
        _write_tasks(tasks, skill_dir)

        _run(tasks, cache, "fake-model-v1", env)
        first_total = _count_calls(counter)
        baseline = (tmp / "CACHE-PROBE/without_skill/output.md").read_bytes()
        if baseline != b"without-clean\n":
            raise AssertionError(f"Codex final extraction leaked transcript/diagnosis: {baseline!r}")
        if b"transcript noise" in (tmp / "CACHE-PROBE/without_skill/answer_full.md").read_bytes():
            raise AssertionError("Codex transcript leaked into answer_full.md")
        second = _run(tasks, cache, "fake-model-v1", env)
        second_delta = _count_calls(counter) - first_total
        if (tmp / "CACHE-PROBE/without_skill/output.md").read_bytes() != baseline:
            raise AssertionError("cache hit changed without_skill output")
        if second.stderr.count("cache-hit") != 2:
            raise AssertionError(f"expected two arm cache hits, got: {second.stderr}")

        skill_before = _count_calls(counter)
        (skill_dir / "SKILL.md").write_text("version two\n", encoding="utf-8")
        skill_run = _run(tasks, cache, "fake-model-v1", env)
        skill_delta = _count_calls(counter) - skill_before
        if skill_run.stderr.count("cache-hit") != 1:
            raise AssertionError(f"skill change should preserve only baseline hit: {skill_run.stderr}")

        identity_before = _count_calls(counter)
        _run(tasks, cache, "fake-model-v2", env)
        identity_delta = _count_calls(counter) - identity_before

        _write_tasks(tasks, skill_dir, prompt="changed cache probe")
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
        race_entries = list((race_cache / "generation-v2").glob("*/record.json"))
        if len(race_entries) != 1:
            raise AssertionError(f"same cache key produced {len(race_entries)} records")

        entries = list((cache / "generation-v2").glob("*/record.json"))
        if len(entries) < 3:
            raise AssertionError(f"expected separate content/identity cache entries, found {len(entries)}")
        invocation_rows = invocations.read_text(encoding="utf-8").splitlines()
        if not invocation_rows or any("-m gpt-5.6-luna" not in row for row in invocation_rows):
            raise AssertionError(f"Codex invocations did not select Luna: {invocation_rows}")
        claude_total = _count_calls(claude_calls)
        print(
            f"first={first_total} second={second_delta} skill={skill_delta} identity={identity_delta} "
            f"prompt={prompt_delta} off={off_delta}"
        )
        print("both_arms cache hit=2")
        print("concurrent_same_key=true")
        print("codex_provider=codex")
        print("codex_model=gpt-5.6-luna")
        print("clean_final=true")
        print("report_only_evidence=true")
        print(f"claude_calls={claude_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
