# Core Product Results

## Release status: BETA; COMPARATIVE CLAIM NOT YET REVALIDATED

The current implementation is suitable for a beta release: its bounded
deterministic suite is green, its scanner contract is substantially smaller,
and earlier paired runs favor Luna+UNSLOP. It is not a validated general release.
Those later paired runs predate fixes to raw-span scoring and per-case efficiency
enforcement, while the newest independently annotated corpus missed its frozen
composition floor before either arm ran. The latest valid public product result
therefore remains the v9 no-ship below.

The failed V7 corpus was a benchmark-construction failure, not a product
failure. Its holdout contained five issue spans across two dirty documents and
four clean documents; the frozen floor was six issues across three dirty and
three clean documents. V7 was spent before a product call, and neither arm ran.
It provides no evidence that the current pipeline is better, worse, or equal to
raw Luna.

## Latest valid public result: NO-SHIP (v9)

The first frozen public v9 holdout does not establish that UNSLOP safely
improves unfamiliar AI-generated or mixed prose. It does show that the UNSLOP
contract helps Luna find and repair substantially more annotated issues than a
neutral editing prompt. That gain is not enough: the treatment also produced
more false positives, caused one real damaging edit, and left every dirty
document short of safe whole-document improvement.

The sealed holdback was not opened after this public failure.

## Frozen public result

Both generation arms used `gpt-5.6-luna`. The blinded adjudicator was
`gpt-5.6-sol`. The holdout contained three dirty documents and one clean
document, with 31 annotated issues and nine protected spans.

| Metric | Luna + UNSLOP | Plain Luna | Required |
|---|---:|---:|---:|
| Detection precision | 81.25% | 83.33% | at least 90% |
| Detection recall | 83.87% | 32.26% | at least 90% |
| Repair success | 87.10% | 58.06% | at least 90% |
| Preservation | 100% | 100% | 100% |
| Damage rate | 11.11% | 0% | 0% |
| Dirty documents safely improved | 0 of 3 | 0 of 3 | at least 80% |
| Clean documents left byte-exact | 1 of 1 | 1 of 1 | 100% |

UNSLOP won the paired comparison on all three dirty documents and tied the
clean document, but no dirty document cleared the absolute safety bar. Paired
wins therefore do not override the no-ship decision.

## What failed

The treatment made 26 true-positive findings, six false-positive findings, and
missed five gold issues. It repaired 27 of 31 annotated issues and preserved
all seven required factual or relational constraints. Its single protected-span
failure weakened a literal energy description from "harnessed energy" to
"received light."

The independent adversarial review found three recurring product failures:

- It treated accurate reports of another source's mistake or claim as errors
  in the current authorial voice.
- It treated literal technical language as AI-style metaphor and edited it
  unnecessarily.
- It missed consequential semantic problems, including unsupported decisions,
  unsafe recommendations, and an unsupported stability conclusion.

Two unsafe decisions remained in the conservation case. An unsafe repeat
recommendation remained in the rover case, alongside the damaging literal
energy edit. The ceramics case retained an unsupported stability conclusion.

## Evidence integrity

Thresholds were frozen before the v9 model run and were not changed afterward.
The manifest, shipping contract, runner, scorer, and scanner hashes are pinned
in `core-thresholds.json`. After model outputs existed, scorer input
normalization was corrected and an initially proposed policy-text heuristic was
rejected by independent review. The final scorer permits deterministic
protected-span overrides only when the manifest explicitly declares
`enforcement: exact_span`; v9 used no such override. The resulting v17 score is
reproducible but is not represented as a pristine pre-frozen trial.

Raw local evidence contains prompt hashes, model events, parsed responses, and
the independent judgments under `evals/runs/core/holdout-v17/`. That directory
is intentionally ignored because the prediction artifact is large and may
contain provider event envelopes. The stable public inputs and frozen hashes
are committed instead.

## Engineering performance

On the measured development machine, `python3 evals/check.py --full` completed
in about three seconds with no expected or unexpected failures. The deterministic
surface is explicitly capped at 80 executable examples and 400 expanded outcome
predicates; the current counts are printed by
`python3 evals/check_complexity_budget.py`. The scanner contract separately
reports 36/36 structural patterns, 16/16 literal triggers, and 20/20 protected
categories.

GEPA Optimize Anything selected one canonical full command instead of seven
redundant phases. The recorded profile reduced warmed behavioral model calls from
48 to 24 and command tokens from 19 to 3. These are evaluation-workflow
improvements, not evidence that the runtime product is faster than raw Luna.

## Next valid experiment

Do not tune directly against v9 and continue calling it a public holdout. Use
its failures as development evidence, improve the general attribution,
literal-language, and semantic-risk logic, and then evaluate once on a newly
authored, independently annotated public corpus. Open the sealed holdback only
after that new public corpus passes the frozen absolute gates.
