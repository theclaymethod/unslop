# Behavioral Evals

The repo separates product measurement from regression checks:

| Layer | Command | Measures |
|-------|---------|----------|
| Tooling | `python3 evals/run_adversarial.py` | Scanner and preservation scripts |
| Behavioral | `skill-benchmark ... evals/shared-benchmark.json` | Skill routing, preservation, and rewrite regressions |
| Core product | `python3 evals/core_runner.py ...` | Paired detection and repair, independent adjudication, and clean no-op behavior |

Use [the core protocol](CORE-BENCHMARK.md#cross-family-development) for model
comparisons, including open models through Cloudflare AI Gateway. The legacy
behavioral lane below uses the same model for generation and judging. Its pass
rate does not establish independent writing-quality improvement.

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

The tune cases cover phrase-level filler, paraphrased sentence and paragraph
scaffolding, macro cleanup, clean no-ops, literal language, attribution,
relational contradictions, safety limits, inert input, and audit-only routing.
`SKILL-PARAPHRASE-01` deliberately has zero scanner hits: it removes an empty
opening, identity claim, and closing question while preserving an informative
question and answer. A larger phrase catalog would not exercise that distinction.
These are authored regression cases, not a representative corpus or human
calibration of the judge. Prompt-substring checks do not substitute for them.

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
python3 evals/build_shared_benchmark.py
python3 evals/check.py
```

If you touched `SKILL.md`, `presets/`, or `references/`, run
`python3 evals/check.py --behavioral tune`. Keep new tuning cases in `tune`; reserve
`holdout` for reporting and `holdback` for final confirmation.

## Run Locally

The behavioral layer uses the local Codex runtime with `gpt-5.6-luna` for both
generation and judging. It does not call Claude.

```bash
uv tool install git+https://github.com/adewale/skill-eval-harness.git@7760b945d1d8fd26152b8190f802e14bed393ca9

skill-benchmark validate evals/shared-benchmark.json --strict-leakage

evals/run_behavioral.sh tune
```

During repeated optimization, cache only content-addressed successful results:

```bash
UNSLOP_BEHAVIORAL_CACHE_MODE=read-write \
UNSLOP_BEHAVIORAL_CACHE_IDENTITY='provider/model/version' \
evals/run_behavioral.sh tune
```

The unchanged `without_skill` generation and judge prompts are reused; changed
candidate outputs miss automatically. Final acceptance must bypass every cache:

```bash
evals/run_behavioral.sh tune --uncached
```

The provider and model are pinned inside `run_behavioral.sh`, so environment
variables cannot silently change an acceptance run. Direct experiments can use
`run_local.py --model MODEL`, but they are not the canonical behavioral gate.

Notes:

- `prepare --out` takes a file path, not a directory.
- `benchmark --allow-scripts` is required for script assertions.
- Run the skill with permission to execute `python3 scripts/*.py`; otherwise the
  run measures the prose instructions without the skill's helper scripts.
- Use `tune` while changing the skill, report `holdout`, and keep `holdback` sealed
  until a final confirmation run.
- Inspect per-case deltas; an aggregate gain does not excuse a damaged document.
