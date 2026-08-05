# Tune Results

## Corrected Luna hard-gate run — 2026-08-04

The previous behavioral wrapper could print success while live judge assertions
failed: harness v1 treated those assertions as soft, and the wrapper did not
independently enforce them. That result is superseded. Live judge assertions
are now gated, boolean and scored verdict schemas remain distinct, and the
wrapper rejects missing, duplicate, unexpected, or failed with-skill cases.

The corrected cached-development run used Luna for both generation and judging,
made 58 generation calls and 58 consolidated judge calls, and took 739 seconds
after the 10.8-second deterministic suite. Consolidating each case's rubric into
one verdict roughly halves the live judgments that the old per-rubric shape
would require. Token telemetry was unavailable, so no measured token total or
percentage reduction is claimed.

| variant | cases | combined pass rate | fully passing cases |
|---|---:|---:|---:|
| Luna + UNSLOP | 29 | 82.76% | 23 |
| Plain Luna | 29 | 79.89% | 22 |

The hard gate correctly returned non-zero. The with-skill failures were
`SKILL-CONTEXT-AUDIT-01`, `SKILL-LITERAL-02`, `SKILL-MACRO-01`,
`SKILL-RUBRIC-01`, `SKILL-SAFETY-SEMANTIC-02`, and `SKILL-TITLE-01`.
These are tuning failures, not a release result, and the sealed holdback remains
unopened.

## Luna tune run — 2026-08-04

This earlier run is retained as historical diagnostic evidence, not acceptance
evidence, because its live judge failures were not hard-gated. It used
`skill-eval-harness` v0.6.0 and
`gpt-5.6-luna` through Codex for both generation and judging. It made 36
generation calls and 68 judge calls; all 104 completed, with no missing outputs
or execution errors.

| variant | cases | objective / combined pass rate |
|---|---:|---:|
| with_skill | 18 | 0.8611 |
| without_skill | 18 | 0.8056 |

The skill gained 5.6 percentage points (normalized gain 0.286). The sampled
sign-flip test was not significant (`p = 1.0`, `n = 18`), so treat this as a
directional result rather than evidence of stable lift. `SKILL-DEHEDGE-01` was
the sole positive pair, there were no negative pairs, and both variants failed
`SKILL-LITERAL-01` and `SKILL-MACRO-01` while earning half credit on
`SKILL-WARMTH-01`.

Generation did not expose token telemetry. Luna judging did: the 68 uncached
judge calls used 1,055,469 input and 7,378 output tokens, or 1,062,847 total.
The run therefore has an exact judge-token total but no complete end-to-end
token count.

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

## Holdout run — 2026-07-06 (post-assembly, branch eval-forms-integrate)

12 holdout cases, judged with `claude -p`, exact bookkeeping (40 judge rows):

| variant | objective (deterministic backstops) | combined (judge + scripts) |
|---------|-------------------------------------|----------------------------|
| with_skill | 0.917 | 0.872 |
| without_skill | 0.875 | 0.879 |

Objective lift +4.2 points on held-out cases; judge-blended is flat. Consistent
with the standing interpretation: the deterministic layer (facts, register,
structure) carries the measurable value, the judge cannot distinguish the
prose, and the without-skill baseline is contaminated by the globally installed
skill (see run_local.py). Holdback remains sealed.
