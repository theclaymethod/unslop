# Plan 012: Design and run the first live mimic-fidelity evaluation (spike)

> **Executor instructions**: This is a SPIKE plan — the deliverable is a
> design doc + one executed measurement run + recorded numbers, not product
> code. Follow steps; verify each; STOP conditions binding. Update
> `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 217c218..HEAD -- evals/run_mimic_refine.py evals/mimic_stats.py references/mimic.md scripts/voice_score.py`
> Mismatched excerpts = STOP.

## Status

- **Priority**: P2 (highest-value direction item)
- **Effort**: M–L (requires live model calls — needs operator-provided
  credentials/CLI and budget approval before step 3)
- **Risk**: LOW to the repo (additive artifacts); MED to the claim (the
  result may be unflattering — that's the point)
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `217c218`, 2026-07-06

## Why this matters

"Write the way a specific human writes" is the product's generative half and
its single biggest unproven claim. Everything about mimic today is validated
by internal machinery: the refine loop runs on canned candidates (dry-run)
or a mock generator; the voice composite is self-consistent but has a
documented ~93-94% verification ceiling; baselines (zero/few/retrieval
few-shot) are defined in `references/mimic.md` but no live run has ever
measured mimic output against a real author's held-out writing. One honest
measurement converts the claim from architecture to evidence — or produces
the failure analysis that redirects the roadmap.

## Current state

- `evals/run_mimic_refine.py` — the loop harness; LIVE mode via
  `--generate-cmd` (executed as an argv list via `shlex.split`, no shell);
  A/DEV split machinery, gates, GI-composite acceptance already built.
- `evals/mimic_stats.py` — paired stats: BCa bootstrap CI + sign-flip
  permutation test. Built, eval-pinned, unused on live data.
- `scripts/voice_score.py` — the deterministic referee (char-3gram, delta,
  EMD, punctuation, contractions, MTLD, General Impostors rank).
- `references/mimic.md` — documents sample requirements (≥5 docs, 2–3k
  words, same genre), the baselines, and the honest-reporting rule
  ("under-claim: the composite is directional cross-genre").
- Voice fixtures are synthetic (three invented authors under
  `evals/fixtures/voice/`); no real-author held-out corpus exists in-repo.
- The teach flow produces `.unslop/voice/<name>/{profile.json,card.md,card/}`
  — gitignored; a real profile exists only on the operator's machine.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Refine loop (live) | `python3 evals/run_mimic_refine.py --help` | shows `--generate-cmd` and split flags — read all flags first |
| Stats | `python3 evals/mimic_stats.py --help` | paired-stats CLI shape |
| Voice score | `python3 scripts/voice_score.py --profile <p> --impostors evals/fixtures/voice/impostors --seed 7 <file>` | composite JSON |
| Suite | `python3 evals/run_adversarial.py` | stays green throughout (this spike must not touch pinned behavior) |

## Scope

**In scope**: a new design doc `evals/LIVE-MIMIC-PROTOCOL.md`; a runnable
experiment script or documented command sequence; one recorded run's numbers
appended to `evals/TUNE-RESULTS.md`; optional new fixtures under
`evals/fixtures/live-mimic/` (prompts, NOT author text — see privacy note).

**Out of scope**: changes to `voice_score.py`, `run_mimic_refine.py`, or any
scanner (if the harness lacks a needed flag, STOP and report the gap —
harness changes are a separate eval-first plan); committing any real author's
text (privacy: the corpus stays operator-local, like `.unslop/`).

## Steps

### Step 1: Write the protocol (no model calls)

Author `evals/LIVE-MIMIC-PROTOCOL.md` — the acceptance bar BEFORE any
generation, so results can't quietly move the goalposts:

1. **Corpus spec**: one real author (the operator volunteers theirs), ≥8
   same-genre docs; split: N_teach for the profile/card, N_held (≥3 docs,
   never seen by teach) for measurement. Document word counts.
2. **Conditions**: (a) mimic single-pass with card; (b) mimic + refine loop;
   (c) retrieval few-shot baseline (same samples in-context, no card/loop) —
   the honest competitor per references/mimic.md; (d) zero-shot base model.
3. **Tasks**: ≥6 prompts matched to the author's genre (commit these).
4. **Metrics**: voice composite + GI rank vs the held-out docs (score
   generated text against the profile, and against held-out-derived profile
   variants for a consistency check); ALL removal gates must pass or the
   sample is a failure regardless of score (the mode's own constitution).
5. **Stats**: paired per-prompt deltas, mimic-vs-retrieval, via
   `mimic_stats.py`; report CI, not just means.
6. **Pre-registered outcomes**: what number pattern = "mimic earns its
   complexity", "parity — card only is enough", "refine adds nothing", each
   with the roadmap consequence. Write these BEFORE step 3.

**Verify**: doc passes `python3 scripts/banned_phrase_scan.py` (0 hard) and
`structure_scan.py --genre docs` (clean).

### Step 2: Dry-run the pipeline end-to-end with the mock

Wire the full protocol using the existing mock generator
(`evals/fixtures/mimic/mock_generator.py`) as the "model" to prove the
plumbing (splits → generate → gate → score → stats) runs unattended and
emits the report shape the protocol defines.

**Verify**: one command (or documented sequence) produces a stats table from
mock data; suite still green.

### Step 3: OPERATOR GATE — live run

STOP and request from the operator: (a) confirmation of budget/model for
`--generate-cmd` (e.g. `claude -p` or an OpenRouter model), (b) the local
path to their taught profile + held-out docs. Do not proceed without both.
Then execute the protocol once, all four conditions, and append the numbers
+ run date + model ids to `evals/TUNE-RESULTS.md` following its existing
"Holdout run — 2026-07-06" section format.

**Verify**: TUNE-RESULTS entry exists with per-condition composites, paired
deltas + CI, gate-failure counts; scanners clean on the edited doc.

## Test plan

The protocol doc's pre-registered outcomes section is the test: the run
either meets a named outcome or the mismatch is itself the recorded finding.

## Done criteria

- [ ] `evals/LIVE-MIMIC-PROTOCOL.md` committed, scanner-clean
- [ ] Mock dry-run reproducible via documented commands
- [ ] One live run recorded in `evals/TUNE-RESULTS.md` (numbers, model, date)
- [ ] No author text committed (`git status` + review)
- [ ] Suite green throughout
- [ ] `plans/README.md` updated

## STOP conditions

- Step 3's operator gate — mandatory stop for approval + local paths.
- The refine harness lacks a flag the protocol needs (e.g. per-prompt
  output capture) — report the specific gap; harness changes are their own
  eval-first plan.
- The composite's cross-genre caveat applies (author corpus ≠ task genre) —
  flag it in the protocol rather than proceeding to a muddy measurement.

## Maintenance notes

- Re-run the protocol when the card format, scorer weights, or refine
  acceptance logic changes materially — it's the product claim's regression
  test, at live-run cost, so reserve for material changes.
- The pre-registered-outcomes discipline is the part reviewers should defend
  hardest against future edits.
