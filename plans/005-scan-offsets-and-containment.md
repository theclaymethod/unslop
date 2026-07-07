# Plan 005: Compute violation offsets once, correctly, and make containment linear

> **Executor instructions**: Follow step by step; verify each step; STOP
> conditions are binding. Update `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- scripts/banned_phrase_scan.py evals/adversarial-evals.json`
> Mismatched excerpts = STOP.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED — this touches span semantics that many eval rows pin; the suite is your safety net
- **Depends on**: plans/004 (schema gate validates your new rows) — soft dependency, proceed without it if 004 isn't DONE
- **Category**: perf + bug
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

`scan_for_violations` in `scripts/banned_phrase_scan.py` has three defects
with one root cause — positions are recomputed instead of carried:

1. **Quadratic span reconstruction**: for every violation it re-splits the
   whole document (`text.splitlines()[:line-1]`) and re-sums line lengths.
   Profiled: `splitlines` called 6,779× (1.38s) on a 6k-sentence doc.
2. **Quadratic containment**: the overlap filter is `any(...)` over all spans
   per violation — 45.9M comparisons on the same doc. Measured end-to-end:
   1.24s @2.5k sentences → 3.63s @5k → 11.5s @10k (clean quadratic).
3. **Wrong offsets on CRLF and case-expanding input**: matches run on
   `scan_text.lower()` but line/column are computed against original `text`;
   `splitlines()` treats `\r\n` as one line break but the reconstruction adds
   back `+1` char per line; and `str.lower()` is not length-preserving for
   e.g. `İ` (U+0130), shifting every subsequent position. The suite is
   LF/ASCII so no row catches this.

Carrying `match.start()`/`match.end()` through as the single source of truth
fixes all three at once.

## Current state

All in `scripts/banned_phrase_scan.py` (function `scan_for_violations`,
starting ~line 1041):

```python
def scan_for_violations(text: str, include_quoted: bool = False) -> list[Violation]:
    violations: list[Violation] = []
    scan_text = mask_ignored_spans(text, include_quoted=include_quoted)
    text_lower = scan_text.lower()

    # Check banned phrases
    for phrase, info in BANNED_PHRASES.items():
        for match in _phrase_pattern(phrase).finditer(text_lower):
            pos = match.start()
            # Calculate line number and column
            line_num = text[:pos].count('\n') + 1
            line_start = text.rfind('\n', 0, pos) + 1
            column = pos - line_start + 1
```

(`pos` indexes `text_lower` = lowered *masked* text, but is sliced against
original `text` — only safe because masking is length-preserving and input is
ASCII-ish.)

Span reconstruction + containment (~lines 1101-1122):

```python
    for v in violations:
        start = sum(len(line) + 1 for line in text.splitlines()[:v["line_number"] - 1]) + v["column"] - 1
        end = start + len(v["phrase"])
        spans.append((start, end))
    ...
    for i, v in enumerate(violations):
        start, end = spans[i]
        contained = any(
            i != j and other_start <= start and end <= other_end and (other_end - other_start) > (end - start)
            for j, (other_start, other_end) in enumerate(spans)
        )
        if not contained or v["category"] in freq_gated:
            filtered.append(v)
```

The `freq_gated` exemption (frequency-gated document-level categories are
never containment-suppressed) is load-bearing and documented in the comment
above it — preserve it exactly.

**Key assumption to verify first**: `mask_ignored_spans` is length-preserving
(replaces masked spans with same-length filler). Verify by reading the
function; if it is NOT length-preserving, STOP (condition 1).

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Full suite | `python3 evals/run_adversarial.py` | exit 0, FAIL 0 |
| Perf probe | `python3 - <<'EOF'` … build a doc of 10,000 slop sentences ("This is a testament to progress. " ×10000), time `scan_for_violations` via import | before ≈11s; after <1.5s |
| Coverage | `python3 evals/check_pattern_coverage.py` | OK |

## Scope

**In scope**: `scripts/banned_phrase_scan.py` (`scan_for_violations` and, if
needed, a small helper); `evals/adversarial-evals.json` (new rows: CRLF
fixture row, case-fold row, perf row).

**Out of scope**: `mask_ignored_spans` itself; `_phrase_pattern`; every
STRUCTURAL_PATTERNS entry; the JSON output schema (keys `line_number`,
`column`, `context`, etc. must keep their meaning — 1-based line/col against
the ORIGINAL text).

## Git workflow

- Branch: `advisor/005-scan-offsets`; rows red-first; sentence-case commits.

## Steps

### Step 1: Red rows

1. CRLF row: stdin document with `\r\n` line endings where a banned phrase
   sits on line 3, asserting `json` line_number == 3 (build the row with an
   `sh -c printf` wrapper; read an existing `json`-assertion row for shape).
   At 217c218 this may pass or fail depending on how the current arithmetic
   nets out — if it passes, tighten the assertion to also check `column`.
   The row's purpose is to pin correct behavior; confirm it fails against a
   deliberately broken variant if it doesn't fail against current code.
2. Case-fold row: document containing `İ` before a banned phrase; assert
   the reported `context` actually contains the phrase text.
3. Perf row: `sh -c` with `timeout 10` running the scanner over a generated
   ~8k-sentence slop document from stdin; assert exit code 1 (violations
   found) — currently this may exceed 10s (red), after the fix it must be
   comfortably under.

**Verify**: new rows behave as described; all pre-existing rows still pass.

### Step 2: Carry offsets

Refactor `scan_for_violations`:
- Compute `line_starts` once: offsets of each line start in **original
  `text`**, built by scanning `text` for `\n` (list of ints, prepend 0).
- For each match, record `span = (match.start(), match.end())` (indices into
  `scan_text`; valid for `text` because masking is length-preserving — but
  **derive them from `scan_text` matches run WITHOUT `.lower()`**: change
  `_phrase_pattern` usage to compile/apply with `re.IGNORECASE` on
  `scan_text` directly, eliminating `text_lower` and the case-fold length
  hazard. First check `_phrase_pattern`'s construction — if patterns embed
  literal-case alternations or the function is shared, add the flag at the
  `finditer` call site via a locally compiled variant; do not change other
  callers' behavior.)
- Derive `line_number`/`column` from `span[0]` by `bisect` over
  `line_starts`. `\r\n` needs no special-casing — offsets are ground truth
  and `column` counts chars from the line start as before (a trailing `\r`
  inside the line is unchanged behavior for LF docs).
- Store the span on each violation dict internally (delete the
  reconstruction loop entirely).

**Verify**: full suite green; CRLF and case-fold rows green.

### Step 3: Linear containment

Replace the O(n²) filter with a sweep: sort indices by
`(start, -(end-start))`; iterate keeping a running "current covering span"
stack (or simply track max_end of any strictly-larger span seen at or before
this start). A violation is contained iff some OTHER span has
`other_start <= start`, `end <= other_end`, and strictly greater length —
reproduce EXACTLY these semantics including the strictness. Keep the
`freq_gated` exemption untouched (apply the filter, then re-admit freq_gated
categories exactly as now).

**Verify**: full suite green (many FP/REC rows exercise containment); perf
probe <1.5s @10k sentences; perf row green.

## Test plan

New rows: CRLF line-number pin, case-fold context pin, perf ceiling. Existing
suite (440 rows) is the regression net for containment semantics — run it
after each step, not just at the end.

## Done criteria

- [ ] Full suite exit 0, FAIL 0 (439+1 + new rows)
- [ ] Perf probe: <1.5s on the 10k-sentence doc (record before/after in commit message)
- [ ] `grep -n "splitlines()\[" scripts/banned_phrase_scan.py` → no matches
- [ ] `python3 evals/check_pattern_coverage.py` OK; `build_shared_benchmark.py --check` up to date
- [ ] `plans/README.md` updated

## STOP conditions

- `mask_ignored_spans` is not length-preserving.
- `_phrase_pattern` semantics can't take IGNORECASE without changing match
  behavior on any existing row (two failed attempts = stop, report which row).
- Containment-sweep semantics diverge on any existing row after one fix
  attempt — the old and new filters can be run side-by-side in a scratch
  script over the eval fixtures; report the first differing case.

## Maintenance notes

- Future pattern additions inherit correct offsets automatically; the perf
  row guards the aggregate.
- Reviewer: scrutinize the strictly-larger condition and the freq_gated
  re-admission — those two details carry all the containment behavior.
- Deferred: unifying this offset machinery with `suggest.py`'s span logic
  (it consumes scanner output; no change needed now).
