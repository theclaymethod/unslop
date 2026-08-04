#!/usr/bin/env python3
"""Content-hash stdin cache for ``skill-benchmark judge --judge-cmd``.

The harness invokes a shell judge command once per qualitative assertion and
passes the complete judge prompt on stdin. Caching that exact prompt keeps the
immutable ``without_skill`` verdicts stable while candidate skill outputs are
still judged live. The cache is opt-in and stores only successful, parseable
JSON responses.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


CACHE_SCHEMA = "judge-v1"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _extract_valid_verdict(raw: bytes) -> dict | None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        # The current UNSLOP benchmark uses the harness's plain binary-verdict
        # schema. Do not persist arbitrary provider JSON such as rate-limit or
        # authentication error objects merely because it parses.
        if isinstance(value, dict) and isinstance(value.get("passed"), bool):
            return value
    return None


def judge_cache_key(prompt: bytes, command: str, identity: str) -> tuple[str, dict]:
    payload = {
        "schema": CACHE_SCHEMA,
        "prompt_sha256": _sha256_bytes(prompt),
        "judge_cmd": command,
        "judge_identity": identity,
    }
    return _sha256_bytes(_canonical_json(payload).encode("utf-8")), payload


def _entry_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / CACHE_SCHEMA / f"{key}.json"


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


def _load(cache_dir: Path, key: str, payload: dict) -> bytes | None:
    path = _entry_path(cache_dir, key)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        output = base64.b64decode(record["stdout_b64"], validate=True)
    except (OSError, UnicodeError, ValueError, KeyError, json.JSONDecodeError):
        return None
    if (
        record.get("schema") != CACHE_SCHEMA
        or record.get("key") != key
        or record.get("key_payload") != payload
        or record.get("returncode") != 0
        or record.get("stdout_sha256") != _sha256_bytes(output)
        or _extract_valid_verdict(output) is None
    ):
        return None
    return output


def _save(cache_dir: Path, key: str, payload: dict, output: bytes) -> None:
    path = _entry_path(cache_dir, key)
    record = {
        "schema": CACHE_SCHEMA,
        "key": key,
        "key_payload": payload,
        "returncode": 0,
        "stdout_b64": base64.b64encode(output).decode("ascii"),
        "stdout_sha256": _sha256_bytes(output),
    }
    _atomic_write(path, (_canonical_json(record) + "\n").encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--identity", required=True, help="explicit judge model/provider identity")
    parser.add_argument("--judge-cmd", default="claude -p", help="shell command receiving the prompt on stdin")
    args = parser.parse_args()

    prompt = sys.stdin.buffer.read()
    cache_dir = Path(args.cache_dir).resolve()
    key, payload = judge_cache_key(prompt, args.judge_cmd, args.identity)
    cached = _load(cache_dir, key, payload)
    if cached is not None:
        sys.stdout.buffer.write(cached)
        return 0

    try:
        proc = subprocess.run(
            args.judge_cmd,
            shell=True,
            input=prompt,
            capture_output=True,
            check=False,
        )
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 127

    if proc.stdout:
        sys.stdout.buffer.write(proc.stdout)
    if proc.stderr:
        sys.stderr.buffer.write(proc.stderr)

    valid = proc.returncode == 0 and _extract_valid_verdict(proc.stdout) is not None
    if valid:
        _save(cache_dir, key, payload, proc.stdout)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
