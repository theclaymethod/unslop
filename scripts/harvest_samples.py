#!/usr/bin/env python3
"""Harvest user-authored writing samples from transcripts and declared folders.

Adapters:
- claude-jsonl: JSONL transcript files with explicit user/assistant roles. Unknown
  schemas are skipped with a warning; authorship is never guessed.
- codex-jsonl: Codex CLI/Desktop session JSONL (~/.codex/sessions/YYYY/MM/DD/
  rollout-*.jsonl). Reads `event_msg` user_message text and user-role
  `response_item` message content; drops assistant/developer/tool rows and
  filters instruction-injection wrappers (AGENTS.md dumps, <environment_context>,
  and similar structural markers) that Codex injects into user-role turns.
- text-folder: directories containing .md/.txt files. These are user-authored by
  declaration, but still pass through the AI-contamination tripwire.

Adapter detection for .jsonl files is by content shape, not filename: each file
is peeked line-by-line until a recognizable claude-jsonl or codex-jsonl entry is
found. Files that never match either shape fall through to the claude-jsonl
parser's own "unknown schema" warning path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import banned_phrase_scan  # noqa: E402
import structure_scan  # noqa: E402


WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?")
SENTENCE_RE = re.compile(r"[.!?](?:\s|$)")
COMMAND_RE = re.compile(
    r"^\s*(?:/[\w-]+|(?:open|read|write|edit|fix|review|run|grep|search|cat|"
    r"sed|python3?|npm|git)\b.*(?:/[\w./-]+|--?\w+))",
    re.I,
)
TAG_RE = re.compile(r"<(?:system-reminder|[^>\s]+)[^>]*>[\s\S]*?</(?:system-reminder|[^>\s]+)>", re.I)
QUOTE_ASSISTANT_RE = re.compile(r"(?im)^\s*(?:>|you said:|assistant:|claude said:)")
FILLER_RE = re.compile(r"\b(?:um|uh)\b,?", re.I)
DATE_FLOOR = 0.0


def words(text: str) -> list[str]:
    return WORD_RE.findall(text)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normal_tokens(text: str) -> list[str]:
    return [w.lower() for w in words(text)]


def fivegrams(text: str) -> set[tuple[str, ...]]:
    toks = normal_tokens(text)
    return set(tuple(toks[i:i + 5]) for i in range(max(0, len(toks) - 4)))


def complete_sentence_count(text: str) -> int:
    return len(SENTENCE_RE.findall(text))


def extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return ""


def role_from_entry(entry: dict[str, Any]) -> str | None:
    msg = entry.get("message")
    role = msg.get("role") if isinstance(msg, dict) else None
    if role in {"user", "assistant"}:
        return role
    top = entry.get("type")
    if top in {"user", "assistant"}:
        return top
    return None


def message_text(entry: dict[str, Any]) -> str:
    msg = entry.get("message")
    if isinstance(msg, dict):
        return extract_text(msg.get("content"))
    return extract_text(entry.get("content"))


# Codex CLI/Desktop session envelopes: {"timestamp", "type", "payload"}. These are
# the top-level `type` values actually observed (and defensively allowed) in
# ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl. `user_message`/`agent_message` are
# not top-level types themselves -- they are `payload.type` values nested inside
# an `event_msg` envelope.
CODEX_TOP_TYPES = {"session_meta", "event_msg", "response_item", "turn_context", "compacted"}

# Structural markers Codex injects into user-role turns that are not the user's
# own writing: a repo's AGENTS.md dumped verbatim, the environment/skill/turn
# banners, or an explicit user-instructions wrapper. Filtering is by these
# prefixes (structure), never by guessing at content.
CODEX_INJECTION_PREFIXES = (
    "# AGENTS.md instructions for",
    "<environment_context>",
    "<user_instructions>",
    "<INSTRUCTIONS>",
    "<skill>",
    "<turn_aborted>",
)


def is_codex_envelope(entry: dict[str, Any]) -> bool:
    return entry.get("type") in CODEX_TOP_TYPES and isinstance(entry.get("payload"), dict)


def is_injection_wrapper(text: str) -> bool:
    return text.strip().startswith(CODEX_INJECTION_PREFIXES)


def detect_jsonl_adapter(path: Path) -> str:
    """Peek at a JSONL file's shape to pick claude-jsonl or codex-jsonl parsing.

    Falls back to claude-jsonl (which itself warns and skips truly unknown
    schemas) when neither shape is recognized in any line.
    """
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        if is_codex_envelope(entry):
            return "codex-jsonl"
        if role_from_entry(entry) is not None:
            return "claude-jsonl"
    return "claude-jsonl"


def strip_transcript_noise(text: str) -> str:
    text = TAG_RE.sub(" ", text)
    lines = []
    for line in text.splitlines():
        if re.match(r"^\s*>", line):
            continue
        lines.append(line)
    return normalize_text("\n".join(lines))


def is_quoted_assistant(text: str) -> bool:
    if QUOTE_ASSISTANT_RE.search(text):
        return True
    lowered = text.lower().strip()
    return lowered.startswith(("you wrote:", "your answer:", "your response:"))


def is_command_like(text: str) -> bool:
    stripped = text.strip()
    if COMMAND_RE.search(stripped):
        return True
    if len(words(stripped)) <= 8 and re.search(r"(^|\s)(?:/[\w./-]+|--?\w+)", stripped):
        return True
    return False


def dictated(text: str) -> bool:
    w = max(1, len(words(text)))
    fillers = FILLER_RE.findall(text)
    return len(fillers) >= 2 and len(fillers) / w > 0.035


def tripwire(text: str) -> bool:
    banned = banned_phrase_scan.scan_for_violations(text, include_quoted=True)
    structure = structure_scan.scan(text)
    categories = {v["category"] for v in banned}
    categories.update(f"struct:{f['metric']}" for f in structure["flags"])
    hard = any(v["severity"] == "hard" for v in banned)
    return hard or len(categories) >= 2


def source_date(entry: dict[str, Any]) -> str | None:
    raw = entry.get("timestamp") or entry.get("created_at")
    if not isinstance(raw, str):
        return None
    return raw


def parse_since(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def date_ok(date: str | None, since: datetime | None) -> bool:
    if not since or not date:
        return True
    try:
        return datetime.fromisoformat(date.replace("Z", "+00:00")).replace(tzinfo=None) >= since
    except ValueError:
        return True


def iter_claude_jsonl(path: Path, warnings: list[str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    candidates = []
    stats = {"authorship": 0}
    saw_known_schema = False
    for idx, line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            warnings.append(f"{path}: line {idx}: invalid JSON; skipping file")
            return [], stats
        if not isinstance(entry, dict):
            continue
        role = role_from_entry(entry)
        if role is None:
            continue
        saw_known_schema = True
        if role != "user":
            stats["authorship"] += 1
            continue
        text = message_text(entry)
        candidates.append({
            "text": text,
            "source": {
                "path": str(path),
                "line": idx,
                "message_index": idx,
                "date": source_date(entry),
                "adapter": "claude-jsonl",
            },
        })
    if not saw_known_schema:
        warnings.append(f"{path}: unknown jsonl schema; skipped")
        return [], stats
    return candidates, stats


def codex_message_texts(payload: dict[str, Any]) -> list[str]:
    """Text of a response_item message's content parts, keyed on the caller
    already having confirmed role=="user" -- the role check, not the content
    item's own `type` (input_text/output_text/...), is what gates authorship."""
    content = payload.get("content")
    if not isinstance(content, list):
        return []
    return [
        item["text"]
        for item in content
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    ]


def iter_codex_jsonl(path: Path, warnings: list[str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    candidates = []
    stats = {"authorship": 0, "instruction-injection": 0}
    saw_known_schema = False
    for idx, line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            warnings.append(f"{path}: line {idx}: invalid JSON; skipping file")
            return [], stats
        if not isinstance(entry, dict):
            continue
        if not is_codex_envelope(entry):
            continue
        saw_known_schema = True
        payload = entry["payload"]
        payload_type = payload.get("type")
        date = source_date(entry)

        # event_msg envelopes: only user_message/agent_message carry authored text.
        if entry.get("type") == "event_msg":
            if payload_type == "agent_message":
                stats["authorship"] += 1
            elif payload_type == "user_message":
                message = payload.get("message")
                if isinstance(message, str):
                    if is_injection_wrapper(message):
                        stats["instruction-injection"] += 1
                    else:
                        candidates.append({
                            "text": message,
                            "source": {
                                "path": str(path),
                                "line": idx,
                                "message_index": idx,
                                "date": date,
                                "adapter": "codex-jsonl",
                            },
                        })
            # task_started/task_complete/token_count/exec_command_end/etc: not
            # authored text at all -- skip without guessing.
            continue

        # response_item envelopes: only role=="user" messages are candidates;
        # reasoning/function_call/function_call_output/custom_tool_call* are
        # tool plumbing, never authored text.
        if entry.get("type") == "response_item" and payload_type == "message":
            role = payload.get("role")
            if role != "user":
                stats["authorship"] += 1
                continue
            texts = codex_message_texts(payload)
            if not texts:
                continue
            if any(is_injection_wrapper(t) for t in texts):
                stats["instruction-injection"] += 1
                continue
            candidates.append({
                "text": "\n".join(texts),
                "source": {
                    "path": str(path),
                    "line": idx,
                    "message_index": idx,
                    "date": date,
                    "adapter": "codex-jsonl",
                },
            })
            continue

        # session_meta (holds base_instructions), turn_context, compacted, and
        # any other response_item payload type: never harvest, never guess.
    if not saw_known_schema:
        warnings.append(f"{path}: unknown jsonl schema; skipped")
        return [], stats
    return candidates, stats


def iter_text_file(path: Path) -> list[dict[str, Any]]:
    return [{
        "text": path.read_text(errors="replace"),
        "source": {
            "path": str(path),
            "offset": 0,
            "adapter": "text-folder",
            "mtime": path.stat().st_mtime,
        },
    }]


def collect_sources(paths: list[Path], warnings: list[str]) -> tuple[list[dict[str, Any]], dict[str, int], bool]:
    raw = []
    stats = {"authorship": 0}
    missing = False
    for source in sorted(paths, key=lambda p: str(p)):
        if not source.exists():
            print(f"missing source: {source}", file=sys.stderr)
            missing = True
            continue
        files: list[Path]
        if source.is_dir():
            files = sorted(
                [p for p in source.rglob("*") if p.suffix.lower() in {".jsonl", ".md", ".txt"}],
                key=lambda p: str(p),
            )
        else:
            files = [source]
        for file in files:
            try:
                if file.suffix.lower() == ".jsonl":
                    adapter = detect_jsonl_adapter(file)
                    if adapter == "codex-jsonl":
                        items, sub = iter_codex_jsonl(file, warnings)
                    else:
                        items, sub = iter_claude_jsonl(file, warnings)
                    raw.extend(items)
                    for key, value in sub.items():
                        stats[key] = stats.get(key, 0) + value
                elif file.suffix.lower() in {".md", ".txt"}:
                    raw.extend(iter_text_file(file))
            except (OSError, UnicodeDecodeError) as e:
                warnings.append(f"{file}: unreadable ({e}); skipping")
                stats["unreadable"] = stats.get("unreadable", 0) + 1
    return raw, stats, missing


def apply_filters(raw: list[dict[str, Any]], min_words: int, since: datetime | None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {
        "authorship": 0,
        "length": 0,
        "fragment-share": 0,
        "command-likeness": 0,
        "duplication": 0,
        "quoted-assistant": 0,
        "since": 0,
    }
    kept = []
    previous: list[set[tuple[str, ...]]] = []
    for item in sorted(raw, key=lambda c: (c["source"]["path"], c["source"].get("line", c["source"].get("offset", 0)))):
        if not date_ok(item["source"].get("date"), since):
            stats["since"] += 1
            continue
        text = strip_transcript_noise(item["text"])
        if is_quoted_assistant(text):
            stats["quoted-assistant"] += 1
            continue
        if is_command_like(text):
            stats["command-likeness"] += 1
            continue
        count = len(words(text))
        if count < min_words:
            stats["length"] += 1
            continue
        if complete_sentence_count(text) < 2:
            stats["fragment-share"] += 1
            continue
        grams = fivegrams(text)
        if grams:
            dupe = False
            for old in previous:
                overlap = len(grams & old) / max(1, min(len(grams), len(old)))
                if overlap > 0.6:
                    dupe = True
                    break
            if dupe:
                stats["duplication"] += 1
                continue
            previous.append(grams)
        candidate = {
            "text": text,
            "source": item["source"],
            "words": count,
            "dictated": False,
        }
        if dictated(text):
            candidate["dictated"] = True
        if tripwire(text):
            candidate["suspect_ai"] = True
        kept.append(candidate)
    return kept, stats


def recency_value(candidate: dict[str, Any]) -> float:
    source = candidate.get("source", {})
    raw_date = source.get("date")
    if isinstance(raw_date, str):
        try:
            return datetime.fromisoformat(raw_date.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    raw_mtime = source.get("mtime")
    if isinstance(raw_mtime, int | float):
        return float(raw_mtime)
    path = source.get("path")
    if isinstance(path, str):
        try:
            return Path(path).stat().st_mtime
        except OSError:
            pass
    return DATE_FLOOR


def rank_candidates(candidates: list[dict[str, Any]], max_candidates: int) -> list[dict[str, Any]]:
    ranked = sorted(
        candidates,
        key=lambda c: (
            bool(c.get("suspect_ai")),
            -recency_value(c),
            c["source"]["path"],
            c["source"].get("line", c["source"].get("offset", 0)),
        ),
    )
    return ranked[:max_candidates]


def harvest(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    warnings: list[str] = []
    raw, auth_stats, missing = collect_sources([Path(s) for s in args.sources], warnings)
    candidates, stats = apply_filters(raw, args.min_words, parse_since(args.since))
    for key, value in auth_stats.items():
        stats[key] = stats.get(key, 0) + value
    output = {
        "candidates": rank_candidates(candidates, args.max_candidates),
        "drop_stats": {k: v for k, v in stats.items() if v},
        "warnings": warnings,
    }
    if args.self_check_determinism:
        output["deterministic"] = json.dumps(output, sort_keys=True) == json.dumps(output, sort_keys=True)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return output, 2 if missing else 0


def write_output(output: dict[str, Any], path: str) -> None:
    text = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if path == "-":
        print(text, end="")
        return
    target = Path(path)
    target.write_text(text)
    stats_path = target.with_name(target.stem + ".drop_stats.json")
    stats_path.write_text(json.dumps(output["drop_stats"], indent=2, sort_keys=True) + "\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", metavar="SOURCE")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--min-words", type=int, default=40)
    parser.add_argument("--max-candidates", type=int, default=200)
    parser.add_argument("--since")
    parser.add_argument("--self-check-determinism", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    output, code = harvest(args)
    write_output(output, args.output)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
