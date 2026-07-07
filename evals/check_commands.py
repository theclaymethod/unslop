#!/usr/bin/env python3
"""Parity gate for the subcommand router.

Pins the top-level verb surface and keeps SKILL.md's argument-hint, its routing
table, and the files under references/commands/ in exact agreement. A future edit
cannot silently add or drop a verb, orphan a command file, or leave a routed
command without a file.

Checks:
  (a) argument-hint top-level verbs == EXPECTED_TOPLEVEL, exactly.
  (b) every routing-table link resolves to a references/commands/<cmd>.md file,
      and every such file is linked from the routing table (no orphans).
  (c) every top-level verb is routed; any extra routed command is an allowed
      maintenance command.
  (d) each command file is <= MAX_LINES lines.
  (e) each command file's first line is `# /unslop <cmd>`.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _check_support import ROOT  # noqa: E402

SKILL = ROOT / "SKILL.md"
COMMANDS_DIR = ROOT / "references" / "commands"

# The pinned four-verb surface. A change here is a deliberate product decision,
# never an accident of editing SKILL.md.
EXPECTED_TOPLEVEL = {"teach", "cleanup", "rewrite", "mimic"}
# Command files reachable as maintenance paths, not top-level verbs.
ALLOWED_MAINTENANCE = {"contribute"}
MAX_LINES = 90


def argument_hint_verbs(text: str) -> set[str]:
    """Top-level verbs from the frontmatter argument-hint's first [...] group."""
    m = re.search(r'^argument-hint:\s*"(.*?)"\s*$', text, re.M)
    if not m:
        raise RuntimeError("no argument-hint field in SKILL.md frontmatter")
    group = re.search(r"\[(.*?)\]", m.group(1))
    if not group:
        raise RuntimeError("argument-hint has no [...] command group")
    verbs = set()
    for chunk in group.group(1).split("·"):
        for tok in chunk.split("|"):
            tok = tok.strip()
            if tok:
                verbs.add(tok)
    return verbs


def routing_table_commands(text: str) -> set[str]:
    """Commands linked as references/commands/<cmd>.md anywhere in SKILL.md."""
    return set(re.findall(r"references/commands/([a-z0-9_-]+)\.md", text))


def command_files() -> set[str]:
    return {p.stem for p in COMMANDS_DIR.glob("*.md")}


def main() -> int:
    problems = []
    text = SKILL.read_text(encoding="utf-8")

    hint = argument_hint_verbs(text)
    if hint != EXPECTED_TOPLEVEL:
        problems.append(
            f"argument-hint verbs {sorted(hint)} != pinned surface "
            f"{sorted(EXPECTED_TOPLEVEL)}"
        )

    routed = routing_table_commands(text)
    files = command_files()

    for cmd in sorted(routed - files):
        problems.append(f"routing table links '{cmd}' but references/commands/{cmd}.md is missing")
    for cmd in sorted(files - routed):
        problems.append(f"references/commands/{cmd}.md exists but is not in the routing table (orphan)")

    for cmd in sorted(EXPECTED_TOPLEVEL - routed):
        problems.append(f"top-level verb '{cmd}' is not in the routing table")

    extras = routed - EXPECTED_TOPLEVEL
    for cmd in sorted(extras - ALLOWED_MAINTENANCE):
        problems.append(f"routed command '{cmd}' is neither a top-level verb nor an allowed maintenance path")

    for path in sorted(COMMANDS_DIR.glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        n = len(lines)
        if n > MAX_LINES:
            problems.append(f"{path.name} is {n} lines (> {MAX_LINES})")
        expected_first = f"# /unslop {path.stem}"
        first = lines[0] if lines else ""
        if first.strip() != expected_first:
            problems.append(f"{path.name} first line is {first!r}, expected {expected_first!r}")

    # Synonym routing: the "Routing by phrase" table must exist, cover the
    # demoted flows, and every target must be a real command file (optionally
    # with a #section anchor).
    REQUIRED_SYNONYMS = {"audit", "harvest", "calibrate", "refine", "voice check"}
    skill_text = (ROOT / "SKILL.md").read_text()
    import re as _re
    syn_rows = _re.findall(r"^\| *([^|]+?) *\| *\[?references/commands/([a-z]+)\.md(#[a-z-]+)?",
                           skill_text[skill_text.find("Routing by phrase"):], _re.M) \
        if "Routing by phrase" in skill_text else []
    covered = {name.strip().strip('`').lower() for name, _, _ in syn_rows}
    for req in sorted(REQUIRED_SYNONYMS):
        if not any(req in c for c in covered):
            problems.append(f"synonym routing missing an entry covering {req!r}")
    for name, cmd, _ in syn_rows:
        if not (COMMANDS_DIR / f"{cmd}.md").exists():
            problems.append(f"synonym {name.strip()!r} routes to missing file {cmd}.md")

    if problems:
        print("command router parity FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"command router parity ok: {len(files)} files, {len(syn_rows)} synonyms, "
          f"top-level {sorted(EXPECTED_TOPLEVEL)}, maintenance {sorted(extras)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
