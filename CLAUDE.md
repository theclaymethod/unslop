# Claude Instructions

## Product rule

The adversarial eval suite defines the product. Start there. Before
implementation, encode behavioral changes in `evals/adversarial-evals.json`
and leave legacy `evals/evals.json` untouched because it serves old consumers,
not current product decisions.

## Add or change a pattern

1. Add the smallest red case before implementation.
2. A scanner pattern needs one false-negative row and one `protects`
   false-positive row.
3. A collocation-gated word also needs one REC row proving its jargon use still
   flags.
4. Prefer a minimal pair in `evals/fixtures/pairs/` for contextual or literal
   senses; run `python3 evals/check_pairs.py`.
5. Add a `skill` row only for rewrite, preserve, decline, or routing behavior.
   Update `evals/build_shared_benchmark.py` metadata and regenerate
   `evals/shared-benchmark.json`.
6. Do not weaken assertions, add XFAILs, or remove coverage to make a change
   pass. Literal uses in construction, mechanics, law, medicine, and code need
   protection.
7. A new `evals/check_*.py` must use the import seam in `evals/CHECKS.md`.

`check_pattern_coverage.py` requires every scanner pattern to have eval
coverage and every category to have a protecting FP row. Use
`python3 evals/kata_add_pattern.py --run` to rehearse the workflow.

## Check the repository

Run the single canonical command:

```bash
python3 evals/check.py
```

Install the harness if needed:

```bash
uv tool install git+https://github.com/adewale/skill-eval-harness.git
```

Use `run_adversarial.py --only PREFIX` or `--case ID` only to diagnose a
failure; the canonical command already exercises those checks.

If `SKILL.md`, `presets/`, or `references/` changed, also run:

```bash
python3 evals/check.py --behavioral tune
```

For co-writer, mimic, or detector-pack model changes, run the canned model
parity dry-run. Before merge, run the live GPT and Anthropic matrix described in
`references/pipeline.md`.

## Interpret results

- `tune` shapes the skill.
- `holdout` is for reporting.
- `holdback` stays sealed until final confirmation.
- Per-case deltas matter more than aggregate lift.
- Keep the single documented XFAIL only while it reflects the intentional
  scanner tradeoff.
