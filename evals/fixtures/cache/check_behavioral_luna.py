#!/usr/bin/env python3
"""Exercise the canonical behavioral wrapper against fake Luna/Codex tools."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


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
out.write_text('<final>Luna output</final>\\n', encoding='utf-8')
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
        {'case_id': 'LUNA-WRAPPER', 'variant': 'with_skill', 'prompt': 'Rewrite.',
         'instruction': 'Use the skill under test.', 'run_dir': 'LUNA-WRAPPER/with_skill'},
        {'case_id': 'LUNA-WRAPPER', 'variant': 'without_skill', 'prompt': 'Rewrite.',
         'instruction': '', 'run_dir': 'LUNA-WRAPPER/without_skill'},
    ]
    out.write_text(''.join(json.dumps(row) + '\\n' for row in rows), encoding='utf-8')
elif args[0] == 'judge':
    out.write_text('', encoding='utf-8')
elif args[0] == 'benchmark':
    out.write_text('{}\\n', encoding='utf-8')
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


def _run(root: Path, env: dict[str, str], cached: bool) -> None:
    run_root = root / ("cached" if cached else "uncached")
    command = ["bash", "evals/run_behavioral.sh", "tune"]
    current = dict(env, UNSLOP_BEHAVIORAL_RUN_ROOT=str(run_root))
    if not cached:
        command.append("--uncached")
    proc = subprocess.run(command, cwd=ROOT, env=current, capture_output=True, text=True)
    if proc.returncode:
        raise AssertionError(f"wrapper failed: {proc.stderr}\n{proc.stdout}")


def main() -> int:
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

        codex_rows = [json.loads(line) for line in codex_log.read_text().splitlines()]
        if len(codex_rows) != 4 or any(
            "-m" not in row or row[row.index("-m") + 1] != "gpt-5.6-luna"
            for row in codex_rows
        ):
            raise AssertionError(f"generation did not stay on Luna: {codex_rows}")
        harness_rows = [json.loads(line) for line in harness_log.read_text().splitlines()]
        judge_rows = [row for row in harness_rows if row[0] == "judge"]
        if len(judge_rows) != 2:
            raise AssertionError(f"expected two judge routes: {judge_rows}")
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
        print("claude_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
