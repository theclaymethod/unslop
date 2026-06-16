# Claude Instructions

## Product Rule

The eval suite defines the product. When adding or changing an AI-writing pattern,
start with evals, then update the skill or scripts until the suite passes.

## Add a New Pattern

1. Edit `evals/adversarial-evals.json` first.
2. Add the smallest useful coverage:
   - `script` false-negative row when the scanner should catch the pattern.
   - `script` false-positive row when the same words have a legitimate literal or
     domain-specific use.
   - `skill` row when the behavior is agent-level: rewrite, preserve, decline, or route.
3. If a `skill` row is added, update `evals/build_shared_benchmark.py` with its split
   and domain, then regenerate `evals/shared-benchmark.json`.
4. Update `scripts/banned_phrase_scan.py`, `SKILL.md`, `presets/`, or `references/`
   only after the eval captures the desired product behavior.

Prefer contextual patterns over broad word bans. A row for `wedge` or `load-bearing`
should also protect literal uses such as construction, mechanics, law, medicine, code,
or other domain-specific prose.

## Required Checks

Run these before handing work back:

```bash
python3 evals/run_adversarial.py
python3 evals/build_shared_benchmark.py
python3 evals/build_shared_benchmark.py --check
skill-benchmark validate evals/shared-benchmark.json --strict-leakage
```

When behavior depends on the full skill output, also run the relevant behavioral
split from `evals/BEHAVIORAL-EVALS.md`.

## Interpreting Results

- `tune` cases are for shaping the skill.
- `holdout` cases are for reporting.
- `holdback` cases stay sealed until final confirmation.
- The base model already removes many AIisms, so per-case deltas matter more than
  aggregate lift.
- Keep the single documented XFAIL only if it still reflects an intentional regex
  scanner tradeoff.
