# Agent Instructions

## Product rule

The adversarial contracts define the product. Put scanner examples in
`evals/fixtures/contracts/scanner-examples.json` and behavioral or routing
changes in `evals/adversarial-evals.json`. Leave legacy `evals/evals.json`
untouched because it serves old consumers, not current product decisions.

## Add or change a pattern

1. Add the smallest red scanner example before implementation.
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

Run the fast canonical core-contract gate (five deterministic examples):

```bash
python3 evals/check.py
```

It exercises only bounded offline plumbing: five high-signal examples covering
the manifest, Luna runner interface, scoring, evidence, and acceptance. It does
not call Luna and is engineering evidence, not proof that the product improves
writing.
Run the bounded deterministic maintenance lane before a release and whenever
scanner patterns, preservation, runner integrity, or benchmark plumbing change:

```bash
python3 evals/check.py --maintenance
```

Run the product, maintenance, and behavioral integrity lanes together with:

```bash
python3 evals/check.py --full
```

The deterministic surface may not exceed 80 executable examples or 400
expanded outcome predicates, and nested aggregate wrappers are forbidden. The
budget counts contract-table assertions directly and recursively expands each
Python fixture's final pass/fail logic; do not describe wrapper rows as atomic.
The full command keeps
strict XFAIL enforcement and presents evidence under `core-outcome`,
`deterministic-safety`, and `integrity-and-tools`. The fast core-contract lane
is the normal edit loop. Mimic, voice, climb, and contribution checks are separate
engineering-health scoreboards; run their `check_*.py --all` command when that
tool changes, but do not count them as proof of core detection or repair.

Install the harness if needed:

```bash
uv tool install git+https://github.com/adewale/skill-eval-harness.git
```

Use `run_adversarial.py --only PREFIX` or `--case ID` only to diagnose a
failure.

If `SKILL.md`, `presets/`, or `references/` changed, also run:

```bash
python3 evals/check.py --behavioral tune
```

For co-writer, mimic, or detector-pack model changes, run the canned model
parity dry-run. Before merge, run the documented live Luna generation and
independent Sol judge matrix in `references/pipeline.md`.

## Interpret results

- `tune` shapes the skill.
- `holdout` is for reporting.
- `holdback` stays sealed until final confirmation.
- Per-case deltas matter more than aggregate lift.
- Keep the single documented XFAIL only while it reflects the intentional
  scanner tradeoff.
