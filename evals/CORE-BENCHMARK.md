# Core Product Benchmark

This benchmark answers one question:

> On unfamiliar AI-generated or mixed prose, does UNSLOP find the genuine
> writing problems, repair them, and leave facts and good prose intact?

It does not award product-quality credit for test count, routing, caching,
schema validation, voice imitation, or contributor tooling. Those remain
important engineering or feature checks, but they have separate scoreboards.

## Scoreboards

| Scoreboard | Evidence | Headline use |
|---|---|---|
| Core product | `core-benchmark.json`, raw run evidence, `core_metrics.py` | Whether UNSLOP works |
| Voice | teach/mimic fixtures and live mimic protocol | Whether UNSLOP sounds like a taught author |
| Engineering | canonical adversarial suite and harness checks | Whether the repository is safe to change |

The core scoreboard always reports these outcomes separately:

- **Detection precision:** legitimate findings / all findings.
- **Detection recall:** found gold issues / all gold issues.
- **Repair success:** gold issues actually improved / all gold issues.
- **Preservation:** required facts, qualifications, and relationships retained.
- **Damage rate:** already-good protected spans harmed / all protected spans.
- **Net improvement:** issue-bearing documents independently judged better than
  their source. Clean cases do not dilute this denominator.
- **Clean no-op rate:** clean documents returned byte-for-byte unchanged. This
  is the strongest check that an editor leaves already-good prose alone.

The report also shows the same metrics for Luna without UNSLOP and the
with-skill-minus-without-skill delta. A positive aggregate does not excuse a
damaging case; per-case failures remain visible.

## Case Contract

Public cases live in `evals/core-benchmark.json` and have one immutable source
document and a split:

- `tune` is visible during development.
- `holdout` is for reporting, not prompt adjustment.
- `holdback` is not committed with the public corpus. A separately generated
  local manifest lives under the ignored `evals/runs/` tree; the repository
  stores only its hash and counts. Running it requires
  `UNSLOP_CONFIRM_HOLDBACK=1`.

Gold annotations identify exact issue spans, protected good spans, and
preservation constraints. Generation receives the source, genre, and register,
but never the gold annotations. The independent adjudication step receives the
gold only after both rewrites exist.

Every selected case must produce both arms:

1. `with_skill`: Luna receives the pinned UNSLOP rewrite contract.
2. `without_skill`: the same Luna model receives a neutral diagnose-and-rewrite
   request without reading local or globally installed skill files.

The rewrite judge is the independent `gpt-5.6-sol` orchestrator model. It sees
randomized candidate labels and rewrites only—not either arm's findings or
treatment identity.

The runner records one canonical copy per case of the prompt hashes, raw
generation, raw adjudication, parsed findings, validation battery, and final
rewrites. Per-arm rows carry hashes instead of duplicating that evidence.
Missing, malformed, or timed-out runs fail the evaluation; they do not
disappear from denominators.

## Span Matching

Predicted findings use offsets into the original source. A finding matches one
gold issue at 0.5 or greater intersection-over-union. Category labels are
reported but do not control identity because two editors can legitimately name
the same problem differently. Matching is one-to-one. The runner requires an
exact source quote and normalizes a wrong offset only when that quote occurs
once. Duplicate, malformed, ambiguous, and shotgun findings count as failures.

## Acceptance

Do not set release thresholds from the tune split or from observed public
outputs. Freeze the public corpus, runner, scorer, scanner, shipping contract,
and release thresholds before the first public holdout run. Final evidence must
include:

- an uncached Luna run for both arms;
- every raw artifact and prompt/model hash;
- split- and case-level metrics;
- a paired comparison against Luna without UNSLOP;
- an independent adversarial review of annotations, runner behavior, and
  claimed conclusions.

Until those artifacts exist, scanner coverage and the legacy behavioral pass
rate are regression evidence, not proof that the product improves writing.

## Current public result

The frozen v9 public holdout failed the release gate. UNSLOP substantially
improved Luna's detection recall and repair rate, but it also introduced false
positives and one damaging edit, missed substantive semantic and safety issues,
and safely improved none of the three dirty documents end to end. The sealed
holdback remains unopened. See `CORE-RESULTS.md` for metrics and failure modes.
