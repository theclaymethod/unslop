# Tune Results

First behavioral run, before `SKILL-WEDGE-01` was added:

- Harness: `skill-eval-harness` v0.4.2.
- Split: `tune` (`14` cases at the time, `with_skill` and `without_skill` variants).
- Runner: `python3 evals/run_local.py` using `claude -p`.
- Judge: `skill-benchmark judge --judge-cmd 'claude -p'`.

## Result

Judge assertions fully passed on `12 / 14` cases for both variants. Aggregate lift
is approximately zero because the base model already de-slops well. Use per-case
deltas as the signal.

Discriminating cases:

- `SKILL-LEGAL-02`: skill better. The skill preserved the legal hedge/reference
  better than the baseline.
- `SKILL-DONOHARM-01`: skill worse. The skill rewrote already-clean prose and
  invented a problem instead of returning it as-is.
- `SKILL-RUBRIC-01`: both weak. Both variants removed jargon but stayed generic.

Next skill work:

- Add a real already-clean exit before the rewrite path.
- Improve the warm/rubric path so it adds concrete voice without inventing facts.

## Limitations

- Some `with_skill` runs could not execute `python3 scripts/*.py`, so they measured
  the prose workflow without the helper scripts.
- `skill_invoked` assertions were removed because the headless runner emits no
  invocation telemetry.
- Harness v0.4.2 can emit null judge scores; coerce them before `benchmark` as
  shown in `evals/BEHAVIORAL-EVALS.md`.
