#!/usr/bin/env python3
"""Rehearse the add-a-pattern procedure and prove each safety net fires in order.

This is a meta-eval: it does not test the scanner, it tests the *process* that keeps
the scanner honest. In a throwaway copy of the repo it walks a careless executor
through adding a banned phrase and checks that, at every step, the guard that is
supposed to catch a mistake actually does:

  step 1  add the scanner entry with NO eval row      -> coverage gate exits 1
  step 2  add the false-negative row                  -> coverage passes, parity exits 1
  step 3  add the catalog line                        -> parity passes, the row runs green
  step 4  delete the scanner entry, keep the row      -> the row goes red

If a future refactor silently disables the coverage gate, catalog parity, or the
runner, one of these steps stops behaving and this kata (wired as DOC-10) turns red.

Run:  python3 evals/kata_add_pattern.py --run
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHRASE = "synergistic paradigm"
CATEGORY = "test_kata"
KATA_ID = "KATA-01"

SCANNER_LINE = (
    f'    "{PHRASE}": {{"category": "{CATEGORY}", "severity": "hard", "suggestion": None}},\n'
)


def run(tmp, *cmd):
    proc = subprocess.run(
        ["python3", *cmd],
        capture_output=True,
        text=True,
        cwd=tmp,
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def add_scanner_entry(tmp):
    scanner = tmp / "scripts" / "banned_phrase_scan.py"
    lines = scanner.read_text().splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("BANNED_PHRASES") and line.rstrip().endswith("{"):
            lines.insert(i + 1, SCANNER_LINE)
            scanner.write_text("".join(lines))
            return
    raise AssertionError("could not find BANNED_PHRASES opening in the temp scanner")


def remove_scanner_entry(tmp):
    scanner = tmp / "scripts" / "banned_phrase_scan.py"
    text = scanner.read_text()
    assert SCANNER_LINE in text, "scanner entry missing when trying to remove it"
    scanner.write_text(text.replace(SCANNER_LINE, "", 1))


def add_fn_row(tmp):
    suite_path = tmp / "evals" / "adversarial-evals.json"
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    suite["evals"].append({
        "id": KATA_ID,
        "category": "scanner_false_negative",
        "title": f"Kata: '{PHRASE}' flags",
        "target": "script",
        "command": ["python3", "scripts/banned_phrase_scan.py"],
        "stdin": f"The team promised a {PHRASE} would fix everything.",
        "failure_mode": "throwaway kata pattern",
        "correct_behavior": "flagged",
        "assertions": [
            {"type": "json", "path": "total_violations", "gte": 1},
            {"type": "violation_phrase_contains", "value": PHRASE},
        ],
    })
    suite_path.write_text(json.dumps(suite, indent=2, ensure_ascii=False), encoding="utf-8")


def add_catalog_line(tmp):
    catalog = tmp / "references" / "taboo-phrases.md"
    catalog.write_text(catalog.read_text() + f"\n- {PHRASE}\n")


def kata(verbose=True):
    tmp = Path(tempfile.mkdtemp(prefix="unslop-kata-"))
    log = []

    def say(msg):
        log.append(msg)
        if verbose:
            print(msg)

    try:
        for sub in ("scripts", "evals", "references"):
            shutil.copytree(ROOT / sub, tmp / sub)
        say("[setup] temp repo created")

        results = []

        # ---- step 1: scanner entry, no eval row -----------------------------
        add_scanner_entry(tmp)
        rc, out, _ = run(tmp, "evals/check_pattern_coverage.py", "--coverage")
        ok1 = rc == 1 and PHRASE in out
        results.append(ok1)
        say(f"[step 1] scanner entry, no row -> coverage exit {rc} "
            f"(expect 1, mentions phrase={PHRASE in out}): {'OK' if ok1 else 'FAIL'}")

        # ---- step 2: add the FN row -----------------------------------------
        add_fn_row(tmp)
        rc_cov, _, _ = run(tmp, "evals/check_pattern_coverage.py", "--coverage")
        rc_par, _, _ = run(tmp, "evals/check_taboo_parity.py")
        ok2 = rc_cov == 0 and rc_par == 1
        results.append(ok2)
        say(f"[step 2] add FN row -> coverage exit {rc_cov} (expect 0), "
            f"parity exit {rc_par} (expect 1): {'OK' if ok2 else 'FAIL'}")

        # ---- step 3: add the catalog line -----------------------------------
        add_catalog_line(tmp)
        rc_par2, _, _ = run(tmp, "evals/check_taboo_parity.py")
        rc_row, out_row, _ = run(tmp, "evals/run_adversarial.py", "--only", "KATA")
        ok3 = rc_par2 == 0 and rc_row == 0
        results.append(ok3)
        say(f"[step 3] add catalog line -> parity exit {rc_par2} (expect 0), "
            f"KATA row exit {rc_row} (expect 0): {'OK' if ok3 else 'FAIL'}")

        # ---- step 4: remove scanner entry, keep the row ---------------------
        remove_scanner_entry(tmp)
        rc_row2, _, _ = run(tmp, "evals/run_adversarial.py", "--only", "KATA")
        ok4 = rc_row2 == 1
        results.append(ok4)
        say(f"[step 4] drop scanner entry, keep row -> KATA row exit {rc_row2} "
            f"(expect 1, row now red): {'OK' if ok4 else 'FAIL'}")

        passed = all(results)
        say(f"[result] {sum(results)}/4 safety nets fired -> {'PASS' if passed else 'FAIL'}")
        return passed, log
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv):
    parser = argparse.ArgumentParser(description="Add-a-pattern kata (meta-eval).")
    parser.add_argument("--run", action="store_true", help="run the kata")
    args = parser.parse_args(argv)
    if not args.run:
        parser.print_help()
        return 0
    passed, _ = kata(verbose=True)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
