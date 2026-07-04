# Behavioral Evals

The repo has two eval layers:

| Layer | Command | Measures |
|-------|---------|----------|
| Tooling | `python3 evals/run_adversarial.py` | Scanner and preservation scripts |
| Behavioral | `skill-benchmark ... evals/shared-benchmark.json` | Skill output quality and with-skill/without-skill lift |

`evals/shared-benchmark.json` is generated from the `target: skill` cases in
`evals/adversarial-evals.json`:

```bash
python3 evals/build_shared_benchmark.py
python3 evals/build_shared_benchmark.py --check
```

The generated manifest adds:

- `with_skill` and `without_skill` variants.
- `tune`, `holdout`, and `holdback` splits.
- LLM judge assertions for prose quality.
- Script backstops for fact preservation and anti-slop-register regressions.
- Ablations that name the skill component each case cluster protects.

Script assertions run from `evals/` and read each run's `{output_dir}/output.md`.
Use them as regression backstops; the judge assertions carry the behavioral signal.

## Add a Case

When you find a new AIism or failure mode, add it to `evals/adversarial-evals.json`
first.

Use the smallest useful pair:

- A `script` false-negative case when the scanner should catch the pattern.
- A `script` false-positive case when the same words have a legitimate literal or
  domain-specific use.
- A `skill` case when the product behavior matters: the skill should rewrite,
  preserve, decline, or route differently.

Then update the scanner/skill until the new case passes without breaking the old
suite:

```bash
python3 evals/run_adversarial.py
python3 evals/build_shared_benchmark.py
python3 evals/build_shared_benchmark.py --check
python3 evals/check_taboo_parity.py
skill-benchmark validate evals/shared-benchmark.json --strict-leakage
```

If you touched `SKILL.md`, `presets/`, or `references/`, run
`evals/run_behavioral.sh tune`. Keep new tuning cases in `tune`; reserve
`holdout` for reporting and `holdback` for final confirmation.

## Run Locally

The behavioral layer needs local model credentials for `claude -p`.

```bash
uv tool install git+https://github.com/adewale/skill-eval-harness.git

skill-benchmark validate evals/shared-benchmark.json --strict-leakage

evals/run_behavioral.sh tune
```

Notes:

- `prepare --out` takes a file path, not a directory.
- `benchmark --allow-scripts` is required for script assertions.
- Run the skill with permission to execute `python3 scripts/*.py`; otherwise the
  run measures the prose instructions without the skill's helper scripts.
- Use `tune` while changing the skill, report `holdout`, and keep `holdback` sealed
  until a final confirmation run.
- The base model already de-slops well, so per-case deltas matter more than the
  aggregate mean.
