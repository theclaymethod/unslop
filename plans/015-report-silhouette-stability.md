# Report 015: Can per-author silhouette references be stable enough to ship?

Spike for plan 015, measurement only, nothing under `scripts/` or `evals/`
changed. The harness lives at `plans/scratch/015-silhouette-stability.py`
and reads fixtures already committed under `evals/fixtures/voice/authors/`
and `evals/fixtures/silhouette/`.

Drift check ran clean: `git diff --stat 217c218..HEAD -- scripts/silhouette_scan.py
scripts/voice_profile.py evals/fixtures/` produced no output.

## Setup

Four "author" corpora, all pre-existing fixtures:

| author | docs | source |
| --- | --- | --- |
| amara | 5 | `evals/fixtures/voice/authors/amara/*.md` |
| boris | 5 | `evals/fixtures/voice/authors/boris/*.md` |
| celia | 5 | `evals/fixtures/voice/authors/celia/*.md` |
| human_fixtures | 8 | `evals/fixtures/silhouette/corpus/human/*.txt` (the committed generic-reference build corpus, used here as a 4th pseudo-author) |

amara, boris, celia have 5 docs each -- below the plan's "≥6 docs" line for
the full jackknife-plus-subsample design. Per the plan's shrink-honestly
instruction: none of the four corpora have fewer than 5 docs, so the STOP
condition ("all authors <5 docs") does not apply, but the design is
shrunk for the three 5-doc authors -- see Table 2.

The harness imports `scripts/silhouette_scan.py`'s `compute_metrics` and
`paragraphs` directly (the same `sys.path.insert(scripts_dir)` the scanner
itself uses) and computes the five silhouette metrics
(`scaffold_opener_share`, `role_entropy_bits`, `heading_preview`,
`preview_fulfillment`, `callback_content`) per document. Per-author
median/IQR use the identical method `evals/check_silhouette.py` uses to
build the committed generic reference: `statistics.quantiles(n=4,
method="inclusive")`, IQR floored at 0.05, fence and weight constants
copied read-only from that file (not re-derived):

| metric | fence | weight |
| --- | --- | --- |
| scaffold_opener_share | 0.20 | 2.0 |
| role_entropy_bits | 0.80 | 1.0 |
| heading_preview | 0.20 | 1.0 |
| preview_fulfillment | 0.25 | 1.0 |
| callback_content | 0.30 | 1.5 |

The harness is deterministic (fixed seed, printed table matches byte-for-byte
across two runs).

## Table 1: Extraction -- per-author median / IQR / degenerate count

"Degenerate" = raw sample IQR is exactly 0.0 (before the 0.05 floor), same
definition the scanner's own docstring uses for the generic human corpus.

| author | scaffold_opener_share | role_entropy_bits | heading_preview | preview_fulfillment | callback_content | degenerate / 5 |
| --- | --- | --- | --- | --- | --- | --- |
| amara | med 0.000, IQR 0.000 (deg) | med -0.000, IQR 0.000 (deg) | n=0, no data | med 0.167, IQR 0.033 | med 0.222, IQR 0.250 | 2 |
| boris | med 0.000, IQR 0.000 (deg) | med -0.000, IQR 0.000 (deg) | n=0, no data | med 0.000, IQR 0.000 (deg) | med 0.200, IQR 0.200 | 3 |
| celia | med 0.000, IQR 0.167 | med -0.000, IQR 0.592 | n=0, no data | med 0.200, IQR 0.250 | med 0.286, IQR 0.333 | 0 |
| human_fixtures | med 0.000, IQR 0.000 (deg) | med -0.000, IQR 0.000 (deg) | n=1, IQR 0.000 (deg) | med 0.000, IQR 0.000 (deg) | med 0.000, IQR 0.062 | 4 |

`heading_preview` never computes for any author corpus: it needs 3+ `##`
headings and none of the voice-author or human-fixture prose docs use
headings (the metric requires `len(heads) >= 3`, see
`scripts/silhouette_scan.py:205`). That is a corpus-coverage gap, not a
stability finding -- a per-author reference would ship with this metric
permanently absent for prose-only authors.

Three of four authors are degenerate (raw IQR 0.0) on 2-4 of the 5
metrics, matching the scanner docstring's claim that these metrics are
"degenerate at zero across the human corpus." Only celia -- whose synthetic
voice happens to use formal connective diction ("Although," "Consequently,"
"nevertheless") that collides with the `ROLE_CUES` regexes -- has real,
non-degenerate variance on every scored metric. That is coincidental
register overlap with the AI-tell vocabulary, not a designed voice
difference; the corpus was built for `voice_profile`-style diction/rhythm
evals, not for silhouette-specific scaffold habits.

## Table 2: Stability -- jackknife + 4-doc subsample swings vs. fence

Pre-registered threshold: an author's per-author reference is **NOT
STABLE** if the max relative swing of the metric's median exceeds 50% of
that metric's generic fence (table above) on 2 or more metrics.

amara, boris, celia (5 docs each): 4-doc random subsampling is
**skipped as redundant**, not run. At n=5, a 4-doc subsample is the
complement of exactly one left-out document -- structurally identical to a
jackknife fold. Running 20 seeded draws would only re-poll the same 5
possible 4-doc sets with replacement and add no new information beyond
jackknife LOO. This is the "shrink the design honestly" case the plan
calls for.

human_fixtures (8 docs): both jackknife (8 folds of 7) and genuine 4-doc
subsampling (20 seeded draws of 4-of-8) ran.

| author | metric | jackknife median swing | % of fence | subsample median swing | % of fence | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| amara | scaffold_opener_share | 0.000 | 0% | n/a (skipped) | -- | ok |
| amara | role_entropy_bits | 0.000 | 0% | n/a | -- | ok |
| amara | heading_preview | 0.000 | 0% | n/a | -- | ok |
| amara | preview_fulfillment | 0.016 | 7% | n/a | -- | ok |
| amara | callback_content | 0.076 | 25% | n/a | -- | ok |
| boris | scaffold_opener_share | 0.000 | 0% | n/a | -- | ok |
| boris | role_entropy_bits | 0.000 | 0% | n/a | -- | ok |
| boris | heading_preview | 0.000 | 0% | n/a | -- | ok |
| boris | preview_fulfillment | 0.000 | 0% | n/a | -- | ok |
| boris | callback_content | 0.100 | 33% | n/a | -- | ok |
| celia | scaffold_opener_share | 0.084 | 42% | n/a | -- | ok |
| celia | role_entropy_bits | 0.296 | 37% | n/a | -- | ok |
| celia | heading_preview | 0.000 | 0% | n/a | -- | ok |
| celia | preview_fulfillment | 0.100 | 40% | n/a | -- | ok |
| celia | callback_content | 0.107 | 36% | n/a | -- | ok |
| human_fixtures | scaffold_opener_share | 0.000 | 0% | 0.000 | 0% | ok |
| human_fixtures | role_entropy_bits | 0.000 | 0% | 0.000 | 0% | ok |
| human_fixtures | heading_preview | 0.000 | 0% | 0.000 | 0% | ok |
| human_fixtures | preview_fulfillment | 0.000 | 0% | 0.000 | 0% | ok |
| human_fixtures | callback_content | 0.000 | 0% | 0.125 | 42% | ok |

**Formal verdict for all four authors: stable** -- none crosses 2 metrics
over the 50%-of-fence line.

That verdict needs a caveat: it is trivially easy to pass when a metric's
IQR is pinned at 0.0 (three of amara's five metrics, three of boris's, four
of human_fixtures's) -- a constant value cannot swing. The only author
scored across all five metrics with real variance, celia, sits at 36-42% of
fence on four separate metrics: close enough to the 50% line that a single
different left-out document plausibly flips the verdict. Direct evidence
of that fragility is already in the run: celia's `doc4.md` alone drives
nearly all of celia's jackknife swing (dropping it changes celia's own
distance-to-self from 0.86 to a value close enough to a rival author's 0.84
that celia's own doc4 is misclassified in Table 3 below). A "stable" verdict
built mostly out of zero-swing degenerate metrics is not the same finding as
a reference that is stable *and* informative.

## Table 3: Discrimination -- nearest-reference accuracy

For every held-out document: build that document's own author's reference
with the document excluded (leave-one-out), keep the other three authors'
full-corpus references plus the committed generic reference
(`evals/fixtures/silhouette/human_reference.json`) as the four rival
candidates, score distance as `sum(|value - ref_median| / max(ref_iqr,
fence))` over metrics valid in both (the same `denom = max(iqr, fence)`
scaling `scan()` itself uses), and check whether the nearest of the five
candidates is the document's own author.

| author | correct / n | accuracy |
| --- | --- | --- |
| amara | 0 / 5 | 0% |
| boris | 3 / 5 | 60% |
| celia | 0 / 5 | 0% |
| human_fixtures | 6 / 8 | 75% (leakage caveat below) |
| **overall** | **9 / 23** | **39.1%** |

Two caveats that both cut the overall number down further:

- **human_fixtures is not an independent test.** It is one of the exact
  eight source documents `evals/check_silhouette.py` uses to build the
  committed generic reference (see `human_reference.json`'s `sources`
  list). Every human_fixtures document's distance-to-generic is
  artificially near zero because that document (or a near-identical sibling
  doc, since the reference is a median/IQR pooled over 15 sources) helped
  build the thing it is being compared against. Dropping human_fixtures as
  leaked leaves three genuinely independent synthetic authors at
  **3 / 15 = 20% accuracy** -- at or below chance for a 5-candidate nearest
  match (~20% chance floor).
- **Ties are common and are resolved by iteration order, not signal.**
  boris's three "correct" hits (doc1, doc2, doc4) share the *exact* distance
  vector `amara=0.18, boris=0.08, celia=0.27, generic=0.17,
  human_fixtures=0.17` -- because boris is degenerate (raw IQR 0.0) on 3 of
  5 metrics, most held-out boris docs collapse to the same near-zero
  distance vector regardless of actual content. The "win" is boris's
  reference happening to sit closest to a mostly-zero vector, not the
  scanner recognizing boris's voice. This is visible directly in Table 1:
  boris is the second-most-degenerate author (3/5) after human_fixtures
  (4/5).

Net reading: outside of leakage and degenerate-tie artifacts, the harness
found **no working discrimination signal**. amara and celia -- the two
non-leaked authors with any real distinguishing metric variance -- never
matched their own document to their own reference, even once.

## Recommendation: no-go (for now)

The stability test (Table 2) passes only because most metrics are pinned at
zero for most authors -- a verdict that can't fail is not evidence of a
working reference. The decisive test is discrimination (Table 3), and it is
the one the per-author reference exists to serve: does a held-out document
score closer to its own author than to an impostor or the generic
reference? At n=5-8 docs/author, on corpora not purpose-built for this
scanner's five metrics, the answer is no for 2 of 3 independent authors, and
the third's apparent win is a degenerate tie rather than real
discrimination.

**What data would change this answer:**

1. A per-author corpus **curated for scaffold/callback habits specifically**
   -- documents chosen (or written) to vary along paragraph-opener cue use,
   preview/fulfill structure, and closing callbacks, the way `celia`'s
   corpus incidentally does through formal connective diction. The three
   existing voice-author corpora were built for `voice_profile`-style
   diction and rhythm evals, not for these five macro-structure metrics, so
   this spike may be **understating** what a purpose-built corpus would show
   -- the plan's requested caveat that synthetic authors could be
   unrealistically distinct did not hold here; if anything the opposite
   risk showed up, that they are too similar to the generic-human zero
   point on these particular metrics to differ from it or each other.
2. A materially larger per-author N. 5-8 docs cannot even populate
   `heading_preview` (needs 3+ real headings, never present) and produces
   raw IQR 0.0 on most metrics for most authors -- there is no sample size
   in this spike's data at which per-author variance reliably exceeds
   author-to-author variance, because most authors don't vary at all on
   most metrics at this N. The next spike should hold corpus-construction
   method fixed and sweep N (e.g., 5/10/20/40 docs of one real, consistently
   voiced author) to find where (if anywhere) discrimination accuracy rises
   above the ~20% chance floor.
3. An independent generic-reference holdout. This run's human_fixtures row
   is not trustworthy evidence either way because it is not disjoint from
   the generic reference; a real test needs a human corpus that never
   touched `human_reference.json`'s build.

Until one of those exists, building the per-author profile field into
`scripts/voice_profile.py` would ship a feature whose central claim --
"this reads like you, not like a stranger" -- is not supported by the only
data available to test it.

## Maintenance note

A "go" here is necessary, not sufficient -- the live-corpus check merges
with plan 012's protocol before any per-author reference ships against real
user data.
