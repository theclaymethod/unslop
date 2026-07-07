# Plan 002: Harden every input surface against bad bytes and unreadable files

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- scripts/ evals/run_local.py evals/adversarial-evals.json`
> On any in-scope drift, compare "Current state" excerpts before proceeding;
> mismatch = STOP.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none (lands cleanly before or after 001; if 004 has landed, its schema gate will validate your new rows automatically)
- **Category**: bug
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

The scanners are the product's "always-on" layer: host agents pipe arbitrary
prose to them and parse the JSON reply as a gate result. Today,
non-UTF-8 stdin produces a raw `UnicodeDecodeError` traceback (reproduced:
`printf '\xff\xfehello' | python3 scripts/banned_phrase_scan.py`) in eight
scripts — violating the repo's own no-traceback contract that eval rows
ROB-04..08/12/13 enforce for missing files and empty stdin. Separately,
`harvest_samples.py` aborts an entire harvest batch when any single file in a
scanned directory is non-UTF-8 or unreadable, and `evals/run_local.py`
tracebacks when the `claude` CLI is absent instead of reporting a per-case
failure. The fix idiom (`errors="replace"`) already exists in the voice tools.

## Current state

- Unguarded `sys.stdin.read()` (verified list at 217c218):
  `scripts/banned_phrase_scan.py:1153`, `scripts/structure_scan.py:294`,
  `scripts/silhouette_scan.py:387`, `scripts/readability_metrics.py:268`,
  `scripts/extract_constraints.py:170`, `scripts/suggest.py:184`,
  `scripts/check_suggestions.py:188`, `scripts/voice_score.py:228`.
- Unguarded whole-file reads in harvest:
  - `scripts/harvest_samples.py:139` (`detect_jsonl_adapter` — full
    `read_text().splitlines()`), `:222` (`iter_claude_jsonl`), `:274`
    (`iter_codex_jsonl`), `:351` (`iter_text_file` — `path.read_text()`),
    with no try/except in `collect_sources` (`:361-390`).
- `evals/run_local.py:58-61`:
  ```python
      try:
          proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
      except subprocess.TimeoutExpired:
          return label, False, "timeout"
  ```
  No `FileNotFoundError`/`OSError` arm; contrast the harness convention at
  `evals/run_model_parity.py:404` which catches
  `(FileNotFoundError, OSError, subprocess.TimeoutExpired)` and degrades.
- The repo's established safe-read idiom (match it):
  `evals/run_mimic_refine.py:91` — `p.read_text(errors="replace")`; also used
  at `:132`, `:164`, `:179`.
- Existing robustness eval rows to model new rows on: open
  `evals/adversarial-evals.json` and read rows with ids starting `ROB-`
  (e.g. ROB-04 "missing file, no traceback"). Each is
  `{"id", "title", "target": "script", "command": [...], "stdin"?, "assertions": [...]}`
  with assertion types like `exit_code`, `stdout_contains`,
  `stderr_not_contains`.
- File-path reads in the same eight scanner scripts (e.g.
  `silhouette_scan.py:385` `path.read_text()`) share the encoding risk for
  file input; include them.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Full suite | `python3 evals/run_adversarial.py` | exit 0; `PASS 44x  XFAIL 1 ... FAIL 0` (44x = 439 + your new rows) |
| Repro (before) | `printf '\xff\xfehello' \| python3 scripts/banned_phrase_scan.py` | currently: traceback. After step 1: JSON, exit 0 or 1, no traceback |
| Row slice | `python3 evals/run_adversarial.py --only ROB` | all ROB rows pass |
| Coverage gate | `python3 evals/check_pattern_coverage.py` | `pattern-coverage gate OK` |

## Scope

**In scope**:
- The 8 scripts listed (stdin + their file-read paths)
- `scripts/harvest_samples.py`
- `evals/run_local.py`
- `evals/adversarial-evals.json` (new ROB and HARV rows)

**Out of scope**:
- `scripts/voice_profile.py`, `scripts/voice_card.py`,
  `evals/run_mimic_refine.py` — already use `errors="replace"`.
- Any change to JSON output keys, exit-code semantics, or the non-English
  decline logic.
- `evals/run_model_parity.py` — already correct; it is the exemplar.

## Git workflow

- Branch: `advisor/002-input-robustness`
- Eval-first repo rule (from `CLAUDE.md`): add the new eval rows FIRST,
  confirm they fail (red), then fix. Commit rows+fix together or rows-then-fix
  as two commits; message style: sentence-case imperative.

## Steps

### Step 1: Add failing eval rows (red first)

Append to the `evals` array in `evals/adversarial-evals.json` (respect the
id numbering — check the current max ROB/HARV numbers first with
`python3 -c "import json; print(sorted(r['id'] for r in json.load(open('evals/adversarial-evals.json'))['evals'] if r['id'].startswith(('ROB','HARV'))))"`):

1. One row per scanner-family entrypoint (minimum: `banned_phrase_scan`,
   `structure_scan`, `silhouette_scan`, `suggest`) asserting bad-bytes stdin
   is handled. Rows can't carry raw bytes in JSON `stdin`, so use a command
   wrapper: `["sh", "-c", "printf '\\xff\\xfeIt is a testament to progress' | python3 scripts/banned_phrase_scan.py"]`
   with assertions: `stderr_not_contains: "Traceback"` and `exit_code` 1
   (the slop phrase must still be detected after replacement-decoding — this
   proves the scan ran rather than short-circuited).
2. One HARV row: point `harvest_samples.py` at a fixture directory containing
   one good `.md` and one binary file (create
   `evals/fixtures/harvest/fixture_bad_encoding/` with `good.md` containing a
   distinctive marker sentence and `bad.bin` written via a small
   `python3 -c` in the row's sh wrapper, or commit the binary fixture —
   prefer generating it in the command so no binary is committed). Assert:
   exit 0, stdout contains the good marker, `stderr_not_contains: "Traceback"`.
3. One row for `run_local.py`: `["python3", "evals/run_local.py", "--help"]`
   is not enough — instead assert the missing-binary path:
   `["sh", "-c", "PATH=/usr/bin:/bin python3 evals/run_local.py /dev/null 2>&1; true"]`
   is fragile; simpler and sufficient: make this a unit-style row invoking a
   tiny inline harness, or SKIP the row and rely on Step 4's code change +
   suite green. If a clean row shape isn't achievable in 30 minutes, skip the
   row, note it in the commit message, and proceed (the parity harness
   convention it copies is already row-covered).

**Verify**: `python3 evals/run_adversarial.py --only ROB --only HARV` → your new rows FAIL, all pre-existing pass.

### Step 2: Fix the eight stdin/file readers

In each script's `main`, replace `text = sys.stdin.read()` with:
```python
text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
```
and each CLI-path `path.read_text()` with `path.read_text(errors="replace")`.
Do not touch any other logic.

**Verify**: `printf '\xff\xfehello' | python3 scripts/structure_scan.py` → JSON output, no traceback (repeat for all 8).

### Step 3: Guard harvest per-file

In `scripts/harvest_samples.py`: change the two JSONL `read_text()` calls and
`iter_text_file`'s read to `errors="replace"`, and wrap the per-file dispatch
in `collect_sources` in `try/except (OSError, UnicodeDecodeError)` that
appends `{"path": str(path), "reason": "unreadable"}` to the existing
warnings/drop-stats mechanism (find the existing drop-reason plumbing used by
`instruction-injection` drops and reuse its shape) and continues.

**Verify**: the HARV row from step 1 now passes.

### Step 4: Widen run_local's except

Match the parity-harness convention:
```python
    except subprocess.TimeoutExpired:
        return label, False, "timeout"
    except (FileNotFoundError, OSError) as e:
        return label, False, f"runner unavailable: {e}"
```

**Verify**: `python3 -c "import sys; sys.path.insert(0,'evals'); import run_local"` → imports clean; full suite green.

## Test plan

The new ROB/HARV rows ARE the tests (this repo's convention — eval rows over
unit tests). Cover: bad-bytes stdin per scanner family, mixed-encoding harvest
directory, and (if achievable) missing-runner degradation. Model row structure
on existing ROB-04.

## Done criteria

- [ ] `python3 evals/run_adversarial.py` → exit 0, FAIL 0, PASS = 439 + new rows
- [ ] `printf '\xff\xfehello' | python3 scripts/<each of 8>.py` → no `Traceback` on stderr
- [ ] `python3 evals/check_pattern_coverage.py` → OK
- [ ] `python3 evals/build_shared_benchmark.py --check` → up to date (no skill rows added)
- [ ] `git status` clean outside in-scope files
- [ ] `plans/README.md` updated

## STOP conditions

- Excerpts don't match current code (drift).
- Any PRE-EXISTING row fails after your change — especially ROB or LANG rows:
  the decode-replace must not alter the non-English decline behavior
  (`is_probably_english` runs on the decoded text; replacement chars reduce
  function-word share, which is fine — decline still requires zero findings —
  but if a LANG row flips, stop).
- The harvest warnings mechanism you're told to reuse doesn't exist under
  that name — report what the actual drop-stats shape is instead of inventing
  a parallel one.

## Maintenance notes

- Future scripts reading stdin must use the buffer-decode idiom; the ROB rows
  added here only cover existing entrypoints.
- Reviewer: check that `errors="replace"` wasn't applied to any file the
  suite compares byte-exactly (fixtures are read by tests as data — the
  in-scope list deliberately excludes eval fixture readers).
