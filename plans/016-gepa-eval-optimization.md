# GEPA eval-loop optimization

## Goal

Use the existing adversarial and behavioral evals as immutable correctness
constraints while GEPA Optimize Anything searches for a smaller, faster check
loop. Luna implements bounded candidates; the root model owns the objective,
candidate selection, integration, and final acceptance.

## Baseline (2026-08-04)

| Measure | Baseline |
|---|---:|
| Deterministic adversarial wall time | 58.82 s |
| Script cases | 481 |
| Result | 479 pass, 1 XFAIL, 1 SPAN-03 timing failure |
| In-process / subprocess cases | 151 / 330 |
| Avoidable dispatch fallbacks | 250 |
| Declared gates | 26 |
| Gate command tokens | 98 |
| Tune model calls | about 104 |
| Tune generation calls | 36 (18 cases x 2 variants) |
| Tune judge calls | 68 (34 assertions x 2 variants) |

The repository has no separate EoVal-named runner. In this plan, EoVal means
the existing `evals/run_adversarial.py` suite plus the generated
`evals/shared-benchmark.json` behavioral layer.

## Hard constraints

1. Preserve every non-performance PASS/XFAIL/FAIL status. `FP-06` stays the
   only expected XFAIL. `SPAN-03` is the explicit red performance defect this
   optimization is allowed to turn green.
2. Keep every scanner-pattern coverage and false-positive protection claim.
3. Keep `shared-benchmark.json` derivable from `adversarial-evals.json` and pass
   strict leakage validation.
4. Do not use timing tolerance changes, removed cases, weaker assertions, or
   extra XFAIL rows as optimizations.
5. Do not label the candidate fully accepted until one uncached deterministic
   and live behavioral pass succeeds.

## GEPA artifact and score

GEPA optimizes a small text profile containing both deterministic phase IDs and
the behavioral cache policy, not the eval cases. The evaluator runs the phases
and returns diagnostic feedback with five scores:

- `correctness`: 1 only when every hard constraint passes;
- `runtime`: baseline wall time divided by candidate wall time;
- `model_calls`: baseline behavioral calls divided by the candidate's expected
  calls, using the call counts exercised by the fake-provider cache tests;
- `command_tokens`: baseline command argument count divided by the candidate;
- `simplicity`: baseline gate and command-token count divided by the candidate.

Any correctness failure forces the aggregate score to zero. The committed
artifact retains every raw evaluator timing; `--samples N` controls per-call
median sampling. Token savings may reuse cached immutable baseline work during
search, but final behavioral acceptance is uncached.

## Work slices

1. Repair the binary-stdin in-process seam and the current SPAN-03 hotspot.
2. Add one canonical repository checker and remove duplicate CI reruns.
3. Add content-hash caching for the unchanged `without_skill` behavioral arm
   and its judge results during optimization.
4. Run GEPA with a bounded candidate and metric-call budget. Record the Pareto
   frontier and select the smallest candidate that preserves correctness.
5. Run the uncached acceptance matrix and publish before/after measurements.

## Acceptance targets

- Deterministic suite: under 10 seconds on this machine, with an unchanged
  non-performance result vector and `SPAN-03` repaired from red to green.
- Codebase check interface: one canonical command, at most three blocking
  deterministic phases, and no full-suite subset reruns.
- Behavioral optimization iterations: at least 45% fewer model calls after the
  first cached baseline run.
- Instruction/check-profile text: no growth; prefer a measured reduction.

## GEPA run (2026-08-04)

The bounded search uses pinned `gepa==0.1.4`, a custom proposer queue, and a
checked-in evaluator. Reproduce it with:

```bash
UNSLOP_BASE_PATH="$PATH" uv run --with gepa==0.1.4 \
  python evals/optimize_check_profile.py \
  --output evals/gepa-check-profile.json --samples 1
```

The evaluator accepts only registered phase IDs, returns correctness, runtime,
model-call, command-token, and simplicity scores, and forces the score to zero
when any hard constraint is absent. Raw attempts, scores, budgets, commands, and
the selected candidate are committed in `evals/gepa-check-profile.json`.

| Profile | Correct | Time | Phases | Cache | Model calls | Command tokens |
|---|---:|---:|---:|---|---:|---:|
| Existing CI seed (median of recorded GEPA calls) | yes | 18.531 s | 18 | off | 104 | 62 |
| Three unique phases, sequential | yes | 7.174 s | 3 | read-write | 52 | 9 |
| Missing strict leakage | no (score 0) | not run | 2 | read-write | 52 | 6 |

GEPA selected the three-phase sequential profile plus the read-write cache
policy: full adversarial suite, shared-benchmark freshness, and strict leakage
validation. Optimization iterations apply that policy with
`UNSLOP_BEHAVIORAL_CACHE_MODE=read-write`; final acceptance uses `--uncached`.
Parallel execution was not retained because the two short checks add negligible
wall time and the sequential profile is simpler.

The selected profile reduced the four main control files (`AGENTS.md`,
`CLAUDE.md`, `evals/CHECKS.md`, and the CI workflow) from 16,702 to 7,401 bytes
and from 1,865 to 955 whitespace tokens (48.8% fewer).

## Accepted result (2026-08-04)

| Measure | Before | After | Change |
|---|---:|---:|---:|
| Deterministic adversarial wall time | 58.82 s | 7.15 s | 87.8% faster |
| Canonical deterministic check | 18.531 s GEPA seed | 7.174 s | 61.3% faster |
| Avoidable dispatch fallbacks | 250 | 0 | eliminated |
| External gate surface | 26 gates | 3 gates | 88.5% fewer |
| Blocking deterministic phases | 18 | 3 | 83.3% fewer |
| Gate command tokens | 62 | 9 | 85.5% fewer |
| Warmed behavioral model calls | about 104 | about 52 | 50% fewer |
| Control-file whitespace tokens | 1,865 | 955 | 48.8% fewer |

The runner currently preserves 488 PASS / 1 expected XFAIL with no failures.
`--jobs 1` and the bounded parallel default produce identical ordered results,
and two repeated default passes are identical. Parallel work is limited to
guaranteed subprocess cases; in-process scanners and the contribution check's
shared workspace stay sequential.

The behavioral cache is opt-in, content-addressed, and identity-bound. It only
reuses the immutable `without_skill` generation arm and successful parseable
judge responses. Deterministic fake-provider cases prove cache hits,
prompt/identity invalidation, failure rejection, and the uncached escape hatch.
The final uncached behavioral run used `gpt-5.6-luna` through Codex for both
generation and judging. All 36 generations and 68 judgments completed without
missing outputs or execution errors. With-skill passed 86.1% versus 80.6%
without-skill, a positive 5.6-point delta that was not significant at this
sample size (`p = 1.0`, `n = 18`). No failed provider output was cached or used
as acceptance evidence. Generation did not expose token telemetry; the 68 Luna
judge calls recorded 1,055,469 input and 7,378 output tokens (1,062,847 total).
The resource result therefore combines an exact judge-token subtotal with the
end-to-end model-call count rather than claiming a complete token total.

The control interface is smaller, but the whole diff is not: cache safety,
runner isolation, executable GEPA evidence, and their regressions add source
code. Against `origin/main`, the complete working change is approximately
2,013 lines, 6,350 whitespace words, and 68.0 KB larger. Report both
measurements during review rather than using the four-file control-text
reduction as a proxy for total codebase complexity.
