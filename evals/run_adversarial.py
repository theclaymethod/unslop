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
from concurrent.futures import ThreadPoolExecutor
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
import threading
from pathlib import Path

from eval_groups import (
    GATE_ORDER,
    GATE_LANES,
    CORE_CONTRACT_EXAMPLE_BUDGET,
    select_group,
    select_lane,
    validate_core_contract_budget,
    validate_topology,
)

ROOT = Path(__file__).resolve().parent.parent
SUITE = Path(__file__).resolve().parent / "adversarial-evals.json"
EXPECTED_XFAIL = {"FP-06"}
BATCHED_PAIR_PREFIXES = ("PAIR-", "PAIRM-")
PAIR_MANIFEST_PATH = ROOT / "evals" / "fixtures" / "pairs" / "manifest.json"
_TOOL_CONTRACT_BY_COMMAND = {
    **{
        ("python3", "evals/check_climb.py", f"--{flag}"): "CLIMB-CONTRACT-01"
        for flag in (
            "converge", "capped", "control", "preservation", "directives",
            "coverage", "codex-adapter",
        )
    },
    **{
        ("python3", "evals/check_contrib.py", f"CONTRIB-{index:02d}"):
            "CONTRIB-CONTRACT-01"
        for index in range(1, 11)
    },
    **{
        ("python3", "evals/check_mimic.py", f"--{flag}"):
            "MIMIC-LOOP-CONTRACT-01"
        for flag in ("acceptance", "patience", "divergence", "stuffed-attack")
    },
    **{
        ("python3", "evals/check_mimic.py", f"--{flag}"):
            "MIMIC-GATES-CONTRACT-01"
        for flag in ("live-path", "copy-gate", "fact-gate", "determinism")
    },
    **{
        ("python3", "evals/check_mimic.py", f"--{flag}"):
            "MIMIC-SUPPORT-CONTRACT-01"
        for flag in ("stats", "split-refusal", "directives")
    },
    **{
        ("python3", "evals/check_mimic.py", f"--{flag}"):
            "CARD-CONTRACT-01"
        for flag in (
            "card-determinism", "card-budget", "card-facts", "card-layout",
            "card-never-does", "coverage-gap", "no-fabrication",
            "card-profile-mismatch",
        )
    },
    **{
        ("python3", "evals/check_voice.py", f"--{flag}"):
            "VOICE-CONTRACT-01"
        for flag in (
            "separation", "gi", "gaming", "copy-violation", "copy-clean",
            "determinism", "short", "profiles",
        )
    },
}
_BATCHED_EXIT_ASSERTION = [{"type": "exit_code", "equals": 0}]
_AGGREGATE_CONTRACT_SHAPES = {
    "DOC-08": {
        "command": ["python3", "evals/check_pairs.py"],
        "assertions": _BATCHED_EXIT_ASSERTION,
    },
    "CLIMB-CONTRACT-01": {
        "command": ["python3", "evals/check_climb.py", "--all"],
        "assertions": _BATCHED_EXIT_ASSERTION + [
            {"type": "stdout_contains", "value": "climb contract: 7/7 passed"}
        ],
    },
    "CONTRIB-CONTRACT-01": {
        "command": ["python3", "evals/check_contrib.py", "--all"],
        "assertions": _BATCHED_EXIT_ASSERTION + [
            {"type": "stdout_contains", "value": "contrib contract: 10/10 passed"},
            {"type": "stdout_contains", "value": "contrib bundles restored: true"},
        ],
    },
    "MIMIC-LOOP-CONTRACT-01": {
        "command": ["python3", "evals/check_mimic.py", "--contract-loop"],
        "assertions": _BATCHED_EXIT_ASSERTION + [
            {"type": "stdout_contains", "value": "mimic-loop contract: 4/4 passed"}
        ],
    },
    "MIMIC-GATES-CONTRACT-01": {
        "command": ["python3", "evals/check_mimic.py", "--contract-gates"],
        "assertions": _BATCHED_EXIT_ASSERTION + [
            {"type": "stdout_contains", "value": "mimic-gates contract: 4/4 passed"}
        ],
    },
    "MIMIC-SUPPORT-CONTRACT-01": {
        "command": ["python3", "evals/check_mimic.py", "--contract-support"],
        "assertions": _BATCHED_EXIT_ASSERTION + [
            {"type": "stdout_contains", "value": "mimic-support contract: 3/3 passed"}
        ],
    },
    "CARD-CONTRACT-01": {
        "command": ["python3", "evals/check_mimic.py", "--all-card"],
        "assertions": _BATCHED_EXIT_ASSERTION + [
            {"type": "stdout_contains", "value": "card contract: 8/8 passed"}
        ],
    },
    "VOICE-CONTRACT-01": {
        "command": ["python3", "evals/check_voice.py", "--all"],
        "assertions": _BATCHED_EXIT_ASSERTION + [
            {"type": "stdout_contains", "value": "voice contract: 8/8 passed"}
        ],
    },
}


def _active_contract_ids(rows):
    """Return aggregate IDs only when their complete row shape is canonical."""
    active = set()
    for row in rows:
        expected = _AGGREGATE_CONTRACT_SHAPES.get(row.get("id"))
        if expected and all(row.get(field) == value for field, value in expected.items()):
            active.add(row["id"])
    return active


def _batched_tool_row(row, selected_ids):
    """Batch only an exact legacy row whose aggregate contract is present.

    New flags, changed assertions, and missing aggregate rows automatically stay
    on the individual path, preventing compaction from hiding new coverage.
    """
    contract_id = _TOOL_CONTRACT_BY_COMMAND.get(tuple(row.get("command", ())))
    return (
        contract_id in selected_ids
        and row.get("assertions") == _BATCHED_EXIT_ASSERTION
    )


def _batched_pair_row(row, selected_ids, pair_manifest):
    """Batch only a pair row exactly represented by DOC-08's manifest contract."""
    if "DOC-08" not in selected_ids or not row.get("id", "").startswith(BATCHED_PAIR_PREFIXES):
        return False
    command = row.get("command")
    assertions = row.get("assertions")
    if not isinstance(command, list) or len(command) != 3 or not isinstance(assertions, list):
        return False
    if command[0] != "python3":
        return False
    script, fixture = command[1], Path(command[2])
    name = fixture.name
    if fixture.as_posix() != f"evals/fixtures/pairs/{name}":
        return False
    matched = None
    for suffix in ("_with.txt", "_without.txt", "_with.md", "_without.md"):
        if name.endswith(suffix):
            matched = suffix
            slug = name[: -len(suffix)]
            break
    if matched is None or slug not in pair_manifest:
        return False
    info = pair_manifest[slug]
    target = info.get("target") if isinstance(info, dict) else None
    kind = info.get("kind") if isinstance(info, dict) else None
    with_fixture = matched in {"_with.txt", "_with.md"}
    if kind == "structure":
        if script == "scripts/structure_scan.py":
            expected = (
                [{"type": "json", "path": f"flagged.{target}", "equals": True}]
                if with_fixture
                else _BATCHED_EXIT_ASSERTION
            )
        elif script == "scripts/banned_phrase_scan.py":
            expected = [{"type": "json", "path": "total_violations", "equals": 0}]
        else:
            return False
    elif kind == "phrase":
        if script == "scripts/banned_phrase_scan.py":
            expected = (
                [
                    {"type": "json", "path": "total_violations", "gte": 1},
                    {"type": "violation_category_equals", "value": target},
                ]
                if with_fixture
                else [{"type": "json", "path": "total_violations", "equals": 0}]
            )
        elif script == "scripts/structure_scan.py" and not with_fixture:
            expected = _BATCHED_EXIT_ASSERTION
        else:
            return False
    else:
        return False
    return assertions == expected

# Scanners dispatched in-process instead of via subprocess. Chosen as the
# highest-census command shapes (see plans/011 census) that are dual-mode
# importable with no observed module-level mutable state (constants only:
# dicts/lists read via .get/.values/.items, never mutated after import).
# A scanner needing source changes to be dispatchable is a plan STOP — do not
# add one here without re-auditing it per the plan's Global-state hazard note.
DISPATCHABLE = {
    "scripts/structure_scan.py",
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
_STATS_LOCK = threading.Lock()
DEFAULT_JOBS = min(8, max(1, os.cpu_count() or 1))

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
        stdin_bytes = ev.get("stdin", "").encode("utf-8")
        sys.stdin = io.TextIOWrapper(
            io.BytesIO(stdin_bytes), encoding="utf-8", errors="replace"
        )
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
        with _STATS_LOCK:
            STATS["inprocess"] += 1
    else:
        with _STATS_LOCK:
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


def _guaranteed_subprocess(ev):
    """Return whether *ev* cannot enter the in-process dispatcher.

    Dispatchable scanner shapes stay on the main thread even when ``--jobs``
    is enabled: their imports and calls temporarily replace ``sys.argv``,
    ``sys.stdin``, and the process cwd. Everything else already uses the
    isolated subprocess path and can be submitted to the bounded pool.
    """
    if ev.get("serial"):
        return False
    command = ev.get("command", ())
    return not (
        len(command) >= 2
        and command[0] == "python3"
        and command[1] in DISPATCHABLE
    )


def list_gates():
    return [
        {
            "id": "core-outcome",
            "command": "python3 evals/run_adversarial.py --group core-outcome",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
            "lane": GATE_LANES["core-outcome"],
            "budget": {"max_examples": CORE_CONTRACT_EXAMPLE_BUDGET},
        },
        {
            "id": "deterministic-safety",
            "command": "python3 evals/run_adversarial.py --group deterministic-safety",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
            "lane": GATE_LANES["deterministic-safety"],
            "budget": {"max_examples": None},
        },
        {
            "id": "integrity-and-tools",
            "command": "python3 evals/run_adversarial.py --group integrity-and-tools",
            "pass_criterion": "exit 0",
            "blocking": True,
            "needs": [],
            "lane": GATE_LANES["integrity-and-tools"],
            "budget": {"max_examples": None},
        },
        {
            "id": "behavioral",
            "command": "python3 evals/check.py --behavioral tune",
            "pass_criterion": "exit 0",
            "blocking": False,
            "needs": ["skill-benchmark", "codex exec (gpt-5.6-luna)"],
            "lane": GATE_LANES["behavioral"],
            "budget": {"max_examples": None},
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
        "--group",
        choices=GATE_ORDER,
        help="run the examples inside one documented evaluation gate",
    )
    parser.add_argument(
        "--lane",
        choices=("core-contract", "maintenance"),
        help=(
            "run an explicit lane: the five-example core-contract gate or the "
            "exhaustive deterministic maintenance matrix"
        ),
    )
    parser.add_argument(
        "--eval-file",
        type=Path,
        default=SUITE,
        help="alternate adversarial suite JSON (used by runner integration checks)",
    )
    parser.add_argument(
        "--subprocess",
        action="store_true",
        help="escape hatch: run every case via subprocess (the pre-dispatcher path)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="print only failures, expected limitations, and the final summary",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=DEFAULT_JOBS,
        metavar="N",
        help=f"parallel workers for guaranteed-subprocess cases (default: {DEFAULT_JOBS})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        metavar="SECONDS",
        help="per-case subprocess timeout (default: 30)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help=argparse.SUPPRESS,  # isolation-audit tool: rerun N times, diff results
    )
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    if args.timeout < 1:
        parser.error("--timeout must be at least 1")
    if args.group and (args.only or args.case):
        parser.error("--group cannot be combined with --only or --case")
    if args.lane and (args.group or args.only or args.case):
        parser.error("--lane cannot be combined with --group, --only, or --case")
    return args


def _execute(
    script_cases,
    skill_cases,
    strict_xfail,
    use_subprocess,
    quiet=False,
    compact=False,
    jobs=DEFAULT_JOBS,
    timeout=30,
    expected_xfail=EXPECTED_XFAIL,
    lane=None,
):
    """Run one full pass over script_cases. Returns (rc, per_case) where
    per_case is an ordered list of (id, status) for equivalence/repeat diffing."""
    counts = {"PASS": 0, "FAIL": 0, "XFAIL": 0, "XPASS": 0}
    observed_xfail = set()
    observed_xpass = set()
    per_case = []
    if not quiet:
        if lane:
            display_lane = "core-contract plumbing (zero-token)" if lane == "core-contract" else lane
            print(f"{BLUE}lane: {display_lane}{RESET}")
        print(f"\n{BLUE}unslop contract — {len(script_cases)} deterministic examples "
              f"({len(skill_cases)} behavioral examples in this lane){RESET}\n")

    # Finish all process-global or explicitly serial work before starting the
    # pool. This prevents repository-mutating checks from exposing temporary
    # state to concurrent subprocesses.
    results = {}
    parallel_cases = []
    if not use_subprocess and jobs > 1:
        candidates = [ev for ev in script_cases if _guaranteed_subprocess(ev)]
        if len(candidates) > 1:
            parallel_cases = candidates

    parallel_ids = {ev["id"] for ev in parallel_cases}
    for ev in script_cases:
        if ev["id"] not in parallel_ids:
            results[ev["id"]] = run_case(
                ev, timeout=timeout, use_subprocess=use_subprocess
            )

    if parallel_cases:
        workers = min(jobs, len(parallel_cases))
        if not quiet:
            print(
                f"{DIM}parallel dispatch: {len(parallel_cases)} subprocess "
                f"cases via {workers} workers{RESET}"
            )
        with ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="adversarial-subprocess"
        ) as executor:
            futures = {
                ev["id"]: executor.submit(run_case, ev, timeout, True)
                for ev in parallel_cases
            }
            # Collect in suite order, independently of completion timing.
            for ev in parallel_cases:
                results[ev["id"]] = futures[ev["id"]].result()

    for ev in script_cases:
        ok, details = results[ev["id"]]
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
        if not quiet and (not compact or status != "PASS"):
            print(f"  {color}{status:6}{RESET} {ev['id']:14} {ev['title']}")
            if status in ("FAIL", "XPASS"):
                print(f"         {DIM}{details}{RESET}")

    if not quiet:
        print(f"\n  {GREEN}PASS {counts['PASS']}{RESET}  "
              f"{DIM}XFAIL {counts['XFAIL']} (known bugs){RESET}  "
              f"{YELLOW}XPASS {counts['XPASS']} (fixed — remove xfail){RESET}  "
              f"{RED}FAIL {counts['FAIL']} (regressions){RESET}\n")

    xfail_ok = True
    if strict_xfail and observed_xfail != expected_xfail:
        xfail_ok = False
        if not quiet:
            print(
                f"{RED}Unexpected XFAIL set: observed {sorted(observed_xfail)}, "
                f"expected {sorted(expected_xfail)}. New xfail requires updating "
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
    suite = json.loads(args.eval_file.read_text())
    evals = suite["evals"]
    # Explicit slices are diagnostic and may target a temporary, not-yet-grouped
    # row (the add-a-pattern kata relies on this). Enforce topology for normal
    # gate runs, where the grouping contract is part of the product surface.
    topology_errors = (
        validate_topology(evals)
        if args.eval_file.resolve() == SUITE.resolve() and not (args.only or args.case)
        else []
    )
    if not topology_errors and args.eval_file.resolve() == SUITE.resolve() and not (args.only or args.case):
        topology_errors.extend(validate_core_contract_budget(evals))
    if topology_errors:
        print("invalid eval topology:\n  " + "\n  ".join(topology_errors), file=sys.stderr)
        return 2
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

    if args.lane:
        selected = select_lane(evals, args.lane)
        script_cases = [e for e in selected if e.get("target") == "script"]
        skill_cases = [e for e in selected if e.get("target") == "skill"]
    elif args.group:
        selected = select_group(evals, args.group)
        script_cases = [e for e in selected if e.get("target") == "script"]
        skill_cases = [e for e in selected if e.get("target") == "skill"]
    elif args.only or args.case:
        prefixes = tuple(args.only)
        wanted = set(args.case)
        script_cases = [
            e for e in script_cases
            if (prefixes and e["id"].startswith(prefixes)) or e["id"] in wanted
        ]

    # Legacy pair/tool wrappers are skipped only when their exact aggregate
    # contract is present. Changed rows automatically stay on the direct path.
    if not args.only and not args.case:
        canonical_suite = args.eval_file.resolve() == SUITE.resolve()
        active_contracts = _active_contract_ids(script_cases) if canonical_suite else set()
        try:
            pair_manifest = json.loads(PAIR_MANIFEST_PATH.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            pair_manifest = {}
        script_cases = [
            row for row in script_cases
            if not _batched_pair_row(row, active_contracts, pair_manifest)
            and not (canonical_suite and _batched_tool_row(row, active_contracts))
        ]

    strict_xfail = not args.only and not args.case
    expected_xfail = EXPECTED_XFAIL.intersection(e["id"] for e in script_cases)

    if args.repeat > 1:
        # Isolation audit: rerun the full pass N times in one process and
        # diff per-case results. Any drift means a scanner is leaking
        # module-level state across cases.
        passes = []
        rc = 0
        for i in range(args.repeat):
            pass_rc, per_case = _execute(
                script_cases,
                skill_cases,
                strict_xfail,
                args.subprocess,
                quiet=True,
                jobs=args.jobs,
                timeout=args.timeout,
                expected_xfail=expected_xfail,
                lane=args.lane,
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

    rc, _ = _execute(
        script_cases,
        skill_cases,
        strict_xfail,
        args.subprocess,
        compact=args.compact,
        jobs=args.jobs,
        timeout=args.timeout,
        expected_xfail=expected_xfail,
        lane=args.lane,
    )
    _print_dispatch_stats()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
