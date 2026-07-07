#!/usr/bin/env python3
"""Deterministic stand-in for the real ``codex`` binary, used offline to test
``evals/model_generate.py``'s ``call_codex`` extraction/timeout logic (CLIMB-07)
without invoking the real Codex CLI or any network.

Parses just enough of ``codex exec ... -o OUT_PATH [-m MODEL] -`` to find the
``-o`` output path, then behaves per ``FAKE_CODEX_MODE``:

  success  read stdin, write a derived line to OUT_PATH, exit 0
  empty    exit 0 but never write OUT_PATH (simulates an empty last-message)
  fail     write to stderr, exit 2, never write OUT_PATH
  hang     sleep far longer than any test timeout (simulates the known-risk
           silent hang; the caller's hard timeout must SIGKILL this process)
"""

import os
import sys
import time


def main(argv):
    out_path = None
    for i, a in enumerate(argv):
        if a == "-o" and i + 1 < len(argv):
            out_path = argv[i + 1]

    mode = os.environ.get("FAKE_CODEX_MODE", "success")

    if mode == "hang":
        time.sleep(600)
        return 0

    stdin_text = sys.stdin.read()

    if mode == "fail":
        sys.stderr.write("fake_codex: simulated exec failure\n")
        return 2

    if mode == "empty":
        return 0

    if out_path:
        with open(out_path, "w") as f:
            f.write(f"fake codex reply to: {stdin_text.strip()[:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
