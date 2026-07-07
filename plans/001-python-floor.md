# Plan 001: Make the advertised Python 3.8+ floor true, and test it in CI

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- scripts/ evals/ README.md .github/workflows/evals.yml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

`README.md` promises "Python 3.8+ and the standard library" (lines 48 and 455),
but 17 Python files use PEP 604 (`str | None`) and PEP 585 (`dict[str, ...]`)
annotations in positions evaluated at import time, with no
`from __future__ import annotations`. On Python 3.8/3.9 the flagship scanner
`scripts/banned_phrase_scan.py` raises `TypeError` at import — the primary
entry point is broken on two advertised platforms. CI pins only Python 3.11,
so no gate can ever catch this. This plan makes the floor claim true and adds
a CI leg at the floor so it stays true.

## Current state

- `scripts/banned_phrase_scan.py:82` — module-level evaluated annotation:
  ```python
  BANNED_PHRASES: dict[str, dict[str, str | None]] = {
  ```
  and there is no `from __future__ import annotations` anywhere in the file.
- The full list of files with evaluated modern annotations and **no**
  future-import (verified at 217c218):
  `scripts/banned_phrase_scan.py`, `scripts/check_packs.py`,
  `scripts/check_suggestions.py`, `scripts/diff_check.py`,
  `scripts/extract_constraints.py`, `scripts/readability_metrics.py`,
  `scripts/silhouette_scan.py`, `scripts/structure_scan.py`,
  `scripts/suggest.py`, `scripts/validate_preservation.py`,
  `scripts/voice_score.py`, `scripts/wiki_sync.py`,
  `evals/build_shared_benchmark.py`, `evals/check_commands.py`,
  `evals/check_gates_doc.py`, `evals/check_silhouette.py`, `evals/run_local.py`.
- The repo's own convention already exists: `scripts/harvest_samples.py`,
  `scripts/harvest_classify.py`, `scripts/contribute.py`,
  `scripts/calibrate_pairs.py`, `scripts/calibrate_score.py`, and
  `evals/check_contrib.py` all begin with `from __future__ import annotations`
  directly after the module docstring. Match that placement.
- `.github/workflows/evals.yml:15` — single CI leg, `python-version: "3.11"`.
- `README.md:267` and `README.md:374` say "439 deterministic cases" /
  "439 cases"; the suite actually holds 440 `target=="script"` rows
  (439 pass + 1 documented xfail, FP-06). `README.md:294` ("439 pass, 1 xfail")
  is already correct. Fix the two imprecise sites while this plan is in the
  README anyway.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Full suite | `python3 evals/run_adversarial.py` | exit 0; final line `PASS 439  XFAIL 1 ... FAIL 0` |
| Syntax check | `python3 -m py_compile scripts/*.py evals/*.py` | exit 0, silent |
| Scanner self-check on README | `python3 scripts/banned_phrase_scan.py README.md` | exit 0, `"total_violations": 0` |

## Scope

**In scope** (the only files you should modify):
- The 17 files listed above (one-line insertion each)
- `.github/workflows/evals.yml`
- `README.md` (two phrases only)

**Out of scope** (do NOT touch):
- Any annotation itself — do not rewrite `str | None` to `Optional[str]`;
  the future-import fixes evaluation without churn.
- `docs/PRODUCT.md` and other references — no floor claim appears there
  as of 217c218 (verify with `grep -rn "3\.8" docs/ references/`; if a claim
  appears, update it identically).
- Anything in `evals/adversarial-evals.json`.

## Git workflow

- Branch: `advisor/001-python-floor` off `main`
- One commit; message style matches repo (`git log --oneline -5` shows
  sentence-case imperative, e.g. "Add codex-jsonl harvester adapter…")
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add the future-import to the 17 files

In each listed file, insert `from __future__ import annotations` as the first
import, immediately after the module docstring (before any other import),
matching `scripts/harvest_samples.py`'s layout exactly.

**Verify**: `grep -L "from __future__ import annotations" scripts/*.py evals/*.py | xargs grep -l ": *\(dict\|list\|set\|tuple\)\[\|| None"` → no output
(every file that still lacks the import has no evaluated modern annotation).

### Step 2: Prove 3.8-compatible imports mechanically

Python 3.8 may not be installed locally; simulate the failure class instead:
for each of the 17 files, confirm the module compiles and that no *runtime*
subscripted generic remains outside annotation position:

**Verify**: `python3 -m py_compile scripts/*.py evals/*.py` → exit 0
**Verify**: `grep -n "get_type_hints" scripts/*.py evals/*.py` → no output
(nothing resolves annotations at runtime, so deferral is safe).

### Step 3: Add a floor leg to CI

In `.github/workflows/evals.yml`, convert the job to a matrix over
`python-version: ["3.8", "3.11"]`. Keep every existing step. The 3.8 leg
proves import-time compatibility via the existing
`python -m py_compile scripts/*.py evals/*.py` step **plus** add one new step
before it, so a plain compile pass can't hide import-time TypeErrors:

```yaml
      - name: Import all scripts (annotation floor check)
        run: |
          for f in scripts/*.py evals/*.py; do python3 -c "import runpy, sys; sys.argv=['x','--help']" >/dev/null 2>&1; python3 - <<EOF
          import importlib.util, pathlib, sys
          p = pathlib.Path("$f")
          spec = importlib.util.spec_from_file_location(p.stem, p)
          m = importlib.util.module_from_spec(spec)
          sys.path.insert(0, str(p.parent))
          try:
              spec.loader.exec_module(m)
          except SystemExit:
              pass
          EOF
          done
```

NOTE: some scripts execute argparse or read stdin at import only under
`if __name__ == "__main__"` — module import must not block. If any file hangs
or errors on import for a non-annotation reason, STOP (condition 3).
A simpler alternative acceptable here: a one-line
`python3 -c "import ast, pathlib; [compile(ast.parse(pathlib.Path(f).read_text()), f, 'exec') for f in ...]"`
does NOT catch evaluated annotations — the exec_module approach (or actually
running the suite on the 3.8 leg) is required. Running the full suite on both
legs is the simplest correct choice if runtime permits (~30s per leg).

**Verify**: `python3 -c "import yaml" 2>/dev/null || true; grep -c "3.8" .github/workflows/evals.yml` → at least 1

### Step 4: Fix the two README count phrasings

Change `README.md:267` "439 deterministic cases" →
"440 deterministic script cases (439 pass, 1 documented xfail)" and
`README.md:374` "Source of truth: 439 cases" → "Source of truth: 440 script
cases". Leave line 294 untouched.

**Verify**: `python3 scripts/banned_phrase_scan.py README.md` → `"total_violations": 0`
**Verify**: `grep -c "439 deterministic cases" README.md` → 0

## Test plan

No new eval rows: this is an import-time property no subprocess row can
express on a newer interpreter. The CI matrix leg IS the regression test.
Locally, the full suite run in Done criteria proves no behavior drift.

## Done criteria

- [ ] `python3 evals/run_adversarial.py` → exit 0, `PASS 439  XFAIL 1`, `FAIL 0`
- [ ] All 17 listed files contain `from __future__ import annotations`
- [ ] `.github/workflows/evals.yml` has a matrix including `"3.8"`
- [ ] `grep -rn "Python 3.8" README.md` still matches (the claim stands, now true)
- [ ] `git status` shows no files outside the in-scope list
- [ ] `plans/README.md` status row updated

## STOP conditions

- The "Current state" excerpt at `banned_phrase_scan.py:82` doesn't match.
- The suite fails after adding the future-imports (would mean some code
  path resolves annotations at runtime — investigate, don't patch around).
- A module errors or hangs on bare import for a non-annotation reason.
- You find a `get_type_hints`/`typing.get_args` call site on these modules.

## Maintenance notes

- Every NEW script must carry the future-import until the floor is raised;
  consider noting this in `AGENTS.md`'s conventions when next edited (out of
  scope here).
- If the maintainer later decides 3.10+ is the real floor, delete the CI 3.8
  leg and the README claim together in one commit — they are a pair.
