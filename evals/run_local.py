#!/usr/bin/env python3
"""
Local runner for the behavioral harness: turn prepared tasks into output.md
files that `skill-benchmark grade`/`judge` can read.

Generation uses the local Codex CLI through ``model_generate.call_codex`` so
its output-last-message extraction is shared with the other Codex checks. The
default and canonical acceptance model is Luna.

  with_skill   -> the task instruction (read SKILL.md ...) + the prompt
  without_skill-> the bare prompt only (the no-skill baseline)

The final rewrite is captured as runs/<case>/<variant>/output.md, and the full
assistant answer is captured as runs/<case>/<variant>/answer_full.md.

Caveat: if the unslop skill is globally installed in the runner, the
without_skill baseline can still behave skill-like, which deflates measured
lift. Note that when interpreting results.

Usage:
    python3 evals/run_local.py runs/tune/tasks.jsonl        # writes output.md files
    python3 evals/run_local.py runs/tune/tasks.jsonl --model gpt-5.6-luna
    python3 evals/run_local.py runs/tune/tasks.jsonl --dry-run
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


CACHE_SCHEMA = "generation-v2"
DEFAULT_CODEX_MODEL = "gpt-5.6-luna"
PROMPT_SUFFIX = (
    "\n\nPut the final text between <final> and </final> markers; put any "
    "diagnosis after it, quoting phrase names in double quotes."
)
OUTPUT_NAMES = ("answer_full.md", "output.md")


def build_prompt(task: dict) -> str:
    if task["variant"] == "with_skill":
        return f"{task['instruction']}\n\n{task['prompt']}{PROMPT_SUFFIX}"
    return f"{task['prompt']}{PROMPT_SUFFIX}"


def extract_final(answer: str) -> str:
    start = answer.find("<final>")
    end = answer.find("</final>", start + len("<final>")) if start != -1 else -1
    if start == -1 or end == -1:
        return answer
    return answer[start + len("<final>"):end].strip()


def extract_output(task: dict, answer: str) -> str:
    """Keep audit evidence visible while returning prose for rewrite tasks."""
    final = extract_final(answer)
    prompt = task.get("prompt", "").lower()
    explicit_report_only = any(
        marker in prompt
        for marker in ("do not rewrite", "don't rewrite", "report only", "audit only")
    )
    if task.get("kind") != "mode_routing" and not explicit_report_only:
        return final
    end = answer.find("</final>")
    remainder = answer[end + len("</final>"):].strip() if end != -1 else ""
    if explicit_report_only:
        return remainder or final
    return "\n\n".join(part for part in (final, remainder) if part)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    if path.is_dir():
        digest = hashlib.sha256()
        for child in sorted(p for p in path.rglob("*") if p.is_file()):
            digest.update(str(child.relative_to(path)).encode("utf-8"))
            digest.update(b"\0")
            digest.update(bytes.fromhex(_sha256_path(child)))
        return digest.hexdigest()
    return "missing"


def _task_for_cache(task: dict) -> dict:
    """Return task content that affects the generated answer.

    ``run_dir`` is only an artifact location and must not prevent reuse across
    optimization iterations. ``repo_root`` is represented by the current
    working directory in the surrounding cache payload, while fixture paths
    carry both their stable spelling and content digest.
    """
    content = dict(task)
    content.pop("run_dir", None)
    content.pop("repo_root", None)
    fixture_rows = []
    for raw in content.get("input_files", []) or []:
        path = Path(str(raw))
        fixture_rows.append({"path": str(path), "sha256": _sha256_path(path)})
    content["input_files"] = fixture_rows
    raw_skill_paths = content.pop("skill_paths", []) or []
    if content.get("variant") == "with_skill":
        content["skill_paths"] = [
            {"path": str(raw), "sha256": _sha256_path(Path(str(raw)))}
            for raw in raw_skill_paths
        ]
    return content


def generation_cache_key(
    task: dict,
    *,
    model: str | None,
    cache_identity: str,
) -> tuple[str, dict]:
    payload = {
        "schema": CACHE_SCHEMA,
        "task": _task_for_cache(task),
        "provider": "codex",
        "model": model or "<cli-default>",
        "cache_identity": cache_identity,
        "prompt_suffix": PROMPT_SUFFIX,
        "extract_protocol": "mode-aware-final-markers-v2",
    }
    return _sha256_bytes(_canonical_json(payload).encode("utf-8")), payload


def _entry_dir(cache_dir: Path, key: str) -> Path:
    return cache_dir / CACHE_SCHEMA / key


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _load_generation_cache(cache_dir: Path, key: str) -> tuple[bytes, bytes] | None:
    entry = _entry_dir(cache_dir, key)
    record_path = entry / "record.json"
    answer_path = entry / "answer_full.md"
    output_path = entry / "output.md"
    if not (record_path.is_file() and answer_path.is_file() and output_path.is_file()):
        return None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        answer = answer_path.read_bytes()
        output = output_path.read_bytes()
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if record.get("schema") != CACHE_SCHEMA or record.get("key") != key:
        return None
    if record.get("answer_sha256") != _sha256_bytes(answer):
        return None
    if record.get("output_sha256") != _sha256_bytes(output):
        return None
    return answer, output


def _save_generation_cache(
    cache_dir: Path,
    key: str,
    payload: dict,
    answer: bytes,
    output: bytes,
) -> None:
    entry = _entry_dir(cache_dir, key)
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{key}.", dir=str(cache_dir)))
    try:
        (tmp / "answer_full.md").write_bytes(answer)
        (tmp / "output.md").write_bytes(output)
        (tmp / "record.json").write_text(
            _canonical_json({
                "schema": CACHE_SCHEMA,
                "key": key,
                "key_payload": payload,
                "answer_sha256": _sha256_bytes(answer),
                "output_sha256": _sha256_bytes(output),
            }) + "\n",
            encoding="utf-8",
        )
        entry.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(tmp, entry)
        except OSError:
            # macOS reports ENOTEMPTY rather than FileExistsError when another
            # worker wins a same-key directory race. Accept only a complete,
            # hash-valid winning entry; otherwise surface the filesystem error.
            if _load_generation_cache(cache_dir, key) is None:
                raise
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _install_outputs(out_dir: Path, answer: bytes, output: bytes) -> None:
    _atomic_write(out_dir / "answer_full.md", answer)
    _atomic_write(out_dir / "output.md", output)


def _call_codex(model: str | None, prompt: str, timeout: int) -> tuple[str | None, str | None]:
    """Call Codex through the shared safe adapter and read its final message."""
    # The behavioral runner pins its acceptance model explicitly. Keeping a
    # default here also makes direct invocations deterministic instead of
    # silently selecting whatever the CLI happens to default to.
    try:
        # ``evals.run_local`` is also imported by offline checks; support that
        # package seam as well as direct ``python3 evals/run_local.py``.
        from .model_generate import call_codex
    except ImportError:
        from model_generate import call_codex

    text, error = call_codex(model or DEFAULT_CODEX_MODEL, prompt, timeout=timeout)
    if error:
        return None, error
    return text, None


def run_one(
    task: dict,
    runs_dir: Path,
    model: str | None,
    timeout: int,
    *,
    cache_dir: Path | None = None,
    cache_mode: str = "off",
    cache_identity: str = "",
) -> tuple[str, bool, str]:
    label = f"{task['case_id']}/{task['variant']}"
    out_dir = runs_dir / task["run_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(task)
    cacheable = cache_mode != "off"
    key_payload = None
    key = None
    if cacheable:
        key, key_payload = generation_cache_key(
            task,
            model=model,
            cache_identity=cache_identity,
        )
        cached = _load_generation_cache(cache_dir, key) if cache_dir is not None else None
        if cached is not None:
            _install_outputs(out_dir, *cached)
            return label, True, f"cache-hit {len(cached[1]) - 1} final bytes"

    # A failed model call must not leave an older candidate answer for the
    # benchmark to discover on a later run.
    for name in OUTPUT_NAMES:
        (out_dir / name).unlink(missing_ok=True)

    answer, error = _call_codex(model, prompt, timeout)
    if error:
        return label, False, f"model-call-fail {error}"
    if answer is None:
        return label, False, "model-call-fail empty output"
    answer = answer.strip()
    if not answer:
        return label, False, "model-call-fail empty output"
    final = extract_output(task, answer)
    answer_bytes = (answer + "\n").encode("utf-8")
    output_bytes = (final + "\n").encode("utf-8")
    _install_outputs(out_dir, answer_bytes, output_bytes)
    if cacheable and cache_mode == "read-write" and cache_dir is not None and key is not None and key_payload is not None:
        _save_generation_cache(cache_dir, key, key_payload, answer_bytes, output_bytes)
        status = "cache-miss"
    else:
        status = "model-call"
    return label, True, f"{status} {len(final)} final chars / {len(answer)} full chars"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", help="tasks.jsonl emitted by `skill-benchmark prepare`")
    parser.add_argument("--jobs", type=int, default=4, help="concurrent model calls")
    parser.add_argument(
        "--model", default=DEFAULT_CODEX_MODEL, help="Codex model id (default: gpt-5.6-luna)"
    )
    parser.add_argument("--timeout", type=int, default=180, help="per-call timeout (s)")
    parser.add_argument("--cache-dir", default=None, help="generation cache directory (opt-in)")
    parser.add_argument(
        "--cache-mode",
        choices=("off", "read-write"),
        default="off",
        help="reuse successful outputs with content-based invalidation; default off",
    )
    parser.add_argument("--cache-identity", default=None, help="explicit model/runner identity for cache keys")
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        metavar="ID",
        help="run only this case ID; repeatable",
    )
    parser.add_argument(
        "--variant",
        choices=("with_skill", "without_skill"),
        help="run only one benchmark arm",
    )
    parser.add_argument("--dry-run", action="store_true", help="print prompts, call nothing")
    args = parser.parse_args()

    if args.cache_mode != "off" and not args.cache_dir:
        parser.error("--cache-mode requires --cache-dir")
    if args.cache_mode != "off" and not args.cache_identity:
        parser.error("--cache-mode requires explicit --cache-identity")

    tasks_path = Path(args.tasks)
    runs_dir = tasks_path.parent
    tasks = [json.loads(line) for line in tasks_path.read_text().splitlines() if line.strip()]
    if args.case:
        wanted = set(args.case)
        tasks = [task for task in tasks if task.get("case_id") in wanted]
        missing = wanted - {task.get("case_id") for task in tasks}
        if missing:
            parser.error("unknown --case: " + ", ".join(sorted(missing)))
    if args.variant:
        tasks = [task for task in tasks if task.get("variant") == args.variant]

    if args.dry_run:
        for t in tasks:
            print(f"--- {t['case_id']}/{t['variant']} ---")
            print(build_prompt(t)[:300])
        return

    cache_dir = Path(args.cache_dir).resolve() if args.cache_dir else None
    print(f"Running {len(tasks)} tasks (jobs={args.jobs}) -> {runs_dir}/", file=sys.stderr)
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futs = {
            pool.submit(
                run_one,
                t,
                runs_dir,
                args.model,
                args.timeout,
                cache_dir=cache_dir,
                cache_mode=args.cache_mode,
                cache_identity=args.cache_identity or "",
            ): t
            for t in tasks
        }
        for fut in concurrent.futures.as_completed(futs):
            label, ok, info = fut.result()
            print(f"  [{'ok ' if ok else 'FAIL'}] {label}  {info}", file=sys.stderr)
            failures += 0 if ok else 1

    print(f"Done. {len(tasks) - failures}/{len(tasks)} succeeded.", file=sys.stderr)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
