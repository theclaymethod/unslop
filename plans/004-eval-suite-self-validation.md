# Plan 004: Give the eval suite a schema gate and drive CI from the gate matrix

> **Executor instructions**: Follow step by step; verify each step; STOP
> conditions are binding. Update `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- evals/ .github/workflows/evals.yml`
> Mismatched excerpts = STOP.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none (land BEFORE plans 005–007 so their new rows are born validated)
- **Category**: tech-debt
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

`evals/adversarial-evals.json` is the product's constitution: 473 hand-merged
rows, hand-numbered ids, 46 commits of churn — and nothing validates it. A
duplicate id runs twice silently (and collapses silently in the xfail set
comparison, `evals/run_adversarial.py:27`); a row missing `command` crashes at
runtime; an unknown assertion type may no-op. All ids are unique today, so a
validator locks the invariant for free. Separately, CI runs only 4 named
steps; the other ~20 blocking gates run only because DOC-* rows inside the
suite invoke them — deleting one DOC row silently drops a gate from CI.
Driving CI's gate execution from `--list-gates` removes that fragility.

## Current state

- `evals/run_adversarial.py:96-110` — `run_case` consumes
  `ev["command"]`, `ev.get("stdin","")`, `ev["assertions"]` with no
  structural validation. `:337-342` filters by id prefix, never asserts
  uniqueness. `EXPECTED_XFAIL` at `:27` is an id-set comparison.
- Row shape in `evals/adversarial-evals.json`: every row has
  `id`, `title`, `target` (`"script"` or `"skill"`); script rows have
  `command` (list) and `assertions` (list of typed dicts); assertion `type`
  values handled by `check_assertion` (verified at 217c218):
  `exit_code`, `json`, `stdout_contains`, `stdout_not_contains`,
  `stderr_not_contains`, `violation_category_equals`,
  `violation_phrase_contains` (read `check_assertion` in
  `evals/run_adversarial.py` for the authoritative set and their fields —
  do not trust this list over the code).
- Gate registration exemplar, `evals/run_adversarial.py:188-194`:
  ```python
      {
          "id": "command-router-parity",
          "command": "python3 evals/check_commands.py",
          "pass_criterion": "exit 0",
          "blocking": True,
          "needs": [],
      },
  ```
- Gate-doc pinning: `evals/check_gates_doc.py` regenerates/compares a JSON
  block in `evals/CHECKS.md` against `--list-gates` output (DOC-03 row). Any
  new gate requires regenerating that block (read `check_gates_doc.py --help`
  or its docstring for the regen flag).
- Shared helpers for check scripts: `evals/_check_support.py` provides
  `ROOT`, `run(cmd, timeout=60)`, `load_evals()`. New checks import from it
  (exemplar: `evals/check_commands.py`'s imports).
- CI: `.github/workflows/evals.yml` — steps run `run_adversarial.py`,
  `build_shared_benchmark.py --check`, `check_taboo_parity.py`,
  `skill-benchmark validate … --strict-leakage` explicitly; nothing else.
- Existing DOC row numbering: DOC-01..DOC-13 exist; your new row takes the
  next free number (verify with the id-listing one-liner from plan 002).

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Full suite | `python3 evals/run_adversarial.py` | exit 0, FAIL 0 |
| Gate list | `python3 evals/run_adversarial.py --list-gates` | JSON, 24 gates before your change; 25 after |
| Gate doc | `python3 evals/check_gates_doc.py` | `gate matrix ok: N gates documented` |
| New gate | `python3 evals/check_evals_schema.py` | exit 0, one summary line |

## Scope

**In scope**: new `evals/check_evals_schema.py`; `evals/run_adversarial.py`
(one gate dict added to `list_gates()` ONLY); `evals/CHECKS.md` (regenerated
block); `evals/adversarial-evals.json` (one DOC row);
`.github/workflows/evals.yml`.

**Out of scope**: any change to `run_case`/`check_assertion` behavior; any
existing row; `build_shared_benchmark.py`.

## Git workflow

- Branch: `advisor/004-suite-self-validation`; red-first for the DOC row;
  sentence-case imperative commits.

## Steps

### Step 1: Write the validator

Create `evals/check_evals_schema.py` (model its skeleton on
`evals/check_commands.py`: shebang, docstring, `_check_support` imports,
`main() -> int`, `raise SystemExit(main())`). It must assert, over
`load_evals()`:

1. `len(ids) == len(set(ids))` — name the duplicates on failure.
2. Every id matches `^[A-Z]+(-[A-Z]+)*-\d+[a-z]?$` (verify this regex against
   the actual corpus FIRST: `LANG-3a` style ids exist — adjust the regex to
   fit ALL current ids exactly, then lock; print any nonconforming id).
3. Every row has `id`, `title`, `target`; `target` in `{"script","skill"}`.
4. Script rows: `command` is a non-empty list of strings; `assertions` is a
   non-empty list; every assertion `type` is in the set derived from
   `check_assertion` — import the authoritative set from
   `run_adversarial` if it's exposed as data, otherwise define the set here
   with a comment naming `check_assertion` as the source and add a
   cross-check: grep-extract the handled types from the source at runtime
   (read the file, regex the `== "<type>"` comparisons) so drift fails loudly.
5. Skill rows: whatever fields `build_shared_benchmark.py` consumes — read
   its loader and validate those keys.

Exit 0 with `evals schema ok: 473 rows, 440 script, 33 skill` (live counts);
exit 1 listing every problem.

**Verify**: `python3 evals/check_evals_schema.py` → exit 0 on the current suite.
**Verify (negative)**: `python3 - <<'EOF'` … copy the suite to /tmp, duplicate
one id, point the checker at it via env/arg if you added one, or temporarily
test by construction — simplest: write the checker to accept an optional path
argument defaulting to the real suite; test with a corrupted temp copy → exit 1.

### Step 2: Register the gate + DOC row (red first)

Add the DOC row invoking `["python3", "evals/check_evals_schema.py"]`,
`exit_code: 0` — it passes immediately (the validator is already green), so
"red" here means: before adding the gate entry, run
`python3 evals/check_gates_doc.py` → it must FAIL after you add the gate to
`list_gates()` and before you regenerate CHECKS.md (that failure proves the
doc pin works). Then regenerate the CHECKS.md block per `check_gates_doc.py`'s
documented mechanism.

**Verify**: `--list-gates` → 25 gates; `check_gates_doc.py` → ok, 25 documented; full suite green.

### Step 3: Drive CI from the gate matrix

Replace the individually-named gate steps in `.github/workflows/evals.yml`
(keep: checkout, setup-python, py_compile, the pipx install, and the
strict-leakage step which needs the installed tool) with one step:

```yaml
      - name: Run all blocking gates from the matrix
        run: |
          python3 - <<'EOF'
          import json, subprocess, sys
          gates = json.loads(subprocess.run(
              ["python3", "evals/run_adversarial.py", "--list-gates"],
              capture_output=True, text=True, check=True).stdout)
          failed = []
          for g in gates:
              if not g.get("blocking"): continue
              cmd = g["command"]
              # Gate commands are repo-authored strings from list_gates(),
              # not user input. Simple commands run shell-free via shlex;
              # compound commands ("a && b") need the shell — acceptable
              # ONLY because the source is the repo's own gate matrix.
              import shlex
              if "&&" in cmd or "|" in cmd:
                  r = subprocess.run(cmd, shell=True)
              else:
                  r = subprocess.run(shlex.split(cmd))
              if r.returncode != 0: failed.append(g["id"])
          sys.exit(1 if failed else 0)
          EOF
```

Security note for the executor: never extend this runner to execute commands
from any source other than `list_gates()` — the shell branch is safe only
while the command strings are version-controlled repo data.

FIRST verify the actual `--list-gates` output shape (is it JSON? a table?)
by running it — adapt the parser to reality. If gates declare `needs` (e.g.
`skill-benchmark`), keep the pipx install step ordered before this one. Non-
blocking gates (behavioral) must be skipped exactly as the matrix marks them.

**Verify**: run the new step's script locally → exit 0, and its runtime is
acceptable (expect ~2-3 min; the full suite runs once as the
`adversarial-suite` gate — confirm the matrix doesn't ALSO run it via a
second entry; dedupe is out of scope, just report the total time).

## Test plan

The validator's negative test (corrupted temp copy → exit 1, names the
problem) is required, executed manually in step 1 and recorded in the commit
message. The DOC row keeps the gate wired forever.

## Done criteria

- [ ] `python3 evals/check_evals_schema.py` → exit 0 with counts line
- [ ] Corrupted-copy negative test → exit 1 naming the duplicate id
- [ ] `--list-gates` shows the new gate; `check_gates_doc.py` green
- [ ] Full suite green (439+1 pass/xfail + your DOC row)
- [ ] CI workflow runs gates from the matrix; local dry-run exit 0
- [ ] `plans/README.md` updated

## STOP conditions

- `--list-gates` output is not machine-parseable — report its actual format
  and propose adding `--list-gates --json` as a follow-up instead of scraping.
- The id-shape regex can't be made to fit all existing ids without becoming
  vacuous — report the outlier ids for a human decision.
- Regenerating CHECKS.md touches unrelated gate entries (would mean the doc
  drifted earlier) — report, don't absorb.

## Maintenance notes

- Every future plan adding rows/gates gets validated automatically; keep the
  assertion-type cross-check in sync when `check_assertion` grows a type
  (the runtime grep makes forgetting loud).
- Reviewer: scrutinize the CI step's failure surfacing — a gate id list in
  the failure output is required for debuggability.
