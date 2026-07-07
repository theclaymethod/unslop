#!/usr/bin/env python3
"""Schema gate for evals/adversarial-evals.json.

evals/adversarial-evals.json is hand-merged and hand-numbered with no
validation: a duplicate id runs twice silently, a malformed row crashes at
runtime instead of failing the gate cleanly. This checker asserts the row
invariants without executing anything:

  (a) every id is unique
  (b) every id matches the pinned shape (PREFIX-NN, optional lowercase suffix)
  (c) every row has id/title/target, and target is "script" or "skill"
  (d) script rows: command is a non-empty list of strings, assertions is a
      non-empty list, and every assertion's type is one check_assertion() in
      evals/run_adversarial.py actually understands
  (e) skill rows: have the keys evals/build_shared_benchmark.py's loader
      reads off each source row, and each assertion is a judge assertion
      with a 'check' field (the only assertion shape that loader consumes)

Usage: python3 evals/check_evals_schema.py [path-to-suite.json]
Defaults to the real evals/adversarial-evals.json. Pass an alternate path to
run this against a mutated copy — useful for negative-testing the checker
itself against a suite with a deliberately broken row.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _check_support import ROOT  # noqa: E402

DEFAULT_SUITE = ROOT / "evals" / "adversarial-evals.json"
RUN_ADVERSARIAL = ROOT / "evals" / "run_adversarial.py"

# PREFIX-NN, PREFIX-PREFIX-NN, ..., with an optional lowercase letter suffix
# (LANG-3a). Verified against every id currently in adversarial-evals.json
# plus the incoming ENC-01/SLUG-01/REGX-01/WIKI-01/SPAN-01/DOC-24/LANG-20
# shapes from parallel plans.
ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*-\d+[a-z]?$")

# Keys build_shared_benchmark.py's to_case() reads off each skill source row
# (see its use of src["id"], src["category"], src["title"], src["prompt"],
# src["correct_behavior"], src["failure_mode"], src["assertions"] in
# evals/build_shared_benchmark.py).
SKILL_REQUIRED_KEYS = {
    "id", "title", "category", "prompt", "correct_behavior",
    "failure_mode", "assertions",
}

# The only assertion shape build_shared_benchmark.py's to_case() consumes
# from a skill source row: `if a["type"] == "judge": ... a["check"]`.
SKILL_ASSERTION_TYPES = {"judge"}


def script_assertion_types() -> set[str]:
    """Assertion types evals/run_adversarial.py's check_assertion() actually
    handles, extracted at runtime by regexing its `if t == "<type>":`
    comparisons — so if that function grows a new type without this checker
    being updated, extraction still tracks it instead of silently drifting."""
    src = RUN_ADVERSARIAL.read_text(encoding="utf-8")
    m = re.search(r"def check_assertion\(.*?\n(?=def |\Z)", src, re.S)
    body = m.group(0) if m else src
    return set(re.findall(r't == "([a-z_]+)"', body))


def load_suite(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))["evals"]


def main(argv) -> int:
    path = Path(argv[0]) if argv else DEFAULT_SUITE
    rows = load_suite(path)
    problems = []

    seen_ids = {}
    for i, row in enumerate(rows):
        rid = row.get("id")
        if rid is not None:
            seen_ids.setdefault(rid, []).append(i)
    for rid, idxs in sorted(seen_ids.items()):
        if len(idxs) > 1:
            problems.append(f"duplicate id: {rid!r} appears {len(idxs)} times (rows {idxs})")

    script_types = script_assertion_types()

    n_script = 0
    n_skill = 0

    for i, row in enumerate(rows):
        rid = row.get("id", f"<row {i}, no id>")

        missing_required = [k for k in ("id", "title", "target") if k not in row]
        if missing_required:
            problems.append(f"{rid}: missing required key(s) {missing_required}")

        if "id" in row and not ID_RE.match(row["id"]):
            problems.append(f"{rid}: id {row['id']!r} does not match shape {ID_RE.pattern}")

        target = row.get("target")
        if target not in ("script", "skill"):
            problems.append(f"{rid}: target {target!r} not in {{'script', 'skill'}}")
            continue

        if target == "script":
            n_script += 1
            command = row.get("command")
            if not isinstance(command, list) or not command or not all(isinstance(c, str) for c in command):
                problems.append(f"{rid}: command must be a non-empty list of strings, got {command!r}")
            assertions = row.get("assertions")
            if not isinstance(assertions, list) or not assertions:
                problems.append(f"{rid}: assertions must be a non-empty list")
            else:
                for a in assertions:
                    t = a.get("type") if isinstance(a, dict) else None
                    if t not in script_types:
                        problems.append(
                            f"{rid}: assertion type {t!r} not in script assertion set {sorted(script_types)}"
                        )
        else:  # skill
            n_skill += 1
            missing = sorted(SKILL_REQUIRED_KEYS - row.keys())
            if missing:
                problems.append(f"{rid}: skill row missing keys {missing}")
            assertions = row.get("assertions")
            if not isinstance(assertions, list) or not assertions:
                problems.append(f"{rid}: assertions must be a non-empty list")
            else:
                for a in assertions:
                    t = a.get("type") if isinstance(a, dict) else None
                    if t not in SKILL_ASSERTION_TYPES:
                        problems.append(
                            f"{rid}: assertion type {t!r} not in skill assertion set {sorted(SKILL_ASSERTION_TYPES)}"
                        )
                    elif "check" not in a:
                        problems.append(f"{rid}: judge assertion missing 'check' key")

    if problems:
        print(f"evals schema FAILED: {len(problems)} problem(s)")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"evals schema ok: {len(rows)} rows, {n_script} script, {n_skill} skill")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
