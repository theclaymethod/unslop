# Completion spec: eval-hardening branch (claim under test)

## Claim

The `eval-hardening` branch (8 commits, `10aa31a..18a442a`, currently checked out in
/Users/clayton/dev/unslop) is an objectively better implementation of the unslop skill
and its eval suite than the baseline commit `10aa31a`, across: (1) eval-suite integrity,
(2) scanner precision AND recall, (3) fact preservation, (4) macro-structure coverage,
(5) behavioral-eval determinism, (6) docs/CI executability, (7) a cost-tiered execution
architecture. If the claim survives, the branch merges to main.

"Objectively better" here means: measurably better on both error directions (false
positives and false negatives), with no regression the baseline handled correctly, and
with the improvements enforced by the suite itself rather than by convention.

## Baseline vs branch

- Baseline: git commit `10aa31a` (main). 55 deterministic script cases (54 pass,
  1 xfail FP-06), 27 behavioral cases with 5 script backstops, 4 documented checks.
- Branch: `18a442a`. 174 script cases (173 pass, 1 xfail FP-06 — intentional,
  documented in evals/CRITIQUE.md), 33 behavioral cases all carrying deterministic
  backstops, 12 gates in `python3 evals/run_adversarial.py --list-gates`.
- Compare freely: `git worktree add <dir> 10aa31a` gives a runnable baseline.

## Changed surface (commit order)

1. `efd7e0e` runner: `violation_phrase_contains`/`violation_category_equals` assertion
   types; EXPECTED_XFAIL pinned to {FP-06}; XPASS or unexpected-XFAIL exits non-zero;
   argparse `--only/--case/--list-gates`; recall rows REC-04..07, QE-04, SEM-02, AS-04.
2. `4b1c64f` scanner: collocation gates for unpack/lean into/double down/showcase/
   bolster/garner/stakeholder; word-boundary phrase matching; new detection families
   (wh-opener self-Q&A, negative listing, isn't-just variants, noting-phrase pairs,
   cliffhanger fragments, modal+potentially stacks, whether-you're openers, emoji
   headers, more); em-dash/exclamation no longer match across paragraph breaks;
   `evals/check_taboo_parity.py` + DOC-01 enforce scanner↔catalog parity.
3. `8799035` support scripts: unit-family swap detection (km/mi, °C/°F, GB/TB, hr)
   with alias sets both directions; spelled magnitudes beyond currency; curly-quote
   constraint tracking; faithful rewrites (range/quarter/time rewordings, reorders,
   and/or, quote restyling) no longer fail; `validate_preservation.py --strict`
   promotes negation/scope/modality warnings to exit 1; staccato detection through
   em-dash/semicolon joins; splitter handles closing quotes; diff_check reorder
   exemption.
4. `a25515c` behavioral determinism: DETERMINISTIC_ASSERTIONS for every behavioral
   case in `evals/build_shared_benchmark.py`; run_local.py `<final>` extraction
   (output.md = rewrite, answer_full.md = full answer); fixture-prompt sync guard for
   all fixture types; 3 new holdout cases (FRAGMENT-02, DONOHARM-02, INJECT-02);
   binary judge rubrics.
5. `92c0ab6` docs/CI: `evals/run_behavioral.sh` (holdback sealed behind
   UNSLOP_CONFIRM_HOLDBACK=1); CI runs all deterministic gates; `evals/CHECKS.md`
   gate matrix pinned byte-equal to `--list-gates` by DOC-03/check_gates_doc.py;
   SKILL.md examples pinned by DOC-02/check_skill_examples.py (the baseline's crisp
   example violated the skill's own blocking gates).
6. `6161e92` macro layer: `scripts/structure_scan.py` (burstiness, conclusion coda,
   bold-colon listicles, one-line staccato, connective paragraph openers, signposting,
   opener repetition, participial closers; `--genre docs|social` carve-outs;
   markdown-aware). Rows STRUCT-01..16 + ROB-12..14. SKILL-MACRO-01/02 use essays
   that are phrase-scan-clean but structure-flagged. A 20-doc probe corpus lives at
   /private/tmp/claude-501/-Users-clayton-dev-unslop/830a19b6-9d14-4fc1-9d39-e37f50f5a402/scratchpad/macro-probe/
   (ai/ and human/): expected classification 10/12 ai docs flag, 8/8 human docs clean.
7. `18a442a` consolidation + tiers: SKILL.md 295→180 lines; `references/pipeline.md`
   (Tier 0 scripts → Tier 1 pack-scoped small detectors → Tier 2 single rewriter →
   Tier 0 gates); `references/packs/` (5 packs + manifest covering all 46 scanner
   categories); `references/maintenance.md`; `scripts/check_packs.py` + DOC-04/05/06;
   SKILL-TIER-01 scope-discipline case.

## Expected behaviors (verification surfaces)

All from repo root unless stated. Deterministic gates (no credentials needed):

```
python3 evals/run_adversarial.py            # exit 0; 173 PASS, XFAIL exactly {FP-06}
python3 evals/build_shared_benchmark.py --check
python3 evals/check_taboo_parity.py
python3 evals/check_gates_doc.py
python3 evals/check_skill_examples.py
python3 evals/check_packs.py
skill-benchmark validate evals/shared-benchmark.json --strict-leakage
```

Behavior deltas the branch claims (baseline worktree should show the opposite):

- Scanner clean on: "The plant is in Garner, North Carolina."; "Notwithstanding
  anything to the contrary in Section 4, the tenant remains liable."; "Drive the
  wedge into the kerf."; "We unpacked the boxes after the move."; escrow
  "stakeholder"; "painted the landscape of the Hudson Valley."
- Scanner flags: "Why does this matter? Because costs compound."; "This isn't just a
  bugfix, it's a rethink."; "The result? A 40% drop."; "Whether you're a seasoned
  developer or just starting out…"; "It is worth noting…"; "could potentially".
- validate_preservation fails on: 150 km→150 miles; 5 million→5 billion users;
  curly-quote content edits. Passes on: 10-20%→"between 10% and 20%";
  Q3 2024→"the third quarter of 2024"; 3:00 PM→"3 pm"; GB/hr expansions.
- Suite integrity: deleting the leverage+navigate scanner patterns must fail the
  branch suite (baseline suite stays green under the same deletion); marking a
  passing case xfail:true must exit non-zero on the branch.
- structure_scan: flags the SKILL-MACRO essay texts (which produce 0 phrase-scan
  violations); `--genre docs` suppresses bold-colon flags; human corpus docs clean.

Higher-cost real surfaces (available, optional):

- Behavioral layer: `evals/run_behavioral.sh tune` (needs `claude -p` and
  `skill-benchmark`, installed at ~/.local/bin). Artifacts of a passing tune run
  exist in runs/tune/.
- OSS model spot-check artifacts (24 model-case outputs + graded matrix):
  /private/tmp/claude-501/-Users-clayton-dev-unslop/830a19b6-9d14-4fc1-9d39-e37f50f5a402/scratchpad/oss-runs/
  Re-runnable via the script in the same scratchpad dir; OpenRouter key available in
  macOS keychain service `OPENROUTER_API_KEY`.

## Known tradeoffs / accepted decisions

- FP-06 stays an intentional xfail (literal "delve into a place" vs figurative —
  pattern kept for recall; documented in CRITIQUE.md).
- Comma-joined staccato fragments are deliberately NOT flagged by
  readability_metrics (splitting on commas would false-flag ordinary prose);
  em-dash/semicolon joins are flagged.
- diff_check still reports raw change_percentage on reorders; only the
  excessive_change flag is exempted.
- rubric.md / personality-guide.md / edit-library.md were deliberately not
  pointer-ized during consolidation; presets/ verified as non-duplicative deltas.
- SKILL-MODE-01's deterministic proxy accepts an ask-first branch via the token
  "audit" in answer_full.md.
- Suite runtime grew (~55→174 subprocess cases, tens of seconds); accepted.
- The tiered pipeline (references/pipeline.md, packs) is documentation + integrity
  gates; no orchestration code executes it in this repo. Its behavioral claim is
  pinned only by SKILL-TIER-01.

## Setup notes

- Python 3.14 via Homebrew as `python3`; no third-party deps for the deterministic
  gates. `skill-benchmark` and `codex` on PATH at ~/.local/bin.
- The repo working tree is clean at `18a442a` on branch `eval-hardening`.
- Do not commit anything; do not push; leave the tree byte-identical. Back up any
  file you temporarily mutate with cp and restore with cmp verification. Never use
  `git checkout --` to restore.
