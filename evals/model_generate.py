#!/usr/bin/env python3
"""Live ``--generate-cmd`` adapter for evals/run_structure_climb.py.

Reads an assembled climb prompt on stdin, calls one model, writes the model's
prose to stdout. Reuses run_model_parity's model-call plumbing so the climb's
live path spans the same Anthropic (claude-cli) and OpenRouter (GPT + open-weights)
spectrums as the recorded parity matrix.

  python3 evals/model_generate.py --kind claude-cli  --model claude-3-5-haiku-latest
  python3 evals/model_generate.py --kind openrouter  --model openai/gpt-5.5
  python3 evals/model_generate.py --kind openrouter  --model z-ai/glm-5.2

Exit 0 on a usable response, 1 on any model/network/key error (which aborts the
climb honestly rather than silently shipping an empty draft). claude-cli can also
be driven natively (``--generate-cmd "claude -p --model <id>"``); this adapter
exists for the OpenRouter models, which need the keychain POST wrapper.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_model_parity as parity  # noqa: E402


def main(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kind", required=True, choices=["claude-cli", "openrouter"])
    p.add_argument("--model", required=True)
    args = p.parse_args(argv)

    prompt = sys.stdin.read()
    if args.kind == "claude-cli":
        text, err = parity.call_claude_cli(args.model, prompt)
    else:
        text, err = parity.call_openrouter(args.model, prompt)

    if err or text is None:
        sys.stderr.write(f"model_generate ({args.kind}/{args.model}) failed: {err}\n")
        return 1
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
