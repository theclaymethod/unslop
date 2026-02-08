#!/usr/bin/env python3
"""
Sync unslop rules with Wikipedia's "Signs of AI writing" page.

Fetches the latest revision, parses structured data from wikitext,
and outputs diffs or integration prompts for Claude Code.

Subcommands:
    check  - Check for updates (exits 0 if no updates, 1 if updates available)
    diff   - Output structured JSON diff of changes since last sync
    prompt - Output a Claude Code integration prompt with mapped changes

Usage:
    python wiki_sync.py check
    python wiki_sync.py diff
    python wiki_sync.py prompt
    python wiki_sync.py prompt | claude -p --allowedTools Edit,Read,Grep,Glob,Bash
"""

import hashlib
import json
import re
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from typing import TypedDict

STATE_FILE = Path(__file__).parent / ".wiki_sync_state.json"
WIKI_PAGE = "Wikipedia:Signs_of_AI_writing"
API_URL = "https://en.wikipedia.org/w/api.php"


class SyncState(TypedDict):
    last_revision_id: int
    last_timestamp: str
    content_hash: str
    last_content_snapshot: str


class ParsedSection(TypedDict):
    title: str
    level: int
    content: str
    watch_words: list[str]
    examples: list[str]


class Change(TypedDict):
    type: str  # "new_section", "new_words", "modified", "removed"
    section: str
    details: str
    words: list[str]


def fetch_latest_revision() -> tuple[int, str, str]:
    """Fetch the latest revision content from Wikipedia.

    Returns (revision_id, timestamp, wikitext).
    """
    params = {
        "action": "query",
        "titles": WIKI_PAGE,
        "prop": "revisions",
        "rvslots": "*",
        "rvprop": "ids|timestamp|content",
        "format": "json",
        "formatversion": "2",
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "unslop-wiki-sync/1.0"})

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    page = data["query"]["pages"][0]
    if "missing" in page:
        print(f"Error: Page '{WIKI_PAGE}' not found.", file=sys.stderr)
        sys.exit(2)

    revision = page["revisions"][0]
    rev_id = revision["revid"]
    timestamp = revision["timestamp"]
    content = revision["slots"]["main"]["content"]
    return rev_id, timestamp, content


def load_state() -> SyncState | None:
    if not STATE_FILE.exists():
        return None
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(rev_id: int, timestamp: str, content: str) -> None:
    state: SyncState = {
        "last_revision_id": rev_id,
        "last_timestamp": timestamp,
        "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        "last_content_snapshot": content,
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def parse_wikitext(wikitext: str) -> list[ParsedSection]:
    """Parse wikitext into structured sections with watch words and examples."""
    sections: list[ParsedSection] = []
    current_title = "Introduction"
    current_level = 1
    current_lines: list[str] = []

    for line in wikitext.split("\n"):
        header_match = re.match(r"^(={2,6})\s*(.+?)\s*\1\s*$", line)
        if header_match:
            if current_lines:
                sections.append(_build_section(current_title, current_level, current_lines))
            current_level = len(header_match.group(1))
            current_title = header_match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append(_build_section(current_title, current_level, current_lines))

    return sections


def _build_section(title: str, level: int, lines: list[str]) -> ParsedSection:
    """Build a ParsedSection from raw lines."""
    content = "\n".join(lines).strip()
    watch_words = _extract_watch_words(content)
    examples = _extract_examples(content)
    return {
        "title": title,
        "level": level,
        "content": content,
        "watch_words": watch_words,
        "examples": examples,
    }


def _extract_watch_words(content: str) -> list[str]:
    """Extract words-to-watch from tmbox templates and bold/italic markers."""
    words: list[str] = []

    # Match {{tmbox|text=...}} content
    for match in re.finditer(r"\{\{tmbox\|[^}]*text\s*=\s*([^}]+)\}\}", content, re.DOTALL):
        text = match.group(1)
        # Extract bold words within tmbox
        for bold in re.finditer(r"'''(.+?)'''", text):
            words.append(bold.group(1).strip())

    # Match bold words in "words to watch" style lists
    for match in re.finditer(r"'''(.+?)'''", content):
        word = match.group(1).strip()
        if word and len(word) < 50:
            words.append(word)

    # Match items in bulleted lists
    for match in re.finditer(r"^\*\s*'''(.+?)'''", content, re.MULTILINE):
        words.append(match.group(1).strip())

    return list(dict.fromkeys(words))  # dedupe preserving order


def _extract_examples(content: str) -> list[str]:
    """Extract example blocks (blockquotes, textdiff templates)."""
    examples: list[str] = []

    # {{blockquote|...}}
    for match in re.finditer(r"\{\{blockquote\|([^}]+)\}\}", content, re.DOTALL):
        examples.append(match.group(1).strip())

    # {{textdiff|old=...|new=...}}
    for match in re.finditer(
        r"\{\{textdiff\|[^}]*old\s*=\s*([^|]+)\|[^}]*new\s*=\s*([^}]+)\}\}",
        content, re.DOTALL
    ):
        examples.append(f"BEFORE: {match.group(1).strip()}\nAFTER: {match.group(2).strip()}")

    # Indented blockquote lines (: prefix in wikitext)
    block_lines: list[str] = []
    for line in content.split("\n"):
        if line.startswith(":"):
            block_lines.append(line.lstrip(": "))
        elif block_lines:
            examples.append("\n".join(block_lines))
            block_lines = []
    if block_lines:
        examples.append("\n".join(block_lines))

    return examples


def compute_diff(old_sections: list[ParsedSection], new_sections: list[ParsedSection]) -> list[Change]:
    """Compute structured diff between two parsed page versions."""
    changes: list[Change] = []

    old_by_title = {s["title"]: s for s in old_sections}
    new_by_title = {s["title"]: s for s in new_sections}

    for title, new_sec in new_by_title.items():
        if title not in old_by_title:
            changes.append({
                "type": "new_section",
                "section": title,
                "details": f"New section with {len(new_sec['watch_words'])} watch words",
                "words": new_sec["watch_words"],
            })
        else:
            old_sec = old_by_title[title]
            new_words = set(new_sec["watch_words"]) - set(old_sec["watch_words"])
            if new_words:
                changes.append({
                    "type": "new_words",
                    "section": title,
                    "details": f"{len(new_words)} new watch words added",
                    "words": sorted(new_words),
                })

            old_hash = hashlib.sha256(old_sec["content"].encode()).hexdigest()
            new_hash = hashlib.sha256(new_sec["content"].encode()).hexdigest()
            if old_hash != new_hash and not new_words:
                changes.append({
                    "type": "modified",
                    "section": title,
                    "details": "Section content changed (no new watch words)",
                    "words": [],
                })

    for title in old_by_title:
        if title not in new_by_title:
            changes.append({
                "type": "removed",
                "section": title,
                "details": "Section removed from Wikipedia page",
                "words": old_by_title[title]["watch_words"],
            })

    return changes


# Mapping from Wikipedia section themes to unslop target files/sections
SECTION_MAP: dict[str, dict[str, str]] = {
    "words to watch": {
        "file": "references/taboo-phrases.md",
        "section": "AI Vocabulary (Additional)",
    },
    "promotional": {
        "file": "references/taboo-phrases.md",
        "section": "Promotional Language",
    },
    "significance": {
        "file": "references/taboo-phrases.md",
        "section": "Significance & Legacy Inflation",
    },
    "legacy": {
        "file": "references/taboo-phrases.md",
        "section": "Significance & Legacy Inflation",
    },
    "vague": {
        "file": "references/taboo-phrases.md",
        "section": "Vague Attributions",
    },
    "attribution": {
        "file": "references/taboo-phrases.md",
        "section": "Vague Attributions",
    },
    "copula": {
        "file": "references/taboo-phrases.md",
        "section": "Copula Avoidance",
    },
    "participial": {
        "file": "references/taboo-phrases.md",
        "section": "Superficial -ing Analyses",
    },
    "chatbot": {
        "file": "references/taboo-phrases.md",
        "section": "Communication Artifacts",
    },
    "jargon": {
        "file": "references/taboo-phrases.md",
        "section": "Business Jargon",
    },
    "structure": {
        "file": "references/taboo-phrases.md",
        "section": "Structural Patterns to Avoid",
    },
    "synonym": {
        "file": "references/taboo-phrases.md",
        "section": "Elegant Variation / Synonym Cycling",
    },
}


def map_change_to_target(change: Change) -> dict[str, str]:
    """Map a Wikipedia change to the appropriate unslop file and section."""
    section_lower = change["section"].lower()
    for keyword, target in SECTION_MAP.items():
        if keyword in section_lower:
            return target
    return {
        "file": "references/taboo-phrases.md",
        "section": "AI Vocabulary (Additional)",
    }


def generate_prompt(changes: list[Change], sections: list[ParsedSection]) -> str:
    """Generate a Claude Code integration prompt from detected changes."""
    if not changes:
        return "No changes detected since last sync. Nothing to integrate."

    lines = [
        "# Wikipedia AI Writing Patterns — Integration Update",
        "",
        "The Wikipedia 'Signs of AI writing' page has been updated.",
        "Below are changes that need to be integrated into the unslop skill.",
        "",
        "## Changes Detected",
        "",
    ]

    for i, change in enumerate(changes, 1):
        target = map_change_to_target(change)
        lines.append(f"### {i}. [{change['type'].upper()}] {change['section']}")
        lines.append(f"")
        lines.append(f"**Details:** {change['details']}")
        lines.append(f"**Target file:** `{target['file']}`")
        lines.append(f"**Target section:** {target['section']}")
        if change["words"]:
            lines.append(f"**Words/phrases to add:**")
            for word in change["words"]:
                lines.append(f"- \"{word}\"")
        lines.append("")

    lines.extend([
        "## Integration Instructions",
        "",
        "For each change above:",
        "",
        "1. Read the target file",
        "2. Check if the phrase already exists (avoid duplicates)",
        "3. Add new phrases to the appropriate section in `references/taboo-phrases.md`",
        "4. Mirror additions in `scripts/banned_phrase_scan.py` BANNED_PHRASES dict",
        "5. If a new before/after example is warranted, add to `references/edit-library.md`",
        "",
        "After all changes:",
        "- Run `python3 scripts/banned_phrase_scan.py < /dev/null` to verify no syntax errors",
        "- Verify no duplicate entries in taboo-phrases.md",
    ])

    return "\n".join(lines)


def cmd_check() -> None:
    """Check for updates. Exit 0 = no updates, 1 = updates available."""
    rev_id, timestamp, content = fetch_latest_revision()
    state = load_state()

    content_hash = hashlib.sha256(content.encode()).hexdigest()

    if state is None:
        print(f"No previous sync state. Current revision: {rev_id} ({timestamp})")
        print("Run 'diff' or 'prompt' to see all content as new.")
        sys.exit(1)

    if content_hash == state["content_hash"]:
        print(f"No changes. Current revision: {rev_id} ({timestamp})")
        print(f"Last synced revision: {state['last_revision_id']} ({state['last_timestamp']})")
        sys.exit(0)

    print(f"Updates available!")
    print(f"  Last synced: revision {state['last_revision_id']} ({state['last_timestamp']})")
    print(f"  Current:     revision {rev_id} ({timestamp})")
    sys.exit(1)


def cmd_diff() -> None:
    """Output structured JSON diff of changes."""
    rev_id, timestamp, content = fetch_latest_revision()
    state = load_state()

    new_sections = parse_wikitext(content)

    if state is None:
        old_sections: list[ParsedSection] = []
    else:
        old_sections = parse_wikitext(state["last_content_snapshot"])

    changes = compute_diff(old_sections, new_sections)

    output = {
        "revision_id": rev_id,
        "timestamp": timestamp,
        "previous_revision_id": state["last_revision_id"] if state else None,
        "total_changes": len(changes),
        "changes": changes,
    }

    print(json.dumps(output, indent=2))
    save_state(rev_id, timestamp, content)


def cmd_prompt() -> None:
    """Output a Claude Code integration prompt."""
    rev_id, timestamp, content = fetch_latest_revision()
    state = load_state()

    new_sections = parse_wikitext(content)

    if state is None:
        old_sections: list[ParsedSection] = []
    else:
        old_sections = parse_wikitext(state["last_content_snapshot"])

    changes = compute_diff(old_sections, new_sections)
    prompt = generate_prompt(changes, new_sections)

    print(prompt)
    save_state(rev_id, timestamp, content)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: wiki_sync.py <check|diff|prompt>", file=sys.stderr)
        sys.exit(2)

    command = sys.argv[1]
    commands = {
        "check": cmd_check,
        "diff": cmd_diff,
        "prompt": cmd_prompt,
    }

    if command not in commands:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(f"Available: {', '.join(commands)}", file=sys.stderr)
        sys.exit(2)

    commands[command]()


if __name__ == "__main__":
    main()
