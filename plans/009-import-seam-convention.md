# Plan 009: Standardize the check-script import seam and document it

> **Executor instructions**: Follow step by step; verify each step; STOP
> conditions binding. Update `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- evals/ CLAUDE.md AGENTS.md`
> Mismatched excerpts = STOP.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none (avoid running concurrently with 004/007 — same files)
- **Category**: dx
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

`evals/check_*.py` scripts import repo code three different ways: (a)
`sys.path.insert(0, ROOT)` then `from scripts.banned_phrase_scan import …`
(`check_taboo_parity.py:8-10`, `check_pattern_coverage.py:29-31`,
`check_silhouette.py:29-31`); (b) insert the `scripts/` dir and import bare
(`check_pairs.py:6`); (c) route through `evals/_check_support.py`
(`check_voice.py:10`, `check_contrib.py:12`). A contributor adding the next
check has three competing precedents and no written rule. This plan picks the
winner, converts the outliers, and writes the rule down. It deliberately does
NOT re-package the repo (single-underscore shared modules + path insertion is
the accepted dual-mode compromise; full packaging was audited and judged not
worth it).

## Current state

- The winner (convention to standardize on), from `evals/check_voice.py:8-12`
  and `evals/_check_support.py`:
  ```python
  from pathlib import Path
  import sys
  sys.path.insert(0, str(Path(__file__).resolve().parent))
  from _check_support import ROOT, run, load_evals
  sys.path.insert(0, str(ROOT))          # when scripts.* imports are needed
  from scripts.banned_phrase_scan import scan_for_violations
  ```
  (Read `check_voice.py`'s actual header and treat IT as the exemplar; the
  sketch above is from memory of the shape, not a paste.)
- Outlier list to convert (verify each with a quick head-read):
  `evals/check_pairs.py` (bare scripts-dir import), and any check that
  re-defines `ROOT`/`run()` locally instead of importing `_check_support`
  (grep: `grep -ln "def run(" evals/check_*.py` and
  `grep -ln "^ROOT = " evals/check_*.py` — anything hitting both patterns
  AND not importing `_check_support`).
- Documentation targets: `evals/CHECKS.md` (add a short "Writing a new
  check" subsection — note this file has a gate-pinned JSON block via
  `check_gates_doc.py`/DOC-03; your prose must not touch that block) and one
  line in `CLAUDE.md`'s "Add a New Pattern" section pointing to it.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Full suite | `python3 evals/run_adversarial.py` | exit 0, FAIL 0 |
| Each converted check | `python3 evals/check_pairs.py` (etc.) | same exit + output as before conversion |
| Gate doc | `python3 evals/check_gates_doc.py` | ok (prose edits must not break the pinned block) |
| Scanner hygiene | `python3 scripts/banned_phrase_scan.py evals/CHECKS.md` | 0 hard violations |

## Scope

**In scope**: outlier `evals/check_*.py` headers (imports only — zero logic
changes), `evals/CHECKS.md` (one new prose subsection), `CLAUDE.md` (one
line).

**Out of scope**: `scripts/*` import mechanics (dual-mode pattern there is
settled), `_check_support.py` itself (unless a converted check needs an
existing helper exposed — adding an export is fine, adding new behavior is
not), any check's assertions or logic.

## Git workflow

- Branch: `advisor/009-import-convention`; one commit.

## Steps

### Step 1: Convert the outliers

For each outlier: replace its import header with the exemplar shape; delete
any local `run()`/`ROOT` duplicates in favor of `_check_support` imports.
Capture each check's stdout+exit on a pre-conversion run; compare after.

**Verify**: per-check before/after outputs identical; full suite green.

### Step 2: Write the rule

In `evals/CHECKS.md`, add a "Writing a new check" subsection (~8 lines):
import seam (exemplar snippet), `_check_support` helpers available, exit-code
convention (0 ok / 1 findings / 2 usage), and the gate-registration +
CHECKS-regen step. Add one pointer line to `CLAUDE.md` §"Add a New Pattern".

**Verify**: `check_gates_doc.py` ok; `banned_phrase_scan.py evals/CHECKS.md`
→ 0 hard; `python3 scripts/structure_scan.py --genre docs evals/CHECKS.md` → clean.

## Test plan

No new rows. Identical before/after outputs on every converted check is the
whole proof; the suite re-runs them all anyway via their gates.

## Done criteria

- [ ] `grep -ln "def run(" evals/check_*.py` → only `_check_support.py`-importers remain clean (no local run() outside it)
- [ ] Full suite green; every individual check exits as before
- [ ] CHECKS.md subsection exists; scanners clean on it; DOC-03 gate green
- [ ] `plans/README.md` updated

## STOP conditions

- A converted check's output differs in any byte — its local helper had
  divergent behavior (e.g. a different timeout); report the divergence
  instead of absorbing it silently.
- The CHECKS.md pinned JSON block fails DOC-03 after your prose edit —
  you touched the generated region; revert and re-place the prose.

## Maintenance notes

- Plan 004's new check (if landed after this) should follow the documented
  seam; if 004 landed first, converting its header is in scope here.
- Reviewer: confirm zero logic diffs — this plan is imports and prose only.
