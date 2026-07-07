# Plan 008: Unify the drifted prose-view helpers shared by the structural scanners

> **Executor instructions**: Follow step by step; verify each step; STOP
> conditions binding. Update `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- scripts/structure_scan.py scripts/silhouette_scan.py scripts/_lang.py`
> Mismatched excerpts = STOP.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED — reconciling the drift can shift metric values; two gates pin them
- **Depends on**: none
- **Category**: tech-debt
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

`structure_scan.py` and `silhouette_scan.py` each carry private copies of the
tokenizer (`words`), markdown stripper, and paragraph splitter — and the
strippers have already drifted: structure blanks blockquote lines
(`structure_scan.py:66`), silhouette doesn't; silhouette strips `**bold**`
markup (`silhouette_scan.py:117`), structure doesn't. Two scanners meant to
compose therefore analyze two different "prose views" of the same document.
An earlier consolidation pass created `scripts/_lang.py` for exactly this
class of problem (English heuristics) — this plan extends it to the prose
view, reconciling the drift deliberately instead of silently.

## Current state

- `scripts/structure_scan.py:58-59` — `words()`; byte-identical to
  `scripts/silhouette_scan.py:100-101`.
- `scripts/structure_scan.py:62-72` — `strip_markdown_for_prose`; handles
  blockquotes+headers at `:66`:
  ```python
      if re.match(r"\s*>", line) or re.match(r"\s{0,3}#{1,6}\s+", line):
  ```
- `scripts/silhouette_scan.py:108-119` — `strip_md`; strips bold at `:117`:
  ```python
      line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
  ```
  (no blockquote handling).
- `scripts/structure_scan.py:75-77` and `scripts/silhouette_scan.py:122-125`
  — paragraph splitters, functionally identical.
- `scripts/_lang.py` — the established shared-module pattern (dual-mode
  import via `sys.path.insert(0, str(Path(__file__).resolve().parent))` then
  `from _lang import …` — copy the import mechanics from
  `structure_scan.py`'s top).
- Pinning gates (your safety net AND your constraint):
  - `python3 evals/check_silhouette.py --reference` — silhouette's committed
    human-reference stats must stay byte-identical unless deliberately
    regenerated.
  - `python3 evals/check_silhouette.py --separation` — 12/12 AI flagged,
    0/8 human flagged, must hold.
  - The full suite's structure rows (many REC/FP rows) pin structure_scan.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Full suite | `python3 evals/run_adversarial.py` | exit 0, FAIL 0 |
| Silhouette ref | `python3 evals/check_silhouette.py --reference` | ok, unchanged |
| Separation | `python3 evals/check_silhouette.py --separation` | 12/12, 0/8 |
| Structure spot | `python3 scripts/structure_scan.py README.md` | unchanged flag set vs HEAD (capture before/after) |

## Scope

**In scope**: `scripts/_lang.py` (add helpers), `scripts/structure_scan.py`,
`scripts/silhouette_scan.py` (replace local copies with imports).

**Out of scope**: metric formulas, thresholds, genre tables, reference stats
regeneration (STOP rather than regenerate), `evals/*`.

## Git workflow

- Branch: `advisor/008-shared-prose-view`; single commit acceptable (pure
  refactor); capture before/after scanner outputs in the commit message.

## Steps

### Step 1: Decide the reconciliation — parameterize, don't average

The drift is load-bearing until proven otherwise. Move to `_lang.py`:

```python
def words(text): ...                      # identical copy, one home
def paragraphs(text): ...                 # identical copy, one home
def strip_markdown_for_prose(text, *, blank_blockquotes=False, strip_bold=False):
    ...
```

with the union of both behaviors behind keyword flags. Callers preserve
their exact current behavior: structure passes `blank_blockquotes=True`,
silhouette passes `strip_bold=True`. NO caller-visible change in this plan —
whether the flags should converge is a maintainer decision recorded in
Maintenance notes, not an executor improvisation.

**Verify**: `python3 - <<'EOF'` — import both scanners' modules, run each
of their OLD local functions (from git stash or a pre-change copy in /tmp)
and the new shared function with the matching flags over
`evals/fixtures/silhouette/` docs (or any 3 fixture .md files), assert
byte-equal outputs. Simplest: before editing, snapshot
`python3 scripts/structure_scan.py <file>` and
`python3 scripts/silhouette_scan.py <file>` for 3 fixture files to /tmp;
after editing, diff — must be byte-identical.

### Step 2: Swap the callers

Delete the local copies in both scanners; import from `_lang` with the
dual-mode pattern already at the top of each file (both already import
`_lang`… structure does; silhouette does NOT import `_lang` at 217c218 —
if plan 006 landed first it now does; otherwise add the same import block
structure_scan uses).

**Verify**:
- 3-file output snapshots byte-identical to before
- `python3 evals/check_silhouette.py --reference` → unchanged
- `--separation` → 12/12, 0/8
- Full suite green
- Dual-mode check: `python3 -c "from scripts.structure_scan import scan" && python3 scripts/structure_scan.py README.md >/dev/null` → both work

## Test plan

No new rows — this is behavior-preserving by construction, and the byte-
identical snapshot check plus the two silhouette gates plus 440 rows are the
proof. (If any output differs, that IS the drift biting — STOP condition.)

## Done criteria

- [ ] `grep -n "def strip_md\|def strip_markdown_for_prose\|def words" scripts/structure_scan.py scripts/silhouette_scan.py` → no local definitions remain
- [ ] Snapshot diff: byte-identical scanner outputs on 3 fixture files
- [ ] Both silhouette gates green; full suite green
- [ ] `plans/README.md` updated

## STOP conditions

- Any output byte differs after the swap — do not "fix forward"; the flags
  aren't capturing the real behavioral difference. Report the diff.
- Silhouette's reference check reports drift — you touched scoring; revert.
- Import cycle appears between `_lang` and a scanner (would happen if a
  helper needs scanner constants) — report; the helper may need a third
  module instead.

## Maintenance notes

- OPEN QUESTION for the maintainer, deliberately not resolved here: should
  both scanners converge on one prose view (blockquotes blanked AND bold
  stripped)? Converging changes silhouette's committed reference stats and
  needs a deliberate regeneration + separation re-verification — a small
  follow-up plan, eval-first.
- Reviewer: the parameterized function must contain BOTH original code paths
  verbatim, not a rewrite — that's what makes byte-identity achievable.
