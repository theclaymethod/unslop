#!/usr/bin/env python3
"""Runner for the deterministic (target=="script") cases in adversarial-evals.json.

These cases encode the CORRECT behavior of the skill's Python scripts. Most are
currently marked `xfail: true` because they expose real bugs (false positives,
fact-preservation holes, crashes). The runner is a regression harness:

  - PASS         assertion holds (good)
  - FAIL         assertion broken and NOT marked xfail (a regression)
  - XFAIL        assertion broken as expected (documented bug, still open)
  - XPASS        assertion holds but was marked xfail (bug fixed -> drop xfail!)

Exit code is non-zero on FAIL, XPASS, or an unexpected XFAIL set. Run from the
skill root:  python3 evals/run_adversarial.py

Behavioral (target=="skill") cases are skipped here; they require an agent/LLM
judge. List them with --list-skill.
"""
import json
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITE = Path(__file__).resolve().parent / "adversarial-evals.json"
EXPECTED_XFAIL = {"FP-06"}

if sys.stdout.isatty():
    GREEN, RED, YELLOW, BLUE, DIM, RESET = (
        "\033[32m", "\033[31m", "\033[33m", "\033[34m", "\033[2m", "\033[0m"
    )
else:  # don't emit escape codes into pipes / CI logs
    GREEN = RED = YELLOW = BLUE = DIM = RESET = ""


def _dig(obj, path):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            part = int(part)
        cur = cur[part]
    return cur


def check_assertion(a, proc):
    """Return (ok, detail) for one assertion against a finished process."""
    t = a["type"]
    if t == "exit_code":
        return proc.returncode == a["equals"], f"exit={proc.returncode}"
    if t == "stdout_contains":
        return a["value"] in proc.stdout, "stdout"
    if t == "stdout_not_contains":
        return a["value"] not in proc.stdout, "stdout"
    if t == "stderr_not_contains":
        return a["value"] not in proc.stderr, "stderr"
    if t == "violation_phrase_contains":
        try:
            data = json.loads(proc.stdout)
            phrases = [v.get("phrase", "") for v in data.get("violations", [])]
        except Exception as e:  # noqa: BLE001
            return False, f"json error: {e}"
        return any(a["value"] in phrase for phrase in phrases), f"phrases={phrases}"
    if t == "violation_category_equals":
        try:
            data = json.loads(proc.stdout)
            categories = [v.get("category", "") for v in data.get("violations", [])]
        except Exception as e:  # noqa: BLE001
            return False, f"json error: {e}"
        return a["value"] in categories, f"categories={categories}"
    if t == "json":
        try:
            data = json.loads(proc.stdout)
            actual = _dig(data, a["path"])
        except Exception as e:  # noqa: BLE001
            return False, f"json error: {e}"
        if "equals" in a:
            return actual == a["equals"], f"{a['path']}={actual}"
        if "gte" in a:
            return actual >= a["gte"], f"{a['path']}={actual}"
        if "lte" in a:
            return actual <= a["lte"], f"{a['path']}={actual}"
        return False, "no comparator"
    return False, f"unknown assertion type {t}"


class _Failed:
    """Stand-in process result when the command never produced output."""
    def __init__(self, returncode, stderr):
        self.returncode = returncode
        self.stdout = ""
        self.stderr = stderr


def run_case(ev, timeout=30):
    try:
        proc = subprocess.run(
            ev["command"],
            input=ev.get("stdin", ""),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except (FileNotFoundError, OSError) as e:
        proc = _Failed(127, str(e))

    results = [check_assertion(a, proc) for a in ev["assertions"]]
    ok = all(r[0] for r in results)
    details = "; ".join(d for _, d in results)
    return ok, details


def list_gates():
    return [
        {
            "id": "adversarial-suite",
            "command": "python3 evals/run_adversarial.py",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "shared-benchmark-check",
            "command": "python3 evals/build_shared_benchmark.py --check",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "strict-leakage-validate",
            "command": "skill-benchmark validate evals/shared-benchmark.json --strict-leakage",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": ["skill-benchmark"],
        },
        {
            "id": "taboo-catalog-parity",
            "command": "python3 evals/check_taboo_parity.py",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "pattern-coverage",
            "command": "python3 evals/check_pattern_coverage.py",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "add-pattern-kata",
            "command": "python3 evals/kata_add_pattern.py --run",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "pack-structure",
            "command": "python3 scripts/check_packs.py",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "behavioral-tune",
            "command": "evals/run_behavioral.sh tune",
            "pass_criterion": "exit 0",
            "blocking": False,
            "needs": ["skill-benchmark", "claude -p"],
        },
        {
            "id": "banned-phrase-scan",
            "command": "python3 scripts/banned_phrase_scan.py < transformed.txt",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "structure-scan",
            "command": "python3 scripts/structure_scan.py < transformed.txt",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "validate-preservation",
            "command": "python3 scripts/validate_preservation.py original.txt transformed.txt",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "readability-metrics",
            "command": "python3 scripts/readability_metrics.py < transformed.txt",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "diff-check",
            "command": "python3 scripts/diff_check.py original.txt transformed.txt",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "rubric-judge",
            "command": "Judge transformed output against the skill rubric",
            "pass_criterion": "non-deterministic rubric pass",
            "blocking": False,
            "needs": ["rubric judge"],
        },
    ]


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Run deterministic unslop adversarial eval cases."
    )
    parser.add_argument(
        "--list-skill",
        action="store_true",
        help="list behavioral skill cases and exit",
    )
    parser.add_argument(
        "--list-gates",
        action="store_true",
        help="emit the deterministic gate matrix as JSON and exit",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="PREFIX",
        help="run only case IDs with this prefix; repeatable",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        metavar="ID",
        help="run only this exact case ID; repeatable",
    )
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    suite = json.loads(SUITE.read_text())
    evals = suite["evals"]
    script_cases = [e for e in evals if e.get("target") == "script"]
    skill_cases = [e for e in evals if e.get("target") == "skill"]

    if args.list_gates:
        print(json.dumps(list_gates(), indent=2))
        return 0

    if args.list_skill:
        print(f"\n{BLUE}Behavioral (skill) cases — run with evals/run_behavioral.sh SPLIT:{RESET}")
        for e in skill_cases:
            print(f"  {e['id']:24} [{e['category']}] {e['title']}")
        return 0

    if args.only:
        prefixes = tuple(args.only)
        script_cases = [e for e in script_cases if e["id"].startswith(prefixes)]
    if args.case:
        wanted = set(args.case)
        script_cases = [e for e in script_cases if e["id"] in wanted]

    counts = {"PASS": 0, "FAIL": 0, "XFAIL": 0, "XPASS": 0}
    observed_xfail = set()
    observed_xpass = set()
    print(f"\n{BLUE}unslop adversarial suite — {len(script_cases)} script cases "
          f"({len(skill_cases)} skill cases skipped; --list-skill to see them){RESET}\n")

    for ev in script_cases:
        ok, details = run_case(ev)
        xfail = ev.get("xfail", False)
        if ok and not xfail:
            status, color = "PASS", GREEN
        elif ok and xfail:
            status, color = "XPASS", YELLOW
        elif not ok and xfail:
            status, color = "XFAIL", DIM
        else:
            status, color = "FAIL", RED
        if status == "XFAIL":
            observed_xfail.add(ev["id"])
        if status == "XPASS":
            observed_xpass.add(ev["id"])
        counts[status] += 1
        print(f"  {color}{status:6}{RESET} {ev['id']:14} {ev['title']}")
        if status in ("FAIL", "XPASS"):
            print(f"         {DIM}{details}{RESET}")

    print(f"\n  {GREEN}PASS {counts['PASS']}{RESET}  "
          f"{DIM}XFAIL {counts['XFAIL']} (known bugs){RESET}  "
          f"{YELLOW}XPASS {counts['XPASS']} (fixed — remove xfail){RESET}  "
          f"{RED}FAIL {counts['FAIL']} (regressions){RESET}\n")

    strict_xfail = not args.only and not args.case
    xfail_ok = True
    if strict_xfail and observed_xfail != EXPECTED_XFAIL:
        xfail_ok = False
        print(
            f"{RED}Unexpected XFAIL set: observed {sorted(observed_xfail)}, "
            f"expected {sorted(EXPECTED_XFAIL)}. New xfail requires updating "
            f"EXPECTED_XFAIL and CRITIQUE.md.{RESET}"
        )
    if observed_xpass:
        print(
            f"{RED}Unexpected XPASS: {sorted(observed_xpass)}. "
            f"Remove the xfail flag.{RESET}"
        )

    return 1 if counts["FAIL"] or observed_xpass or not xfail_ok else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
