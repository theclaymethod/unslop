# Plan 015: Spike — can per-author silhouette references be stable enough to ship?

> **Executor instructions**: This is a SPIKE — the deliverable is a
> measurement report and a go/no-go recommendation, not product code.
> Nothing lands in `scripts/` from this plan. Update `plans/README.md`
> when done.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- scripts/silhouette_scan.py scripts/voice_profile.py evals/fixtures/`
> Mismatched excerpts = STOP.

## Status

- **Priority**: P3
- **Effort**: M
- **Risk**: LOW (read-only spike; scratch outputs only)
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

`silhouette_scan.py`'s own docstring says its per-metric median/scale
machinery was deliberately shaped so "a future per-author profile with a
real, non-degenerate IQR widens the scale naturally," and names the
integration: mimic scoring against *this author's* macro habits instead of
the generic-human reference. The open question is empirical: per-author
silhouette metrics may be degenerate on realistic sample counts (the
committed human corpus already shows IQR 0.0 on some metrics). If a handful
of docs can't yield a stable scale, the feature needs a fallback design or
shouldn't ship. Measure before building.

## Current state

- `scripts/silhouette_scan.py:35-44` — the scale machinery and the
  "Voice fingerprint (not implemented here)" docstring; scale denominator is
  `max(sample_iqr, fence)` per metric.
- The five metrics: `scaffold_opener_share`, `callback_content`,
  `role_entropy_bits`, `preview_fulfillment`, `heading_preview` (see module
  docstring); computed per document by `scan()`.
- Committed reference: human stats JSON (find via
  `grep -rn "reference" scripts/silhouette_scan.py` for the path) built from
  the 8-doc human corpus in `evals/fixtures/silhouette/` (verify layout).
- Author-like corpora available for the spike WITHOUT private data: the
  three synthetic voice authors under `evals/fixtures/voice/` (multiple docs
  each) and the human/AI silhouette fixture docs.
- `scripts/voice_profile.py` — where a per-author fingerprint would live if
  the spike says go (a `silhouette` key in profile.json). NOT edited here.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Metric extraction | `python3 scripts/silhouette_scan.py <doc.md>` | JSON with per-metric values |
| Fixture inventory | `ls evals/fixtures/voice/ evals/fixtures/silhouette/` | corpora for the experiment |
| Suite | `python3 evals/run_adversarial.py` | green before and after (nothing changed) |

## Scope

**In scope**: a scratch analysis script under
`plans/scratch/015-silhouette-stability.py` (plans/ is the only writable
area; create the subdir), and the report
`plans/015-report-silhouette-stability.md`.

**Out of scope**: ANY edit under `scripts/`, `evals/` (fixtures included).
This spike reads the repo and writes only under `plans/`.

## Steps

### Step 1: Extraction harness

Write the scratch script: for each author corpus (3 synthetic authors + the
human fixture set as a 4th "author"), compute the five metrics per document
(import silhouette's functions via its dual-mode import), then per author:
median, IQR, and the count of metrics with IQR == 0 (degenerate).

**Verify**: script runs → a table (authors × metrics) of median/IQR printed.

### Step 2: Stability under subsampling

For each author with ≥6 docs: jackknife (leave-one-out) and 4-doc random
subsamples (seeded, 20 draws) → how much do median and IQR move? Report the
max relative swing per metric. Decision-relevant threshold (pre-registered
here): if median swings > 50% of the generic fence on ≥2 metrics at
realistic sample sizes (5-8 docs), per-author references are NOT stable
enough without a fallback.

**Verify**: report table includes swing stats + the threshold verdict per
author.

### Step 3: Discrimination check

Cross-score: does author A's held-out doc score closer to A's per-author
reference than to B's and to the generic reference? (Nearest-reference
accuracy over all held-out docs.) If per-author references don't beat the
generic reference at attributing held-out docs, the feature adds cost
without signal.

**Verify**: accuracy table in the report.

### Step 4: Report + recommendation

`plans/015-report-silhouette-stability.md`: setup, tables, the pre-registered
threshold verdicts, and ONE recommendation: (a) go — per-author reference
with `max(iqr, fence)` guard, sketch the profile-field design, propose the
eval-first follow-up plan; (b) conditional — go only with ≥N docs, fallback
to generic below; (c) no-go — evidence says the metrics don't stabilize;
name what data would change the answer.

**Verify**: scanners clean on the report
(`banned_phrase_scan.py` 0 hard, `structure_scan.py --genre docs` clean).

## Test plan

The pre-registered thresholds in steps 2-3 are the test — written before the
numbers exist, so the recommendation can't chase them.

## Done criteria

- [ ] Scratch script reproducible (seeded) under `plans/scratch/`
- [ ] Report with all three tables + one recommendation, scanner-clean
- [ ] `git status`: nothing modified outside `plans/`
- [ ] Suite green (untouched)
- [ ] `plans/README.md` updated

## STOP conditions

- Silhouette's functions can't be imported without side effects (network,
  state writes) — report; do not refactor them in this plan.
- The synthetic corpora have too few docs per author (<5) for step 2 —
  report the actual counts and shrink the design honestly rather than
  bootstrapping noise.

## Maintenance notes

- If "go": the follow-up plan touches `voice_profile.py`, `voice_score.py`,
  `silhouette_scan.py` in lockstep and MUST be eval-first (new VOICE rows).
- The synthetic authors may be unrealistically distinct; the report must
  carry this caveat — a "go" here is necessary, not sufficient, and the
  live-corpus check merges naturally with plan 012's protocol.
