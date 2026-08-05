#!/usr/bin/env python3
"""Exercise the canonical behavioral wrapper against fake Luna/Codex tools."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from evals.build_shared_benchmark import build_manifest  # noqa: E402


def _write_tools(bin_dir: Path) -> None:
    (bin_dir / "codex").write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

with Path(os.environ['LUNA_WRAPPER_CODEX_LOG']).open('a') as fh:
    fh.write(json.dumps(sys.argv[1:]) + '\\n')
if '-m' not in sys.argv or sys.argv[sys.argv.index('-m') + 1] != 'gpt-5.6-luna':
    raise SystemExit('expected Luna model')
flag = '-o' if '-o' in sys.argv else '--output-last-message'
out = Path(sys.argv[sys.argv.index(flag) + 1])
out.write_text('<final>Luna output</final>\\n\\nDiagnosis: concrete issue.\\n', encoding='utf-8')
""",
        encoding="utf-8",
    )
    (bin_dir / "skill-benchmark").write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
with Path(os.environ['LUNA_WRAPPER_HARNESS_LOG']).open('a') as fh:
    fh.write(json.dumps(args) + '\\n')
out = Path(args[args.index('--out') + 1])
out.parent.mkdir(parents=True, exist_ok=True)
if args[0] == 'prepare':
    rows = [
        {'case_id': 'LUNA-WRAPPER', 'kind': 'mode_routing', 'variant': 'with_skill', 'prompt': 'Rewrite.',
         'instruction': 'Use the skill under test.', 'run_dir': 'LUNA-WRAPPER/with_skill'},
        {'case_id': 'LUNA-WRAPPER', 'kind': 'mode_routing', 'variant': 'without_skill', 'prompt': 'Rewrite.',
         'instruction': '', 'run_dir': 'LUNA-WRAPPER/without_skill'},
        {'case_id': 'LUNA-WRAPPER-2', 'kind': 'rewrite', 'variant': 'with_skill', 'prompt': 'Rewrite again.',
         'instruction': 'Use the skill under test.', 'run_dir': 'LUNA-WRAPPER-2/with_skill'},
        {'case_id': 'LUNA-WRAPPER-2', 'kind': 'rewrite', 'variant': 'without_skill', 'prompt': 'Rewrite again.',
         'instruction': '', 'run_dir': 'LUNA-WRAPPER-2/without_skill'},
    ]
    out.write_text(''.join(json.dumps(row) + '\\n' for row in rows), encoding='utf-8')
elif args[0] == 'judge':
    row = {'judge_task_id': 'LUNA-WRAPPER::with_skill::run-1::judge-1',
           'case_id': 'LUNA-WRAPPER', 'variant': 'with_skill', 'run_number': 1,
           'verdict_kind': 'boolean', 'passed': True, 'evidence': 'ok'}
    if os.environ.get('LUNA_WRAPPER_MALFORMED_SCORED') == '1':
        row['verdict_kind'] = 'scored'
    out.write_text(json.dumps(row) + '\\n', encoding='utf-8')
elif args[0] == 'benchmark':
    rate = 0.0 if os.environ.get('LUNA_WRAPPER_BENCHMARK_FAIL') == '1' else 1.0
    results = [{'case_id': case_id, 'variant': 'with_skill',
                'missing_output': False, 'execution_valid': True,
                'combined_pass_rate': rate}
               for case_id in ('LUNA-WRAPPER', 'LUNA-WRAPPER-2')]
    if os.environ.get('LUNA_WRAPPER_BENCHMARK_OMIT') == '1':
        results.pop()
    if os.environ.get('LUNA_WRAPPER_BENCHMARK_DUPLICATE') == '1':
        results.append(dict(results[0]))
    if os.environ.get('LUNA_WRAPPER_BENCHMARK_UNEXPECTED') == '1':
        results.append(dict(results[0], case_id='LUNA-WRAPPER-UNEXPECTED'))
    report = {'results': results}
    out.write_text(json.dumps(report) + '\\n', encoding='utf-8')
else:
    raise SystemExit(f'unexpected skill-benchmark command: {args[0]}')
""",
        encoding="utf-8",
    )
    (bin_dir / "claude").write_text(
        "#!/bin/sh\necho claude-called >> \"$LUNA_WRAPPER_CLAUDE_LOG\"\nexit 91\n",
        encoding="utf-8",
    )
    for name in ("codex", "skill-benchmark", "claude"):
        (bin_dir / name).chmod(0o755)


def _run(
    root: Path,
    env: dict[str, str],
    cached: bool,
    should_fail: bool = False,
    expected_error: str = "behavioral acceptance failed",
) -> None:
    run_root = root / ("cached" if cached else "uncached")
    command = ["bash", "evals/run_behavioral.sh", "tune"]
    current = dict(env, UNSLOP_BEHAVIORAL_RUN_ROOT=str(run_root))
    if not cached:
        command.append("--uncached")
    proc = subprocess.run(command, cwd=ROOT, env=current, capture_output=True, text=True)
    if should_fail:
        if proc.returncode == 0 or expected_error not in proc.stderr:
            raise AssertionError(f"wrapper accepted a failed benchmark: {proc.stderr}\n{proc.stdout}")
    elif proc.returncode:
        raise AssertionError(f"wrapper failed: {proc.stderr}\n{proc.stdout}")


def main() -> int:
    source = json.loads((ROOT / "evals" / "adversarial-evals.json").read_text())
    manifest = build_manifest(source)
    for case in manifest["cases"]:
        judges = [a for a in case["assertions"] if a["type"] == "judge"]
        source_case = next(row for row in source["evals"] if row["id"] == case["id"])
        rubrics = [a["check"] for a in source_case["assertions"] if a["type"] == "judge"]
        if len(judges) != 1 or judges[0].get("rubric") != rubrics:
            raise AssertionError(f"expected one complete judge for {case['id']}: {judges}")

    with tempfile.TemporaryDirectory(prefix="unslop-luna-wrapper-") as raw:
        root = Path(raw)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        _write_tools(bin_dir)
        codex_log = root / "codex.jsonl"
        harness_log = root / "harness.jsonl"
        claude_log = root / "claude.log"
        env = dict(
            os.environ,
            PATH=f"{bin_dir}:{os.environ.get('PATH', '')}",
            LUNA_WRAPPER_CODEX_LOG=str(codex_log),
            LUNA_WRAPPER_HARNESS_LOG=str(harness_log),
            LUNA_WRAPPER_CLAUDE_LOG=str(claude_log),
        )
        _run(root, env, cached=False)
        _run(root, env, cached=True)
        _run(root, dict(env, LUNA_WRAPPER_BENCHMARK_FAIL="1"), cached=False, should_fail=True)
        _run(root, dict(env, LUNA_WRAPPER_BENCHMARK_OMIT="1"), cached=False, should_fail=True)
        _run(root, dict(env, LUNA_WRAPPER_BENCHMARK_DUPLICATE="1"), cached=False, should_fail=True)
        _run(root, dict(env, LUNA_WRAPPER_BENCHMARK_UNEXPECTED="1"), cached=False, should_fail=True)
        _run(
            root,
            dict(env, LUNA_WRAPPER_MALFORMED_SCORED="1"),
            cached=False,
            should_fail=True,
            expected_error="invalid scored judge verdict",
        )
        audit_output = (root / "uncached" / "tune" / "LUNA-WRAPPER" / "with_skill" / "output.md").read_text()
        if "Diagnosis: concrete issue." not in audit_output:
            raise AssertionError(f"mode-routing output hid the audit diagnosis: {audit_output!r}")
        fixed_rows = [json.loads(line) for line in (root / "uncached" / "tune" / "judge.fixed.jsonl").read_text().splitlines()]
        if any("score" in row or "threshold" in row for row in fixed_rows):
            raise AssertionError(f"boolean verdict was mutated into a scored verdict: {fixed_rows}")

        codex_rows = [json.loads(line) for line in codex_log.read_text().splitlines()]
        if len(codex_rows) != 28 or any(
            "-m" not in row or row[row.index("-m") + 1] != "gpt-5.6-luna"
            for row in codex_rows
        ):
            raise AssertionError(f"generation did not stay on Luna: {codex_rows}")
        harness_rows = [json.loads(line) for line in harness_log.read_text().splitlines()]
        judge_rows = [row for row in harness_rows if row[0] == "judge"]
        if len(judge_rows) != 7:
            raise AssertionError(f"expected seven judge routes: {judge_rows}")
        joined = [" ".join(row) for row in judge_rows]
        normalized = [row.replace("\\", "") for row in joined]
        if not any("--judge-backend codex" in row and "--judge-model gpt-5.6-luna" in row for row in joined):
            raise AssertionError(f"uncached judge did not select Luna: {joined}")
        if not any(
            "--judge-backend cmd" in row
            and "model_generate.py --kind codex --model gpt-5.6-luna" in row
            for row in normalized
        ):
            raise AssertionError(f"cached judge did not select Luna: {normalized}")
        if claude_log.exists() or any("claude" in row.lower() for row in joined):
            raise AssertionError("canonical behavioral wrapper routed to Claude")
        print("uncached_generation=luna")
        print("uncached_judge=luna")
        print("cached_generation=luna")
        print("cached_judge=luna")
        print("failed_benchmark=rejected")
        print("audit_diagnosis=visible")
        print("boolean_verdict=preserved")
        print("one_judge_per_case=true")
        print("partial_benchmark=rejected")
        print("duplicate_benchmark=rejected")
        print("unexpected_benchmark=rejected")
        print("malformed_scored_verdict=rejected")
        print("claude_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
