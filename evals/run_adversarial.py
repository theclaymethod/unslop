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
import contextlib
import importlib.util
import inspect
import io
import json
import argparse
import math
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITE = Path(__file__).resolve().parent / "adversarial-evals.json"
EXPECTED_XFAIL = {"FP-06"}

# Scanners dispatched in-process instead of via subprocess. Chosen as the
# highest-census command shapes (see plans/011 census) that are dual-mode
# importable with no observed module-level mutable state (constants only:
# dicts/lists read via .get/.values/.items, never mutated after import).
# A scanner needing source changes to be dispatchable is a plan STOP — do not
# add one here without re-auditing it per the plan's Global-state hazard note.
DISPATCHABLE = {
    "scripts/banned_phrase_scan.py",
    "scripts/structure_scan.py",
    "scripts/validate_preservation.py",
    "scripts/silhouette_scan.py",
    "scripts/readability_metrics.py",
    "scripts/diff_check.py",
    "scripts/harvest_samples.py",
    "scripts/calibrate_score.py",
    "scripts/check_suggestions.py",
    "scripts/extract_constraints.py",
    "scripts/suggest.py",
    "scripts/harvest_classify.py",
    "scripts/calibrate_pairs.py",
    "scripts/voice_score.py",
}

_MODULE_CACHE = {}
_TIMEOUT_FALLBACK = set()  # rel_paths permanently routed to subprocess after a timeout
STATS = {"inprocess": 0, "subprocess": 0, "dispatch_fallback": 0, "fallback_reasons": []}

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


class _ProcResult:
    """Stand-in for subprocess.CompletedProcess, populated by an in-process dispatch."""
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _DispatchTimeout(Exception):
    pass


@contextlib.contextmanager
def _alarm_timeout(seconds):
    """POSIX signal.alarm-based guard. No-op (relies on the outer subprocess
    timeout instead) on platforms without SIGALRM."""
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handler(signum, frame):
        raise _DispatchTimeout(f"timed out after {seconds}s")

    old_handler = signal.signal(signal.SIGALRM, _handler)
    old_alarm = signal.alarm(max(1, math.ceil(seconds)))
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
        if old_alarm:
            signal.alarm(old_alarm)


def _load_module(rel_path):
    """Import scripts/<name>.py once and cache it. Raises on failure — caller
    treats any exception as a signal to fall back to subprocess."""
    if rel_path not in _MODULE_CACHE:
        mod_name = "_run_adversarial_inproc__" + rel_path.replace("/", "_")[:-3]
        spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULE_CACHE[rel_path] = module
    return _MODULE_CACHE[rel_path]


def _inprocess_case(ev, timeout):
    """Try to run a script-target case in-process. Returns a _ProcResult on
    success, or None if it should fall back to subprocess (not allowlisted,
    previously timed out, or any dispatch exception)."""
    command = ev["command"]
    if len(command) < 2 or command[0] != "python3":
        return None
    rel_path = command[1]
    if rel_path not in DISPATCHABLE or rel_path in _TIMEOUT_FALLBACK:
        return None

    args = command[2:]

    old_argv = sys.argv
    old_stdin = sys.stdin
    old_cwd = os.getcwd()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    try:
        module = _load_module(rel_path)
        if not hasattr(module, "main"):
            return None

        sys.argv = [Path(rel_path).name] + list(args)
        sys.stdin = io.StringIO(ev.get("stdin", ""))
        os.chdir(ROOT)

        sig = inspect.signature(module.main)
        returncode = 0
        with _alarm_timeout(timeout), \
                contextlib.redirect_stdout(stdout_buf), \
                contextlib.redirect_stderr(stderr_buf):
            try:
                if len(sig.parameters) >= 1:
                    result = module.main(list(args))
                else:
                    result = module.main()
                if isinstance(result, int):
                    returncode = result
            except SystemExit as e:
                code = e.code
                if code is None:
                    returncode = 0
                elif isinstance(code, int):
                    returncode = code
                else:
                    stderr_buf.write(str(code))
                    returncode = 1
    except _DispatchTimeout as e:
        # Any timeout permanently routes this scanner to subprocess for the
        # rest of the run — a signal-based guard that fires once is not
        # trustworthy enough to keep retrying in-process.
        _TIMEOUT_FALLBACK.add(rel_path)
        STATS["dispatch_fallback"] += 1
        STATS["fallback_reasons"].append((ev["id"], str(e)))
        return None
    except Exception as e:  # noqa: BLE001 - any dispatch failure -> transparent fallback
        STATS["dispatch_fallback"] += 1
        STATS["fallback_reasons"].append((ev["id"], f"{type(e).__name__}: {e}"))
        return None
    finally:
        sys.argv = old_argv
        sys.stdin = old_stdin
        os.chdir(old_cwd)

    return _ProcResult(returncode, stdout_buf.getvalue(), stderr_buf.getvalue())


def run_case(ev, timeout=30, use_subprocess=False):
    proc = None if use_subprocess else _inprocess_case(ev, timeout)
    if proc is not None:
        STATS["inprocess"] += 1
    else:
        STATS["subprocess"] += 1
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
            "id": "harvest-suite",
            "command": "python3 evals/run_adversarial.py --only HARV",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "contribute-suite",
            "command": "python3 evals/run_adversarial.py --only CONTRIB",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "calibrate-suite",
            "command": "python3 evals/run_adversarial.py --only CAL",
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
            "id": "voice-scorer",
            "command": "python3 evals/check_voice.py --separation && python3 evals/check_voice.py --gi && python3 evals/check_voice.py --gaming && python3 evals/check_voice.py --profiles",
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
            "id": "command-router-parity",
            "command": "python3 evals/check_commands.py",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "seeded-docs",
            "command": "python3 evals/check_seeded_docs.py",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "paired-fixture-hygiene",
            "command": "python3 evals/check_pairs.py",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "mimic-logic",
            "command": "python3 evals/run_adversarial.py --only MIMIC --only CARD",
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
            "id": "silhouette-scan",
            "command": "python3 scripts/silhouette_scan.py < transformed.txt",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
        },
        {
            "id": "silhouette-check",
            "command": "python3 evals/check_silhouette.py",
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
    parser.add_argument(
        "--subprocess",
        action="store_true",
        help="escape hatch: run every case via subprocess (the pre-dispatcher path)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help=argparse.SUPPRESS,  # isolation-audit tool: rerun N times, diff results
    )
    return parser.parse_args(argv)


def _execute(script_cases, skill_cases, strict_xfail, use_subprocess, quiet=False):
    """Run one full pass over script_cases. Returns (rc, per_case) where
    per_case is an ordered list of (id, status) for equivalence/repeat diffing."""
    counts = {"PASS": 0, "FAIL": 0, "XFAIL": 0, "XPASS": 0}
    observed_xfail = set()
    observed_xpass = set()
    per_case = []
    if not quiet:
        print(f"\n{BLUE}unslop adversarial suite — {len(script_cases)} script cases "
              f"({len(skill_cases)} skill cases skipped; --list-skill to see them){RESET}\n")

    for ev in script_cases:
        ok, details = run_case(ev, use_subprocess=use_subprocess)
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
        per_case.append((ev["id"], status))
        if not quiet:
            print(f"  {color}{status:6}{RESET} {ev['id']:14} {ev['title']}")
            if status in ("FAIL", "XPASS"):
                print(f"         {DIM}{details}{RESET}")

    if not quiet:
        print(f"\n  {GREEN}PASS {counts['PASS']}{RESET}  "
              f"{DIM}XFAIL {counts['XFAIL']} (known bugs){RESET}  "
              f"{YELLOW}XPASS {counts['XPASS']} (fixed — remove xfail){RESET}  "
              f"{RED}FAIL {counts['FAIL']} (regressions){RESET}\n")

    xfail_ok = True
    if strict_xfail and observed_xfail != EXPECTED_XFAIL:
        xfail_ok = False
        if not quiet:
            print(
                f"{RED}Unexpected XFAIL set: observed {sorted(observed_xfail)}, "
                f"expected {sorted(EXPECTED_XFAIL)}. New xfail requires updating "
                f"EXPECTED_XFAIL and CRITIQUE.md.{RESET}"
            )
    if observed_xpass and not quiet:
        print(
            f"{RED}Unexpected XPASS: {sorted(observed_xpass)}. "
            f"Remove the xfail flag.{RESET}"
        )

    rc = 1 if counts["FAIL"] or observed_xpass or not xfail_ok else 0
    return rc, per_case


def _print_dispatch_stats():
    total = STATS["inprocess"] + STATS["subprocess"]
    if total == 0:
        return
    print(
        f"{DIM}dispatch: {STATS['inprocess']} in-process, {STATS['subprocess']} subprocess "
        f"({STATS['dispatch_fallback']} dispatch fallbacks){RESET}"
    )
    if STATS["fallback_reasons"]:
        for case_id, reason in STATS["fallback_reasons"]:
            print(f"{DIM}  fallback: {case_id}: {reason}{RESET}")
    if _TIMEOUT_FALLBACK:
        print(f"{DIM}  permanently routed to subprocess (timed out once): "
              f"{sorted(_TIMEOUT_FALLBACK)}{RESET}")


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

    strict_xfail = not args.only and not args.case

    if args.repeat > 1:
        # Isolation audit: rerun the full pass N times in one process and
        # diff per-case results. Any drift means a scanner is leaking
        # module-level state across cases.
        passes = []
        rc = 0
        for i in range(args.repeat):
            pass_rc, per_case = _execute(
                script_cases, skill_cases, strict_xfail, args.subprocess, quiet=True
            )
            passes.append(per_case)
            rc = rc or pass_rc
            print(f"{DIM}--repeat pass {i + 1}/{args.repeat}: rc={pass_rc}{RESET}")
        identical = all(p == passes[0] for p in passes[1:])
        if identical:
            print(f"{GREEN}--repeat {args.repeat}: identical results every pass{RESET}")
        else:
            print(f"{RED}--repeat {args.repeat}: results DIFFER across passes "
                  f"(leaking module-level state){RESET}")
            for i, p in enumerate(passes[1:], start=2):
                diff = [(a, b) for a, b in zip(passes[0], p) if a != b]
                if diff:
                    print(f"{RED}  pass 1 vs pass {i}: {diff}{RESET}")
            rc = 1
        _print_dispatch_stats()
        return rc

    rc, _ = _execute(script_cases, skill_cases, strict_xfail, args.subprocess)
    _print_dispatch_stats()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
