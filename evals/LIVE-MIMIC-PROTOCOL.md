# Live Mimic Fidelity Protocol

Mimic's central claim, "write the way a specific human writes," has never
been tested against a real author's held-out writing. Every existing signal
is internal: dry-run refine on canned candidates, a mock generator for the
LIVE path, and a self-consistent composite with a documented ~93-94% ceiling.
This document is the acceptance bar for the first live measurement, written
before any generation happens. Numbers do not get to redefine what counts as
a win after the fact; the outcomes in section 6 are fixed now.

Everything below is designed against `evals/run_mimic_refine.py`,
`evals/mimic_stats.py`, `scripts/voice_score.py`, and `scripts/voice_profile.py`
as they exist today (read via `--help` and source before writing this). Section
7 lists the places those tools fall short of what the protocol needs; those are
findings for a later plan, not blockers for this one.

## 1. Corpus spec

One real author. At least 8 documents in one genre (essays, technical posts,
newsletter issues: pick one and do not mix). Split the documents into two
groups before anything else runs:

- **N_teach**: the documents `voice_profile.py` and `voice_card.py` (and, in
  turn, `run_mimic_refine.py --samples`) are allowed to read. `run_mimic_refine.py`
  further splits N_teach internally into its own A/DEV halves for card-building
  and acceptance scoring. That internal DEV half is still visible to the loop
  during the run and is not a blind holdout.
- **N_held**: at least 3 documents the teach step never sees. Keep them in a
  directory that is never passed to `voice_profile.py`, `voice_card.py`, or
  `run_mimic_refine.py --samples`. N_held exists purely to build the scoring
  profile in section 4. It is the only genuinely unseen material in the whole
  protocol.

Record, before generation: document count in each group, word count per
document, total corpus word count, and the genre label used for
`--genre {prose,docs,social}`. If total N_teach word count lands under 2,000
words, `voice_profile.py` will mark `low_confidence`. Note that flag rather
than suppressing it, and treat every downstream score as provisional if it
fires.

## 2. Conditions

Four conditions run against the same tasks and the same author:

| Condition | What it feeds the generator | How it runs |
|-----------|------------------------------|-------------|
| (a) mimic, single pass | voice card only, no raw samples | `run_mimic_refine.py --baseline zero --iterations 1 --beam 1` |
| (b) mimic + refine | voice card + k-nearest A samples, looped | `run_mimic_refine.py --baseline retrieval` (default iterations/beam/patience) |
| (c) retrieval few-shot | same k-nearest samples in context, **no card** | generated outside the harness (section 7, gap 1) |
| (d) zero-shot | a bare "write like this person" instruction, no card, no samples | generated outside the harness (section 7, gap 1) |

(c) and (d) are the honest competitors `references/mimic.md` names: static
retrieval and a naive instruction, neither carrying the measured-marker card
mimic depends on. Refine only earns its cost if it beats (c). Mimic only
earns the card if (a) beats (d).

## 3. Tasks

Six genre-matched prompts, committed as task instructions only, under
`evals/fixtures/live-mimic/prompts/01-explaining-technical.md` through
`06-numbers-data.md`. They cover six of the ten card-taxonomy situations from
`references/mimic.md` (explaining-technical, anecdote, argument, disagreement,
hedging-uncertainty, numbers-data), so a fidelity gap that only shows up in one
kind of writing does not hide behind an aggregate. Each prompt asks for
200-300 words on a topic drawn from the operator's own experience, not the
author's, so each task tests whether the *voice* transfers to genuinely new
content rather than how well the model can paraphrase a sample.

No author text lives in this repository. The prompts are instructions to a
model, never excerpts of what the author wrote.

## 4. Metrics

Build one scoring profile from N_held with `voice_profile.py N_held/ -o
heldout-profile.json`. Score every condition's output against that single
profile with `voice_score.py --profile heldout-profile.json --impostors
evals/fixtures/voice/impostors --seed <fixed> <candidate>`: same profile,
same impostor pool, same seed, for all four conditions and all six tasks. Do
not read a condition's score from `run_mimic_refine.py`'s own `report.json`
and compare it against an externally computed `voice_score.py` number.
Section 7, gap 2, explains why that mixes two code paths that are not
guaranteed to agree on identical input.

Two numbers per candidate: the full composite (`0.5·(1-GI) + 0.5·zsum`) and
the GI rank on its own, since GI is the harder-to-game half of the two.

Every candidate must clear the same hard-gate battery
`references/commands/mimic.md` lists for a single-pass mimic: banned-phrase,
structure, readability, `validate_preservation.py` against the task prompt's
intent, and `diff_check.py`, before its score counts for anything. A
candidate that scores well but trips a gate is a failure for that task,
recorded as such, not excluded from the average.

## 5. Statistics

Pair condition (b) against condition (c) per task: six paired composites,
mimic-plus-refine against the honest retrieval baseline, both scored through
the identical path from section 4. Feed the pairs to `mimic_stats.py --seed
<fixed>` and report the BCa CI and the sign-flip p-value, not just the mean
delta. A win requires CI lower bound > 0 and p < 0.05, per the tool's own
under-claim discipline; six paired items is small enough that the permutation
test runs exact.

Report (a) vs (d) the same way as a secondary pair: does the card alone beat
a bare instruction. A mimic that only wins once refine is layered on top is a
different product claim than one where the card already carries the result.

## 6. Pre-registered outcomes

Named before any live number exists. Once real numbers land, this section is
frozen. It cannot be edited to fit what came back.

1. **Mimic earns its complexity.** (b) beats (c) with CI lower bound > 0 and
   p < 0.05, and every accepted candidate clears every hard gate.
   Consequence: keep investing in the refine loop; it is pulling its weight
   over the honest baseline.
2. **Parity, card only.** (a) beats (d) with CI lower bound > 0 and p < 0.05,
   but (b) vs (c) does not clear the same bar (`mimic_stats.py` returns
   `improved: false`). Consequence: the card is where the value is. Stop
   promoting refine as a default path and keep it opt-in for the cases where a
   single pass measurably falls short.
3. **Refine adds nothing.** (b) vs (c) returns `improved: false` or a negative
   mean delta. Consequence: retire the refine loop's default position in the
   mimic flow, or gate it behind an explicit "still short after one pass" ask.
   Redirect the engineering budget to card and teach quality instead of
   iteration.
4. **Gate failure invalidates the run.** Any condition fails hard gates on
   more than one of the six tasks. Consequence: the scoring numbers from that
   run are not reportable at all. Fix the gate failure (or the card/prompt
   that caused it) and rerun before drawing any fidelity conclusion, no matter
   what the composite says.

## 7. Harness gaps

Findings from wiring this protocol against the current tools. None of these
block the mock dry run in section 8; they matter for interpreting a live run
and are reported here rather than patched, per this plan's scope.

1. **No card-free path through the live generator.** `build_prompt()` in
   `run_mimic_refine.py` always prepends `"# Voice card\n" + card_text`; the
   `--baseline` flag only changes which raw samples ride alongside it. There
   is no way to drive conditions (c) and (d), both explicitly card-free,
   through `run_mimic_refine.py`'s own `--generate-cmd` path. Both have to be
   generated outside the harness and scored afterward with `voice_score.py`,
   which works fine (the scorer does not care how a candidate was produced)
   but means the protocol's four conditions do not all flow through one
   command.
2. **Cross-path scoring noise.** `distances()`'s `delta` feature calls
   `z_function_vector()`, which breaks ties among function words with equal
   background mean by dict iteration order. `run_mimic_refine.py`'s in-memory
   profile (`profile_from_paths`, insertion-ordered) and a `voice_profile.py`
   CLI profile round-tripped through JSON (`sort_keys=True`) order those ties
   differently, so scoring the *same* candidate against a profile built from
   the *same* documents through the two paths does not land on the same
   composite. Measured in the mock run below: 1.1839053124386925 both ways for
   one candidate, but 0.20603887153430928 (external, consistent path) versus
   0.187950946479 (internal `report.json`) for another, a ~0.02 gap on a
   composite where the pre-registered win threshold is CI lower bound > 0.
   Section 4's "score everything through one path" rule exists because of
   this; do not relax it for a live run.
3. **`run_mimic_refine.py`'s hard gates are a subset of the documented
   single-pass battery.** `run_gates()` enforces exactly five checks:
   `length_floor`, `preservation` (via `validate_preservation.py`),
   `banned_phrase`, `structure`, `copy_gate`. `references/commands/mimic.md`'s
   single-pass flow lists two more, `readability_metrics.py` and
   `diff_check.py`, that the refine loop never runs. Running them by hand
   against the mock run's own accepted winner in section 8 produced a
   `diff_check.py` "excessive change" flag (104.4% word change against a 40%
   threshold) on every candidate tested, including the one the loop accepted.
   Before trusting a live run's gate-pass rate, decide whether `diff_check.py`
   is even a sound gate for output that is supposed to be reworded into a new
   voice. As written, it looks likely to fire on legitimate mimics, not just
   bad ones.
4. **No dedicated held-out-corpus flag.** `run_mimic_refine.py --samples`
   demands at least 5 documents and refuses below that; there is no separate
   flag for a document set the loop should never touch. N_held (section 1) has
   to be enforced by directory hygiene, keeping it out of every directory this
   protocol's commands point at, rather than by the tool itself.

## 8. Appendix: mock dry run

Proves the pipeline runs unattended end to end, splits through generate
through gate through score through stats, and emits the report shape this
protocol depends on, using `evals/fixtures/mimic/mock_generator.py` as the
model and `evals/fixtures/voice/authors/amara` (5 committed synthetic
documents) as the stand-in author. This is a plumbing check, not a fidelity
measurement: the mock generator selects its canned output by iteration
index, not by prompt content, so none of the numbers below carry a real
voice signal, and the 5-document fixture author sits below this protocol's
own 8-document / N_held ≥ 3 corpus bar (gap 4 explains why the fixtures
cannot satisfy it without pulling in a second author's text as a false
stand-in for N_held).

Commands, run from the repo root:

```bash
WORK=$(mktemp -d)

# Condition (b): mimic + refine, LIVE path via the mock generator.
python3 evals/run_mimic_refine.py \
  --samples evals/fixtures/voice/authors/amara \
  --draft evals/fixtures/mimic/draft.md \
  --out "$WORK/refine" --seed 1 --iterations 3 --beam 2 --patience 2 \
  --baseline retrieval --name amara \
  --generate-cmd "python3 evals/fixtures/mimic/mock_generator.py"

# Condition (a): mimic single pass, card only, one generation.
python3 evals/run_mimic_refine.py \
  --samples evals/fixtures/voice/authors/amara \
  --draft evals/fixtures/mimic/draft.md \
  --out "$WORK/single_pass" --seed 1 --iterations 1 --beam 1 \
  --baseline zero --name amara \
  --generate-cmd "python3 evals/fixtures/mimic/mock_generator.py"

# Held-out profile, standing in for N_held (the real corpus spec doesn't fit
# these fixtures; see above). Reuses the internal DEV split's two documents
# (doc3.md, doc4.md; read from refine/report.json's "split.DEV") since the
# 5-doc fixture author has no documents left over for a genuinely separate
# N_held set.
mkdir -p "$WORK/heldout"
cp evals/fixtures/voice/authors/amara/doc3.md evals/fixtures/voice/authors/amara/doc4.md "$WORK/heldout/"
python3 scripts/voice_profile.py "$WORK/heldout" -o "$WORK/heldout_profile.json"

# Conditions (c) and (d): generated outside the harness (gap 1), same mock model.
mkdir -p "$WORK/retrieval_iter0" "$WORK/retrieval_iter1" "$WORK/retrieval_iter2" "$WORK/zero_shot"
MOCK_ITER=0 python3 evals/fixtures/mimic/mock_generator.py < /dev/null > "$WORK/retrieval_iter0/candidate.md"
MOCK_ITER=1 python3 evals/fixtures/mimic/mock_generator.py < /dev/null > "$WORK/retrieval_iter1/candidate.md"
MOCK_ITER=2 python3 evals/fixtures/mimic/mock_generator.py < /dev/null > "$WORK/retrieval_iter2/candidate.md"
MOCK_ITER=1 python3 evals/fixtures/mimic/mock_generator.py < /dev/null > "$WORK/zero_shot/candidate.md"

# Score every condition through the identical path (gap 2) against the one held-out profile.
python3 scripts/voice_score.py --profile "$WORK/heldout_profile.json" \
  --impostors evals/fixtures/voice/impostors --seed 1 "$WORK/refine/final.md"
python3 scripts/voice_score.py --profile "$WORK/heldout_profile.json" \
  --impostors evals/fixtures/voice/impostors --seed 1 "$WORK/single_pass/final.md"
python3 scripts/voice_score.py --profile "$WORK/heldout_profile.json" \
  --impostors evals/fixtures/voice/impostors --seed 1 "$WORK/retrieval_iter0/candidate.md"
python3 scripts/voice_score.py --profile "$WORK/heldout_profile.json" \
  --impostors evals/fixtures/voice/impostors --seed 1 "$WORK/zero_shot/candidate.md"

# Gate battery from references/commands/mimic.md against the refine winner (gap 3).
python3 scripts/banned_phrase_scan.py "$WORK/refine/final.md"
python3 scripts/structure_scan.py --genre prose "$WORK/refine/final.md"
python3 scripts/readability_metrics.py "$WORK/refine/final.md"
python3 scripts/validate_preservation.py evals/fixtures/mimic/draft.md "$WORK/refine/final.md"
python3 scripts/diff_check.py evals/fixtures/mimic/draft.md "$WORK/refine/final.md"

# Paired stats, mimic-vs-retrieval shape (section 5).
python3 evals/mimic_stats.py "$WORK/pairs.json" --seed 7
```

Captured output (composites via `--seed 1`, matching the refine run's own
seed):

| condition | candidate | composite | GI |
|-----------|-----------|-----------|-----|
| (a) single pass | `single_pass/final.md` | 1.1839053124386925 | 0.0 |
| (b) refine | `refine/final.md` | 0.20603887153430928 | 0.234375 |
| (c) retrieval, iter0 | `retrieval_iter0/candidate.md` | 1.1839053124386925 | 0.0 |
| (c) retrieval, iter1 | `retrieval_iter1/candidate.md` | 0.7467587287728741 | 0.0 |
| (c) retrieval, iter2 | `retrieval_iter2/candidate.md` | 0.20603887153430928 | 0.234375 |
| (d) zero-shot | `zero_shot/candidate.md` | 0.7467587287728741 | 0.0 |

`refine/report.json` reports `best_candidate: cand01.md`, `best_score:
0.187950946479`, `stop_reason: max_iterations`, `split.DEV: [doc3.md,
doc4.md]`: the shape section 4 and 5 depend on. `single_pass/report.json`
shows the same shape with a single iteration.

`mimic_stats.py` on the (b)-vs-(c) pairs, built from the three composites
above (`pairs.json`: `{"treatment": 1.1839053124386925, "baseline":
1.1839053124386925}`, `{"treatment": 0.7467587287728741, "baseline":
0.7467587287728741}`, `{"treatment": 0.20603887153430928, "baseline":
0.20603887153430928}`):

```json
{"ci_high": 0.0, "ci_low": 0.0, "improved": false, "mean_delta": 0.0, "n": 3, "p_value": 1.0, "seed": 7}
```

The pairs come out identical because the mock generator keys its output only
to iteration index, so condition (b)'s iteration-*i* survivor and condition
(c)'s `MOCK_ITER=i` call return the same canned text. The mock has no way to
make the two conditions diverge. `mimic_stats.py` correctly reports
`improved: false` on zero-variance input rather than manufacturing a win.
That reflects the tool's own under-claim discipline holding on degenerate input.
For contrast, the tool's non-degenerate shape (real variance, a real CI, a
real p-value) is already demonstrated on the committed
`evals/fixtures/mimic/stats/win.json` fixture:

```json
{"ci_high": 0.15874999999999997, "ci_low": 0.13999999999999999, "improved": true, "mean_delta": 0.15, "n": 8, "p_value": 0.0078125, "seed": 7}
```

Gate results on the refine winner: `banned_phrase_scan.py`,
`structure_scan.py --genre prose`, `readability_metrics.py`, and
`validate_preservation.py` all exit 0. `diff_check.py` exits 1 with
`"Excessive change (104.4% > 40% threshold)"`, the flag gap 3 above covers.

Swap three things to go live: point `--generate-cmd` at `"claude -p"` (plus a
comparable call for conditions (c)/(d)), point `--samples` at the operator's
own N_teach folder instead of the amara fixture, and build the scoring
profile from a properly separated N_held folder instead of the two-document
DEV stand-in above.
