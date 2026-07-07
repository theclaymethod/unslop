#!/usr/bin/env python3
"""
Local runner for the behavioral harness: turn prepared tasks into output.md
files that `skill-benchmark grade`/`judge` can read.

skill-eval-harness deliberately doesn't call a model and ships only a codex
runner. This drives the prepared tasks through `claude -p` instead.

  with_skill   -> the task instruction (read SKILL.md ...) + the prompt
  without_skill-> the bare prompt only (the no-skill baseline)

The final rewrite is captured as runs/<case>/<variant>/output.md, and the full
assistant answer is captured as runs/<case>/<variant>/answer_full.md.

Caveat: if the unslop skill is globally installed in the runner, the
without_skill baseline can still behave skill-like, which deflates measured
lift. Note that when interpreting results.

Usage:
    python3 evals/run_local.py runs/tune/tasks.jsonl        # writes output.md files
    python3 evals/run_local.py runs/tune/tasks.jsonl --jobs 4 --model sonnet
    python3 evals/run_local.py runs/tune/tasks.jsonl --dry-run
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path


def build_prompt(task: dict) -> str:
    suffix = (
        "\n\nPut the final text between <final> and </final> markers; put any "
        "diagnosis after it, quoting phrase names in double quotes."
    )
    if task["variant"] == "with_skill":
        return f"{task['instruction']}\n\n{task['prompt']}{suffix}"
    return f"{task['prompt']}{suffix}"


def extract_final(answer: str) -> str:
    start = answer.find("<final>")
    end = answer.find("</final>", start + len("<final>")) if start != -1 else -1
    if start == -1 or end == -1:
        return answer
    return answer[start + len("<final>"):end].strip()


def run_one(task: dict, runs_dir: Path, model: str | None, timeout: int) -> tuple[str, bool, str]:
    label = f"{task['case_id']}/{task['variant']}"
    out_dir = runs_dir / task["run_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["claude", "-p", build_prompt(task)]
    if model:
        cmd[1:1] = ["--model", model]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return label, False, "timeout"
    except (FileNotFoundError, OSError) as e:
        return label, False, f"runner unavailable: {e}"
    answer = proc.stdout.strip()
    if not answer:
        return label, False, (proc.stderr.strip()[:120] or "empty output")
    cli_errors = ("Not logged in", "Please run /login", "Credit balance is too low")
    if proc.returncode != 0 or any(marker in answer[:200] for marker in cli_errors):
        return label, False, f"runner error, not a model answer: {answer[:120]}"
    final = extract_final(answer)
    (out_dir / "answer_full.md").write_text(answer + "\n", encoding="utf-8")
    (out_dir / "output.md").write_text(final + "\n", encoding="utf-8")
    return label, True, f"{len(final)} final chars / {len(answer)} full chars"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", help="tasks.jsonl emitted by `skill-benchmark prepare`")
    parser.add_argument("--jobs", type=int, default=4, help="concurrent claude calls")
    parser.add_argument("--model", default=None, help="pass --model to claude (e.g. sonnet)")
    parser.add_argument("--timeout", type=int, default=180, help="per-call timeout (s)")
    parser.add_argument("--dry-run", action="store_true", help="print prompts, call nothing")
    args = parser.parse_args()

    tasks_path = Path(args.tasks)
    runs_dir = tasks_path.parent
    tasks = [json.loads(line) for line in tasks_path.read_text().splitlines() if line.strip()]

    if args.dry_run:
        for t in tasks:
            print(f"--- {t['case_id']}/{t['variant']} ---")
            print(build_prompt(t)[:300])
        return

    print(f"Running {len(tasks)} tasks (jobs={args.jobs}) -> {runs_dir}/", file=sys.stderr)
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futs = {pool.submit(run_one, t, runs_dir, args.model, args.timeout): t for t in tasks}
        for fut in concurrent.futures.as_completed(futs):
            label, ok, info = fut.result()
            print(f"  [{'ok ' if ok else 'FAIL'}] {label}  {info}", file=sys.stderr)
            failures += 0 if ok else 1

    print(f"Done. {len(tasks) - failures}/{len(tasks)} succeeded.", file=sys.stderr)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
