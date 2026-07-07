# Plan 011: Cut suite runtime by dispatching scanner cases in-process

> **Executor instructions**: Follow step by step; verify each step; STOP
> conditions binding. Update `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- evals/run_adversarial.py scripts/`
> Mismatched excerpts = STOP.

## Status

- **Priority**: P3 (big win, but the suite already fits in CI comfortably — do this when runtime starts hurting or after 001–007 land)
- **Effort**: L
- **Risk**: MED — in-process execution changes isolation semantics; the whole suite is both the beneficiary and the thing at risk
- **Depends on**: plans/004 (schema gate — strongly recommended first)
- **Category**: perf
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

Measured at 217c218: the 440-case suite takes 26.6s, of which ~22s is
`python3` interpreter+import startup (~50ms × 440 spawns). Assertion work is
a rounding error. Every case spawns a fresh interpreter via
`subprocess.run` in `run_case`. Routing the dominant command shapes
(`python3 scripts/<scanner>.py …`) to an in-process dispatcher that imports
each module once cuts the suite toward ~5s, which compounds across every CI
run and every red-first development loop this repo's workflow mandates.

## Current state

- `evals/run_adversarial.py:96-115`:
  ```python
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
  ```
  `check_assertion` consumes `proc.stdout`, `proc.stderr`, `proc.returncode`.
- Command census (run this yourself to get exact numbers):
  `python3 -c "import json,collections; rows=json.load(open('evals/adversarial-evals.json'))['evals']; print(collections.Counter(tuple(r['command'][:2]) for r in rows if r.get('target')=='script'))"`
  Expect the bulk to be `('python3', 'scripts/banned_phrase_scan.py')` and
  siblings; `sh -c` wrappers and non-python commands are the fallback tail.
- The scripts are dual-mode importable (each guards CLI behavior under
  `if __name__ == "__main__":` and exposes `main(argv)`-style entrypoints —
  VERIFY per script: read each target's tail; e.g.
  `silhouette_scan.py: raise SystemExit(main(sys.argv[1:]))` takes an argv
  list; `banned_phrase_scan.py`'s main may read `sys.argv` globally —
  the dispatcher must accommodate both shapes).
- Global-state hazard: scanners cache compiled regexes at module level
  (fine — read-only) but check for any module-level MUTABLE state consumed
  across calls (e.g. memoization dicts keyed on input); grep each scanner
  for module-level dict/list assignments mutated inside functions.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Baseline timing | `time python3 evals/run_adversarial.py` | ~26s before; target <10s after |
| Full suite | `python3 evals/run_adversarial.py` | exit 0, FAIL 0 — IDENTICAL pass/fail set before vs after |
| Escape hatch | `python3 evals/run_adversarial.py --subprocess` (new flag) | old path, green |

## Scope

**In scope**: `evals/run_adversarial.py` (dispatcher, flag); NO changes to
any scanner (if a scanner needs modification to be dispatchable, that's a
STOP — report which and why).

**Out of scope**: `scripts/*` (zero edits), gate commands in `list_gates()`
(they stay subprocess), `check_*.py` scripts, parallelism (no threads/
processes pools in this plan — sequential in-process is the whole win).

## Git workflow

- Branch: `advisor/011-inprocess-runner`; commit the dispatcher behind the
  default-ON path only after the equivalence proof (step 3).

## Steps

### Step 1: Build the dispatcher

In `run_adversarial.py`, add an `_inprocess_case(ev, timeout)` used when
`ev["command"]` matches `["python3", "scripts/<name>.py", *args]` for an
allowlist of scanner scripts (start with the top-3 by census). Mechanism:

- Import the module once (importlib, path-based, cached in a dict).
- For each case: patch `sys.argv = ["<name>.py", *args]`, `sys.stdin` =
  `io.StringIO(ev.get("stdin",""))`, capture stdout/stderr via
  `contextlib.redirect_stdout/redirect_stderr`, call the module's `main`
  (adapt per script: `main(argv_list)` vs argv-global `main()`), catch
  `SystemExit` for the return code, and restore everything in `finally`.
- Wrap in a wall-clock guard: if a case exceeds `timeout` there is no clean
  in-process kill — run a `signal.alarm`-based guard (POSIX-only is fine;
  CI is ubuntu) or fall back to subprocess for any case that ever timed out.
- ANY exception in dispatch → fall back to the subprocess path transparently
  and count it (report fallback stats at the end of the run).

**Verify**: `python3 evals/run_adversarial.py --only FP` → identical results
to a `--subprocess` run of the same slice (add the flag in this step).

### Step 2: Equivalence proof over the full suite

Run the suite both ways; diff the full per-case result lines.

**Verify**:
```
python3 evals/run_adversarial.py --subprocess > /tmp/before.txt
python3 evals/run_adversarial.py > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt
```
→ empty diff (or differing only in timing lines if any). Also
`time` both: after-time must be < 40% of before-time, else the allowlist is
missing the hot scripts — extend it.

### Step 3: Isolation audit

Prove no cross-case leakage: run the suite twice in one process
(`--repeat 2` if trivial to add, else run the FP slice after the full suite
in the same invocation via a scratch harness) — identical results both
passes. Grep each allowlisted scanner for module-level mutable state and
document findings in the commit message.

**Verify**: repeated-run results identical; fallback count reported.

## Test plan

The equivalence diff IS the test. Keep `--subprocess` permanently as the
escape hatch and note it in the runner's --help.

## Done criteria

- [ ] Full suite green, identical pass/fail set to subprocess mode (empty diff)
- [ ] Wall-clock < 40% of baseline (record both numbers in commit message)
- [ ] `--subprocess` flag documented and green
- [ ] Zero edits under `scripts/`
- [ ] `plans/README.md` updated

## STOP conditions

- Any scanner requires source changes to be dispatchable.
- The equivalence diff is non-empty after two fix attempts — name the cases.
- Module-level mutable state that leaks across cases is found in a scanner —
  report it; do not "reset" it from the runner.
- signal-based timeout proves unreliable — ship with subprocess-fallback for
  timeout-prone cases and say so, rather than a flaky guard.

## Maintenance notes

- New scanner scripts must be added to the allowlist to benefit; cases fall
  back to subprocess silently otherwise (the fallback counter surfaces it).
- Reviewer: scrutinize the `finally` restoration (argv/stdin/stdout) — a
  leak there corrupts every subsequent case in ways the diff may not catch
  on green-vs-green.
