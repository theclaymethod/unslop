#!/usr/bin/env python3
"""Offline contribution scaffolder for new unslop AI-isms."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRIB_ROOT = ROOT / ".unslop" / "contrib"
TODO_MARKER = "TODO:"

GATE_COMMANDS = [
    ["python3", "evals/run_adversarial.py", "--only", "CONTRIB"],
    ["python3", "evals/run_adversarial.py"],
    ["python3", "evals/build_shared_benchmark.py", "--check"],
    ["python3", "evals/check_taboo_parity.py"],
    ["python3", "evals/check_pattern_coverage.py"],
    ["python3", "evals/kata_add_pattern.py", "--run"],
]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(json.dumps({"error": f"could not read {path}: {exc}"}))
        raise SystemExit(2) from exc


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def shorten(text: str, limit: int = 72) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 1].rstrip() + "..."


def run_scanner(command: list[str], text: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, input=text, capture_output=True, text=True, cwd=ROOT, timeout=30)


def scanner_findings(text: str) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for name, command in (
        ("banned_phrase", ["python3", "scripts/banned_phrase_scan.py"]),
        ("structure", ["python3", "scripts/structure_scan.py"]),
    ):
        proc = run_scanner(command, text)
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            data = {}
        violations = data.get("violations", [])
        if name == "structure":
            violations = [
                {
                    "phrase": flag.get("metric", ""),
                    "category": flag.get("metric", ""),
                    "severity": flag.get("severity", ""),
                }
                for flag in data.get("flags", [])
            ]
        for violation in violations:
            findings.append(
                {
                    "scanner": name,
                    "phrase": violation.get("phrase", ""),
                    "category": violation.get("category", ""),
                    "severity": violation.get("severity", ""),
                }
            )
    return findings


def redaction_pairs(values: list[str]) -> list[tuple[str, str]]:
    pairs = []
    for value in values:
        if "=" not in value:
            print(json.dumps({"error": "--redact values must use orig=REPL"}))
            raise SystemExit(2)
        orig, repl = value.split("=", 1)
        pairs.append((orig, repl))
    return pairs


def apply_redactions(text: str, tell: str, pairs: list[tuple[str, str]]) -> str:
    before_count = text.count(tell)
    redacted = text
    for orig, repl in pairs:
        redacted = redacted.replace(orig, repl)
    if before_count == 0 or redacted.count(tell) != before_count:
        print(json.dumps({"error": "redaction alters the specimen", "tell": tell}))
        raise SystemExit(4)
    return redacted


def row_fn(slug: str, tell: str, snippet: str) -> dict[str, object]:
    assertion_tell = tell.casefold()
    return {
        "id": f"CONTRIB-FN-{slug}",
        "category": "scanner_false_negative",
        "title": f"New AI-ism fixture: {tell}",
        "target": "script",
        "command": ["python3", "scripts/banned_phrase_scan.py"],
        "stdin": snippet,
        "failure_mode": "The scanner misses the contributed tell from the exact specimen.",
        "correct_behavior": "The scanner reports at least one violation containing the contributed tell.",
        "assertions": [
            {"type": "json", "path": "total_violations", "gte": 1},
            {"type": "violation_phrase_contains", "value": assertion_tell},
        ],
    }


def row_fp_template(slug: str, category: str, tell: str) -> dict[str, object]:
    return {
        "id": f"CONTRIB-FP-{slug}",
        "category": "scanner_false_positive",
        "protects": category,
        "title": f"Literal-use protection for {tell}",
        "target": "script",
        "command": ["python3", "scripts/banned_phrase_scan.py"],
        "stdin": "TODO: add a literal or domain-specific use that should remain clean.",
        "failure_mode": "A broad pattern could flag legitimate prose.",
        "correct_behavior": "No violations for the protected literal/domain use.",
        "assertions": [{"type": "json", "path": "total_violations", "equals": 0}],
    }


def render_report(
    manifest: dict[str, object],
    snippet: str,
    gate_results: str = "",
    include_rec: bool = False,
) -> str:
    redactions = manifest.get("redactions", [])
    redaction_note = "names/numbers redacted; tell verbatim" if redactions else "none"
    rows = [
        f"| CONTRIB-FN-{manifest['pattern_name']} | FN | exact specimen flags `{manifest['tell']}` |",
        f"| CONTRIB-FP-{manifest['pattern_name']} | FP | literal-use protection for `{manifest['tell']}` |",
    ]
    if include_rec:
        rows.append("| CONTRIB-REC | REC | existing-word recall still flags |")
    quoted = "\n".join(f"> {line}" if line else ">" for line in snippet.splitlines())
    return (
        f"# Add {manifest['category']} pattern: {shorten(str(manifest['tell']))}\n\n"
        "## The specimen\n\n"
        f"{quoted}\n\n"
        f"- Source genre: {manifest.get('source_genre', 'TODO: source genre')}\n"
        f"- Date: {manifest['date']}\n"
        f"- Redaction note: {redaction_note}\n\n"
        "## Why it's an AI-ism\n\n"
        f"{manifest.get('rationale', 'TODO: explain why this phrase is a reusable AI-writing tell in 2-4 sentences.')}\n\n"
        "## Detection\n\n"
        f"- Pattern added: {manifest.get('pattern_added', f'TODO: regex or phrase for `{manifest['tell']}`')}\n"
        f"- Severity: {manifest.get('severity', 'TODO: hard or soft')}\n"
        f"- Gating rationale: {manifest.get('gating_rationale', 'TODO: explain literal-use boundary')}\n"
        "- Catalog entry location: references/taboo-phrases.md\n\n"
        "## Evals\n\n"
        "| row id | kind | what it pins |\n"
        "|---|---|---|\n"
        + "\n".join(rows)
        + "\n\n"
        "The FN stdin is the unmodified specimen after approved redaction.\n\n"
        "## Gate results\n\n"
        f"{gate_results or 'TODO: paste gate tails from verify.'}\n\n"
        "## Checklist\n\n"
        "- [ ] eval-first (row was red before the pattern)\n"
        "- [ ] literal-use FP row included\n"
        "- [ ] REC row if an existing word was gated\n"
        "- [ ] catalog + scanner parity green\n"
        "- [ ] coverage gate green (pattern exercised)\n"
        "- [ ] snippet publication approved by the user\n"
    )


def cmd_precheck(args: argparse.Namespace) -> int:
    snippet = read_text(Path(args.snippet_file))
    findings = scanner_findings(snippet)
    if findings:
        print(json.dumps({"status": "already_covered", "findings": findings}, indent=2, sort_keys=True))
        return 3
    print(json.dumps({"status": "clean", "words": word_count(snippet)}, indent=2, sort_keys=True))
    return 0


def cmd_scaffold(args: argparse.Namespace) -> int:
    source = Path(args.snippet)
    snippet = read_text(source)
    if args.tell not in snippet:
        print(json.dumps({"error": "tell substring not found", "tell": args.tell}))
        return 2
    try:
        manifest_date = datetime.strptime(args.date, "%Y-%m-%d").date().isoformat()
    except ValueError:
        print(json.dumps({"error": "--date must use YYYY-MM-DD", "date": args.date}))
        return 2
    redactions = redaction_pairs(args.redact or [])
    redacted = apply_redactions(snippet, args.tell, redactions)
    bundle = CONTRIB_ROOT / args.pattern_name
    bundle.mkdir(parents=True, exist_ok=True)
    manifest = {
        "category": args.category,
        "date": manifest_date,
        "pattern_name": args.pattern_name,
        "pre_redaction_sha256": sha256_text(snippet),
        "post_redaction_sha256": sha256_text(redacted),
        "redactions": [{"from": orig, "to": repl} for orig, repl in redactions],
        "tell": args.tell,
        "word_count": word_count(redacted),
    }
    write_json(bundle / "row_fn.json", row_fn(args.pattern_name, args.tell, redacted))
    write_json(bundle / "row_fp_TEMPLATE.json", row_fp_template(args.pattern_name, args.category, args.tell))
    write_json(bundle / "manifest.json", manifest)
    (bundle / "snippet.txt").write_text(redacted, encoding="utf-8")
    (bundle / "report.md").write_text(render_report(manifest, redacted), encoding="utf-8")
    print(json.dumps({"bundle": str(bundle.relative_to(ROOT)), "status": "scaffolded"}, indent=2, sort_keys=True))
    return 0


def run_row(row: dict[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        row["command"],
        input=str(row.get("stdin", "")),
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=30,
    )


def row_assertions_pass(row: dict[str, object], proc: subprocess.CompletedProcess[str]) -> bool:
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False
    for assertion in row.get("assertions", []):
        if assertion.get("type") == "json":
            cur = data
            for part in assertion["path"].split("."):
                cur = cur[int(part)] if isinstance(cur, list) else cur[part]
            if "gte" in assertion and not cur >= assertion["gte"]:
                return False
            if "equals" in assertion and cur != assertion["equals"]:
                return False
        elif assertion.get("type") == "violation_phrase_contains":
            phrases = [v.get("phrase", "") for v in data.get("violations", [])]
            needle = str(assertion["value"]).casefold()
            if not any(needle in str(phrase).casefold() for phrase in phrases):
                return False
        else:
            return False
    return True


def tail(text: str, lines: int = 12) -> str:
    split = text.splitlines()
    return "\n".join(split[-lines:])


def verify_bundle(bundle: Path, run_gates: bool = True) -> tuple[bool, str]:
    if not bundle.exists():
        return False, "missing bundle"
    row_path = bundle / "row_fn.json"
    report_path = bundle / "report.md"
    manifest_path = bundle / "manifest.json"
    snippet_path = bundle / "snippet.txt"
    for path in (row_path, report_path, manifest_path, snippet_path):
        if not path.exists():
            return False, f"missing {path.name}"
    report = report_path.read_text(encoding="utf-8")
    if TODO_MARKER in report:
        return False, "report contains TODO markers"
    row = json.loads(row_path.read_text(encoding="utf-8"))
    snippet = snippet_path.read_text(encoding="utf-8")
    if row.get("stdin") != snippet:
        return False, "row_fn stdin does not equal snippet.txt byte-for-byte"
    proc = run_row(row)
    assertion_ok = row_assertions_pass(row, proc)
    red_first = not assertion_ok
    gate_results = [f"red-first: {'ok' if red_first else 'already green'}"]
    ok = red_first
    if not red_first:
        ok = True
        gate_results[0] = "red-first: already green; proposed pattern appears active"
    if run_gates:
        for command in GATE_COMMANDS:
            proc = subprocess.run(command, capture_output=True, text=True, cwd=ROOT, timeout=120)
            gate_results.append(
                "### "
                + " ".join(command)
                + f"\n\n```text\nexit={proc.returncode}\n{tail(proc.stdout or proc.stderr)}\n```"
            )
            ok = ok and proc.returncode == 0
    final = "\n\n".join(gate_results)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report_path.write_text(render_report(manifest, snippet, final, (bundle / "row_rec.json").exists()), encoding="utf-8")
    return ok, final


def cmd_verify(args: argparse.Namespace) -> int:
    ok, message = verify_bundle(Path(args.bundle), run_gates=not args.no_gates)
    print(message)
    return 0 if ok else 1


def cmd_report(args: argparse.Namespace) -> int:
    bundle = Path(args.bundle)
    if not bundle.exists():
        print(json.dumps({"error": "missing bundle", "bundle": str(bundle)}))
        return 2
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    snippet = (bundle / "snippet.txt").read_text(encoding="utf-8")
    report = (bundle / "report.md").read_text(encoding="utf-8")
    gate_marker = "## Gate results\n\n"
    checklist_marker = "\n\n## Checklist"
    gate_results = ""
    if gate_marker in report and checklist_marker in report:
        gate_results = report.split(gate_marker, 1)[1].split(checklist_marker, 1)[0]
    print(render_report(manifest, snippet, gate_results, (bundle / "row_rec.json").exists()).rstrip())
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    precheck = sub.add_parser("precheck")
    precheck.add_argument("snippet_file")
    precheck.set_defaults(func=cmd_precheck)
    scaffold = sub.add_parser("scaffold")
    scaffold.add_argument("--snippet", required=True)
    scaffold.add_argument("--tell", required=True)
    scaffold.add_argument("--category", required=True)
    scaffold.add_argument("--pattern-name", required=True)
    scaffold.add_argument("--redact", action="append")
    scaffold.add_argument("--date", default=date.today().isoformat())
    scaffold.set_defaults(func=cmd_scaffold)
    verify = sub.add_parser("verify")
    verify.add_argument("--bundle", required=True)
    verify.add_argument("--no-gates", action="store_true")
    verify.set_defaults(func=cmd_verify)
    report = sub.add_parser("report")
    report.add_argument("--bundle", required=True)
    report.set_defaults(func=cmd_report)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
