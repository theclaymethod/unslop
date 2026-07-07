# Agent Instructions

## Product Rule

The eval suite defines the product. When adding or changing an AI-writing pattern,
start with evals, then update the skill or scripts until the suite passes.

## Add a New Pattern

1. Edit `evals/adversarial-evals.json` first.
2. Add the smallest useful coverage:
   - New scanner pattern: exactly one `script` false-negative row and one `script`
     false-positive domain-protection row.
   - Existing word gated behind collocations: add the FN/FP pair plus one REC row
     proving the jargon use still flags.
   - Agent behavior change: add a `skill` row only when the behavior is rewrite,
     preserve, decline, or route.
   - Context-heavy or literal-sense pattern: prefer an `evals/fixtures/pairs/`
     minimal pair plus PAIR rows, then run `python3 evals/check_pairs.py`.
3. If a `skill` row is added, update `evals/build_shared_benchmark.py` with its split
   and domain, then regenerate `evals/shared-benchmark.json`.
4. Update `scripts/banned_phrase_scan.py`, `SKILL.md`, `presets/`, or `references/`
   only after the eval captures the desired product behavior.
5. `python3 evals/check_pattern_coverage.py` (gate DOC-09) fails unless every
   scanner pattern is exercised by a row and every category has a `protects` FP
   row; `python3 evals/kata_add_pattern.py --run` (DOC-10) rehearses this. No
   grandfathering.
6. Adding a new `evals/check_*.py` script? Follow the import seam documented in
   `evals/CHECKS.md`'s "Writing a New Check" section.

Prefer contextual patterns over broad word bans. A row for `wedge` or `load-bearing`
should also protect literal uses such as construction, mechanics, law, medicine, code,
or other domain-specific prose.

## Required Checks

Use `python3 evals/run_adversarial.py --list-gates` to inspect the live gate
matrix. If `skill-benchmark` is missing, install it with
`uv tool install git+https://github.com/adewale/skill-eval-harness.git`.

Run these before handing work back:

```bash
python3 evals/run_adversarial.py
python3 evals/build_shared_benchmark.py
python3 evals/build_shared_benchmark.py --check
python3 evals/check_taboo_parity.py
skill-benchmark validate evals/shared-benchmark.json --strict-leakage
```

If you touched `SKILL.md`, `presets/`, or `references/`, also run
`evals/run_behavioral.sh tune`.

If you touched the co-writer, mimic, or detector-pack model features, run `python3 evals/run_model_parity.py --dry-run --responses evals/fixtures/parity/canned_responses.json` and, before merge, the live matrix across the GPT and Anthropic spectrums (see `references/pipeline.md`, Model Parity).

`evals/evals.json` is the legacy happy-path suite; never edit it. Use
`evals/adversarial-evals.json` as the source of truth.

## Interpreting Results

- `tune` cases are for shaping the skill.
- `holdout` cases are for reporting.
- `holdback` cases stay sealed until final confirmation.
- The base model already removes many AIisms, so per-case deltas matter more than
  aggregate lift.
- Keep the single documented XFAIL only if it still reflects an intentional regex
  scanner tradeoff.
