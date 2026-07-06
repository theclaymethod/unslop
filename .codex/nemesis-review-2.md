# Completion spec: eval-forms-integrate vs main (claim under test)

## Claim
Branch `eval-forms-integrate` (this worktree's HEAD) is objectively better than `main`
(commit 3053ea6) and safe to merge. It adds ten adversarially-verified work packages while
keeping every prior behavior green.

## Baseline vs branch
- main 3053ea6: 201 script cases (200 pass + FP-06 xfail), 33 behavioral, 12 gates.
- branch: 431 script cases (430 pass + FP-06 xfail), 33 behavioral (all deterministically
  backstopped), 23 gates via `python3 evals/run_adversarial.py --list-gates`, mirrored in
  evals/CHECKS.md (drift-pinned).
- Compare freely: `git worktree add <dir> 3053ea6` gives a runnable baseline.

## The ten packages (verification surface per package)
1. Minimal pairs + seeded docs (WP8): fixtures/pairs (16 pairs, target-isolated),
   fixtures/docs + manifests; gates check_pairs, check_seeded_docs. Known queue: word
   floors below spec (12/14), +2.4w with-twin length skew, set-based (not multiset)
   seeded bookkeeping — documented in the WP8 commit message as accepted follow-ups.
2. Meta-skill enforcement (WP9): check_pattern_coverage (75/75 patterns, 313/313 phrases,
   52/52 protects), kata_add_pattern (4 safety nets). Mutation: add a scanner pattern with
   no row -> DOC-09 fails.
3. Co-writer (WP11): scripts/suggest.py + check_suggestions.py contract gates; English-
   only decline in both scanners (LANG rows).
4. Model parity (WP12): evals/run_model_parity.py dry-run rows; measured tiering table in
   references/pipeline.md (2026-07-06 live runs).
5. Harvest (WP13): harvest_samples/harvest_classify; HARV-01 contamination gate (assistant
   text can never reach candidates — mutation-verified).
6. Silhouette (WP14): silhouette_scan 5 discourse metrics, human-reference drift gate,
   separation 12/12 ai + 0/8 human; docs-genre callback carve-out (SIL-9).
7. Contribute (WP16): contribute.py precheck/scaffold/verify/report, offline, specimen
   byte-fidelity, frozen-date fixtures, casefolded assertions, both-scanner precheck.
8. Voice scorer (WP10a): voice_profile/voice_score, GI impostor rank, 3x3 separation,
   gaming guard (VOICE-05). Known queue: same-genre impostor upgrades, background
   calibration, feature-space GI granularity — documented in its commit message.
9. Teach & mimic (WP10b): layered voice cards (no-fabrication rule), coverage classifier,
   run_mimic_refine with GI-hardened acceptance (MIMIC-10 pins the stuffed-candidate
   attack: honest 0.143 vs stuffed 0.733 under the new composite; the old raw distance
   would have accepted the attacker), LIVE path mock-tested (MIMIC-11), mimic_stats
   hand-verified BCa/permutation.
10. Calibrate (WP15): 5 deterministic dimension transforms (single-dimension discipline,
    token-boundary constraint guard), Wilson aggregation, voice-overrides-defaults
    annotations (a_flags/b_flags), CAL-01..11.
Plus: docs/PRODUCT.md (passes all three of the repo's own scanners), the
research-indicates vague_attribution family, integration fixes (directory fixtures in
coverage corpus, hedge_stack protects rename).

## Verification commands (all offline unless noted)
python3 evals/run_adversarial.py                       # 430 PASS / XFAIL {FP-06} / 0 FAIL
python3 evals/build_shared_benchmark.py --check
python3 evals/check_taboo_parity.py ; python3 evals/check_pattern_coverage.py
python3 evals/kata_add_pattern.py --run ; python3 evals/check_pairs.py
python3 evals/check_seeded_docs.py ; python3 evals/check_skill_examples.py
python3 evals/check_packs.py ; python3 evals/check_gates_doc.py
python3 evals/check_silhouette.py --reference ; python3 evals/check_silhouette.py --separation
python3 evals/check_voice.py --separation|--gi|--gaming|--profiles
python3 evals/run_adversarial.py --only CONTRIB|CAL|MIMIC|HARV|SUGG|PARITY  # slices
skill-benchmark validate evals/shared-benchmark.json --strict-leakage
Behavioral (needs claude -p): runs/{tune,holdout,holdback}/benchmark.json artifacts will
exist from the closeout run; inspect rather than rerun if present.

## Known tradeoffs / accepted state (do not report as new findings)
- FP-06 stays the single intentional xfail.
- WP8 and WP10a polish queues (above) are documented accepted follow-ups.
- Silhouette metrics are one-sided precision penalties (miss loose-form AI genres by
  design; surface layers cover those).
- Refine LIVE path is implemented but only mock-generator-tested; no real-generator run
  has occurred. mimic.md states this.
- contribute PR submission is documentation-only (gh flows never executed by code).
- The behavioral without_skill baseline is contaminated by the globally-installed skill
  (documented in run_local.py); per-case deltas over aggregate lift.

## Rules for the verifier
Read-only mindset: cp-backup/cmp-restore for any temporary mutation; never git checkout --
tracked files; no commits; leave the tree byte-identical. Judge "objectively better":
hunt regressions vs the 3053ea6 baseline on BOTH error directions with your own adversarial
inputs (literal/domain prose must stay clean; known tells must flag), mutation-test at
least three gates of your choosing, and verify three claims from the package list at
random by reproducing their evidence.
