# Behavioral evals (skill-eval-harness)

Two complementary layers grade this skill:

| Layer | Graded by | What it answers |
|-------|-----------|-----------------|
| **Tooling** — `run_adversarial.py` | deterministic Python | Does the scanner flag X? Does validation fail on a dropped fact? |
| **Behavioral** — `shared-benchmark.json` | [skill-eval-harness](https://github.com/adewale/skill-eval-harness) + LLM judge | Does the *skill's prose* do the right thing, and does the skill **cause** the improvement? |

The tooling layer can't see prose quality; the behavioral layer can. Keep both.

## The manifest is generated, not hand-edited

`shared-benchmark.json` is built from the 26 `target: skill` cases in
`adversarial-evals.json` so the two layers never drift:

```bash
python3 evals/build_shared_benchmark.py          # regenerate after editing a case
python3 evals/build_shared_benchmark.py --check   # CI: fail if stale
```

Edit a behavioral case in `adversarial-evals.json` (or its split / script-assertion
mapping in `build_shared_benchmark.py`), then regenerate. CI enforces sync.

### What the generator adds

- **`variants: [with_skill, without_skill]`** — every case runs both ways so the
  harness reports **lift** (paired delta), not just an absolute pass rate. Lift is
  the signal the deterministic suite can't produce: it proves the skill caused the
  result instead of the base model happening to behave.
- **`split` (tune / holdout / holdback)** — guards against overfitting the skill to
  its own evals. Iterate on `tune`; report `holdout`; keep `holdback` sealed.
- **`script` assertions** — deterministic backstops that reuse our hardened tooling
  over each run's `output.md`:
  - fact cases (`SKILL-LEGAL-02`, `-APPROX-01`, `-DISAMBIG-01`) →
    `validate_preservation.py` against a fixture of the original prose.
  - anti-slop-register cases (`SKILL-FRAGMENT-01`, `-STACCATO-01`) →
    `banned_phrase_scan.py` must find zero violations.
- **`ablations`** — document which skill component each case cluster protects.

### The `output.md` contract

`script` assertions run with cwd set to `evals/` and read `{output_dir}/output.md`,
which the harness fills with the skill's output for that run. `banned_phrase_scan.py`
masks quoted/code spans, so a rewrite the runner wraps in quotes can hide a real
tell — treat the script result as a backstop and the `judge` result as primary.

## Running the behavioral layer (local, needs model credentials)

The harness drives the skill through a real runner and calls a model to judge, so
this is a local task, not a CI one.

```bash
# 1. Install (pin a tag), then record it in the manifest's harness.version field.
uv tool install git+https://github.com/adewale/skill-eval-harness.git

# 2. Lint the manifest (leakage + holdback + fixture checks).
skill-benchmark validate evals/shared-benchmark.json --strict-leakage

# 3. Prepare the tune split, run it through your local Claude Code runner,
#    then grade with an LLM judge and roll up the benchmark.
skill-benchmark prepare evals/shared-benchmark.json --split tune --out runs/tune
#    ...run the skill for each prepared task, writing each run's output.md...
skill-benchmark judge evals/shared-benchmark.json --runs runs/tune --judge-cmd 'claude -p'
skill-benchmark grade evals/shared-benchmark.json --runs runs/tune --allow-scripts
skill-benchmark benchmark evals/shared-benchmark.json --runs runs/tune
```

`--allow-scripts` is required for the `script` assertions to execute. Report the
`holdout` number for headline results; only break the `holdback` seal to confirm a
final figure, then reseal it.
