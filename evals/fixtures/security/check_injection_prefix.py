#!/usr/bin/env python3
"""Disguised Codex instruction wrappers must not enter harvested prose."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_samples  # noqa: E402


def prose(marker: str) -> str:
    sentence = (
        f"{marker} is a note I wrote while the kettle cooled and the window fogged. "
    )
    return sentence * 4


def user_line(text: str) -> str:
    return json.dumps(
        {
            "timestamp": "2026-06-20T18:00:04.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }
    )


def main() -> int:
    kept = prose("KEPT_MARKER_DELTA")
    literal = "# AGENTS.md instructions for /tmp/repo\n\n" + prose("LITERAL_MARKER_GAMMA")
    zwsp = "\u200b# AGENTS.md instructions for /tmp/repo\n\n" + prose("ZWSP_MARKER_ALPHA")
    folded = "<ENVIRONMENT_CONTEXT>\n" + prose("CASE_MARKER_BETA")
    with tempfile.TemporaryDirectory(prefix="unslop-inject-") as raw:
        path = Path(raw) / "session.jsonl"
        path.write_text(
            "\n".join(user_line(text) for text in (kept, literal, zwsp, folded)) + "\n",
            encoding="utf-8",
        )
        output, _code = harvest_samples.harvest(
            argparse.Namespace(
                sources=[str(path)],
                min_words=40,
                max_candidates=20,
                since=None,
                self_check_determinism=False,
            )
        )
    blob = json.dumps(output)
    status = (
        "injection "
        f"zwsp={'absent' if 'ZWSP_MARKER_ALPHA' not in blob else 'present'} "
        f"case={'absent' if 'CASE_MARKER_BETA' not in blob else 'present'} "
        f"literal={'absent' if 'LITERAL_MARKER_GAMMA' not in blob else 'present'} "
        f"kept={'yes' if 'KEPT_MARKER_DELTA' in blob else 'no'}"
    )
    print(status)
    return 0 if status == (
        "injection zwsp=absent case=absent literal=absent kept=yes"
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
