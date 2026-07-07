#!/usr/bin/env python3
"""Live ``--generate-cmd`` adapter for evals/run_structure_climb.py.

Reads an assembled climb prompt on stdin, calls one model, writes the model's
prose to stdout. Reuses run_model_parity's model-call plumbing so the climb's
live path spans the same Anthropic (claude-cli) and OpenRouter (GPT + open-weights)
spectrums as the recorded parity matrix, plus a ``codex`` kind for the local
Codex CLI (OpenAI's agentic coding CLI, driven non-interactively via
``codex exec``).

  python3 evals/model_generate.py --kind claude-cli  --model claude-3-5-haiku-latest
  python3 evals/model_generate.py --kind openrouter  --model openai/gpt-5.5
  python3 evals/model_generate.py --kind openrouter  --model z-ai/glm-5.2
  python3 evals/model_generate.py --kind codex       --model gpt-5.5
  python3 evals/model_generate.py --kind codex       --model gpt-5.4-mini

Exit 0 on a usable response, 1 on any model/network/key/CLI error (which aborts
the climb honestly rather than silently shipping an empty draft). claude-cli
can also be driven natively (``--generate-cmd "claude -p --model <id>"``);
this adapter exists for the OpenRouter models (need the keychain POST
wrapper) and for codex (needs output extraction, see ``call_codex`` below).

Codex extraction. ``codex exec`` is an AGENT CLI: its stdout is an interleaved
transcript (tool calls, hook lines, token counts), not a clean document. The
clean-extraction path is ``--output-last-message FILE`` (``-o FILE``), which
writes ONLY the agent's final text turn to a file with no wrapping -- verified
by hand against this repo's SKILL-MACRO-01 fixture (a coding-agent prompt
correctly returns bare prose, no markdown fence, no preamble). ``call_codex``
runs read-only/ephemeral (no repo mutation, no persisted session) and reads
that file instead of parsing stdout. KNOWN RISK: codex exec has been observed
to hang silently in this environment (stuck MCP/tool call with no output and
no exit). ``call_codex`` therefore runs the subprocess in its own process
group and enforces a hard wall-clock timeout, SIGKILLing the whole group on
expiry -- a hang is reported as a normal (None, error) failure, not a stuck
process, so the climb loop aborts the round honestly instead of blocking
forever.
"""

import argparse
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_model_parity as parity  # noqa: E402

CODEX_DEFAULT_TIMEOUT = 180


def call_codex(model_id, prompt, timeout=CODEX_DEFAULT_TIMEOUT):
    """Call the local Codex CLI (``codex exec``) and return its final message.

    Uses ``--output-last-message FILE`` to get the agent's clean prose turn
    instead of parsing the interleaved tool/hook transcript on stdout.
    ``--sandbox read-only --ephemeral --skip-git-repo-check`` keep the call a
    pure text-generation request: no repo writes, no persisted session, no
    git-repo requirement. A hard timeout (own process group, SIGKILL on
    expiry) turns a silent hang into an honest (None, error) result instead of
    blocking the climb loop forever.
    """
    fd, out_path = tempfile.mkstemp(prefix="codex_out_", suffix=".txt")
    os.close(fd)
    cmd = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only",
           "--ephemeral", "-o", out_path]
    if model_id:
        cmd += ["-m", model_id]
    cmd.append("-")  # read the prompt from stdin
    try:
        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, start_new_session=True,
            )
        except (FileNotFoundError, OSError) as e:
            return None, f"codex cli error: {e}"
        try:
            _, stderr = proc.communicate(input=prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            return None, f"codex exec timed out after {timeout}s (treated as a hang; round failed)"
        if proc.returncode != 0:
            return None, f"codex exec exit {proc.returncode}: {stderr.strip()[:300]}"
        text = Path(out_path).read_text(errors="replace") if Path(out_path).exists() else ""
        if not text.strip():
            return None, "codex exec exited 0 but --output-last-message was empty"
        return text, None
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


def main(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kind", required=True, choices=["claude-cli", "openrouter", "codex"])
    p.add_argument("--model", required=True)
    p.add_argument("--timeout", type=int, default=CODEX_DEFAULT_TIMEOUT,
                   help="codex kind only: hard wall-clock timeout in seconds (default 180)")
    args = p.parse_args(argv)

    prompt = sys.stdin.read()
    if args.kind == "claude-cli":
        text, err = parity.call_claude_cli(args.model, prompt)
    elif args.kind == "openrouter":
        text, err = parity.call_openrouter(args.model, prompt)
    else:
        text, err = call_codex(args.model, prompt, timeout=args.timeout)

    if err or text is None:
        sys.stderr.write(f"model_generate ({args.kind}/{args.model}) failed: {err}\n")
        return 1
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
