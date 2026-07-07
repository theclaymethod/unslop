# Plan 003: Validate contribute's pattern-name slug and fix the exclamation ReDoS

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. On
> any STOP condition, stop and report. When done, update `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- scripts/contribute.py scripts/banned_phrase_scan.py evals/adversarial-evals.json evals/check_contrib.py`
> Mismatched excerpts = STOP.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

Two verified security findings in the same neighborhood. (1)
`scripts/contribute.py` joins the user/agent-supplied `--pattern-name`
directly into a filesystem path: `../../x` escapes `.unslop/contrib/` and an
absolute path replaces the base entirely (pathlib join semantics), writing
four files anywhere the user can write — and the only containment check runs
*after* the writes, as a crash. (2) The `exclamation_overuse` structural
regex backtracks quadratically (measured: 343ms at 8k chars, 5.6s at 32k) and
is called with no timeout from in-process consumers (`harvest_samples`'s
tripwire, `run_mimic_refine`'s gates), so an ASCII-banner-like region in a
harvested transcript can hang a harvest for minutes.

## Current state

- `scripts/contribute.py:218-219`:
  ```python
      bundle = CONTRIB_ROOT / args.pattern_name
      bundle.mkdir(parents=True, exist_ok=True)
  ```
  then writes `row_fn.json`, `manifest.json`, `snippet.txt`, `report.md`
  into `bundle` (lines ~230-234), and only at line 235 calls
  `bundle.relative_to(ROOT)` inside the success print — which raises
  `ValueError` *after* the files exist, for escaping paths.
- `scripts/banned_phrase_scan.py:966` (inside `STRUCTURAL_PATTERNS`):
  ```python
          "pattern": r"!(?:(?!\n\n)\s)+(?:(?!\n\n)[^.])*!",
  ```
  The `\s`-run and `[^.]`-run overlap (`\s ⊂ [^.]`), so a lone `!` followed by
  a long whitespace-ish run with no closing `!` backtracks quadratically.
- The pattern is pinned by two existing rows in `evals/adversarial-evals.json`:
  `FP-37` (exclamations in separate paragraphs must NOT flag) and `REC-17`
  (stacked exclamations in one paragraph must flag, category
  `exclamation_overuse`). Your replacement must keep both green.
- Contribute's gate: `evals/check_contrib.py` (invoked by the
  `contribute-suite` gate) uses a conforming fixed slug; it will not object
  to added validation.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Full suite | `python3 evals/run_adversarial.py` | exit 0, FAIL 0 |
| Targeted rows | `python3 evals/run_adversarial.py --only FP --only REC --only CONTRIB` | all pass |
| Contrib gate | `python3 evals/check_contrib.py` | exit 0 |
| ReDoS timing (before) | `python3 -c "import time,re; p=re.compile(r'!(?:(?!\n\n)\s)+(?:(?!\n\n)[^.])*!'); s='! '+' '*16000+'x'; t=time.time(); list(p.finditer(s)); print(round(time.time()-t,2))"` | currently ≈1.4s; after fix: <0.05s |

## Scope

**In scope**: `scripts/contribute.py`, `scripts/banned_phrase_scan.py`
(the one pattern string only), `evals/adversarial-evals.json` (new rows).

**Out of scope**: every other structural pattern; `references/contribute.md`
(the doc describes behavior that doesn't change — valid slugs were always the
documented shape); `evals/check_contrib.py` unless a new gate case is added
there (allowed but optional).

## Git workflow

- Branch: `advisor/003-slug-and-redos`; eval rows red-first per repo rule;
  sentence-case imperative commit message.

## Steps

### Step 1: Red rows

Add to `evals/adversarial-evals.json` (check current max ids for CONTRIB/ROB
prefixes first):
1. A CONTRIB row: run
   `["python3", "scripts/contribute.py", "scaffold", "--pattern-name", "../evil", ...]`
   (copy the full required argv shape from an existing CONTRIB row or
   `check_contrib.py`'s invocation) asserting `exit_code: 2` and
   `stdout_contains` a JSON error naming the slug, and
   `stderr_not_contains: "Traceback"`. Also assert via an `sh -c` wrapper that
   `test ! -e .unslop/evil` after the run (no escaped write).
2. A perf-guard row for the regex:
   `["sh", "-c", "timeout 5 python3 -c \"...finditer on '! '+' '*32000+'x'...\""]`
   asserting exit 0 (i.e. completes well under the timeout).

**Verify**: both rows FAIL at 217c218 behavior (row 1 fails because the write
currently succeeds/crashes-after-write; row 2 fails by timeout).

### Step 2: Slug validation in contribute

At the top of the scaffold command handler in `scripts/contribute.py`
(before any path join or mkdir):

```python
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
...
    if not SLUG_RE.match(args.pattern_name):
        print(json.dumps({"error": f"invalid pattern name: {args.pattern_name!r}; use lowercase letters, digits, - or _"}))
        return 2
```

Keep the existing post-hoc `relative_to` (belt and suspenders), but it must
now be unreachable for bad slugs. Match the file's existing error-JSON style
(grep for `"error"` in the file and copy that shape exactly).

**Verify**: step 1's CONTRIB row passes; `python3 evals/check_contrib.py` → exit 0.

### Step 3: Linearize the exclamation pattern

Replace the pattern at `scripts/banned_phrase_scan.py:966` with a
non-overlapping equivalent. Recommended shape:

```python
"pattern": r"![^\S\n]*(?:\n(?!\n))?[^.!\n]*(?:\n(?!\n))?[^.!\n]*!"
```

is complex; a simpler, verified-equivalent intent: two `!` in the same
paragraph with no `.` between them. The cleanest linear form is to disallow
`!` inside the interior run and make whitespace/non-period runs disjoint:

```python
"pattern": r"!(?:(?!\n\n)[^.!])*!"
```

— the interior excludes `!` itself (each `!` then anchors at most one match
attempt forward, killing the quadratic) and still spans anything
non-period within a paragraph. Confirm intent equivalence against FP-37 and
REC-17 (both must keep their current outcome) and against the timing probe.

**Verify**:
- `python3 evals/run_adversarial.py --only FP --only REC` → all pass
- timing probe from the commands table → <0.05s at 32k
- step 1's perf row passes

## Test plan

The two new rows plus the existing FP-37/REC-17 are the tests. Optionally add
one more REC-style row with three stacked `!` sentences to pin multi-match
behavior if the interior-excludes-`!` change alters match *count* semantics
(check `min_matches` on the pattern definition — if the pattern entry has
`min_matches > 1`, matches-per-paragraph counting matters; verify by reading
the pattern's dict entry in full before editing).

## Done criteria

- [ ] Full suite: exit 0, FAIL 0, PASS = previous + new rows
- [ ] `.unslop/` contains no `evil` artifacts; `git status` clean outside scope
- [ ] Timing probe < 0.05s
- [ ] `python3 evals/check_pattern_coverage.py` → OK (pattern still covered)
- [ ] `plans/README.md` updated

## STOP conditions

- The pattern entry at :966 has `min_matches` or other fields whose semantics
  you cannot preserve confidently with the new regex — report the entry
  verbatim and your best alternative instead of guessing.
- FP-37 or REC-17 flips and you cannot restore both with a linear pattern in
  two attempts.
- `contribute.py`'s error-JSON convention differs from the sketch — match the
  file, and if there is no error-JSON convention at all, STOP and report.

## Maintenance notes

- Any future structural pattern with two adjacent unbounded quantified runs
  over overlapping character classes reintroduces this bug class; the perf
  row added here guards only this pattern. A general regex-budget test is
  deliberately out of scope (candidate future gate).
- Reviewer: verify the slug regex matches what `references/contribute.md`
  documents as valid names.
