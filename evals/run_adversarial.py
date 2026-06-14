#!/usr/bin/env python3
"""Runner for the deterministic (target=="script") cases in adversarial-evals.json.

These cases encode the CORRECT behavior of the skill's Python scripts. Most are
currently marked `xfail: true` because they expose real bugs (false positives,
fact-preservation holes, crashes). The runner is a regression harness:

  - PASS         assertion holds (good)
  - FAIL         assertion broken and NOT marked xfail (a regression)
  - XFAIL        assertion broken as expected (documented bug, still open)
  - XPASS        assertion holds but was marked xfail (bug fixed -> drop xfail!)

Exit code is non-zero only on a real FAIL (an undocumented regression) so this
can gate CI without the known-bug backlog turning the build red. Run from the
skill root:  python3 evals/run_adversarial.py

Behavioral (target=="skill") cases are skipped here; they require an agent/LLM
judge. List them with --list-skill.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITE = Path(__file__).resolve().parent / "adversarial-evals.json"

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


def run_case(ev):
    proc = subprocess.run(
        ev["command"],
        input=ev.get("stdin", ""),
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    results = [check_assertion(a, proc) for a in ev["assertions"]]
    ok = all(r[0] for r in results)
    details = "; ".join(d for _, d in results)
    return ok, details


def main(argv):
    suite = json.loads(SUITE.read_text())
    evals = suite["evals"]
    script_cases = [e for e in evals if e.get("target") == "script"]
    skill_cases = [e for e in evals if e.get("target") == "skill"]

    if "--list-skill" in argv:
        print(f"\n{BLUE}Behavioral (skill) cases — run against the agent, judge manually:{RESET}")
        for e in skill_cases:
            print(f"  {e['id']:24} [{e['category']}] {e['title']}")
        return 0

    counts = {"PASS": 0, "FAIL": 0, "XFAIL": 0, "XPASS": 0}
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
        counts[status] += 1
        print(f"  {color}{status:6}{RESET} {ev['id']:14} {ev['title']}")
        if status in ("FAIL", "XPASS"):
            print(f"         {DIM}{details}{RESET}")

    print(f"\n  {GREEN}PASS {counts['PASS']}{RESET}  "
          f"{DIM}XFAIL {counts['XFAIL']} (known bugs){RESET}  "
          f"{YELLOW}XPASS {counts['XPASS']} (fixed — remove xfail){RESET}  "
          f"{RED}FAIL {counts['FAIL']} (regressions){RESET}\n")

    # Only undocumented regressions break the build.
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
