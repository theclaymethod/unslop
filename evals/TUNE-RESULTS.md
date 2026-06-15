# Tune-split results — first behavioral harness run

First end-to-end run of the behavioral layer (`skill-eval-harness` v0.4.2) on the
14-case `tune` split, both variants (`with_skill` / `without_skill`), one run each.
Generation via `claude -p` (`evals/run_local.py`); judging via
`skill-benchmark judge --judge-cmd 'claude -p'`. Outputs and transcripts are under
`runs/tune/` (gitignored).

## Headline

| Variant | Judge cases fully passing | Mean combined pass rate |
|---------|---------------------------|--------------------------|
| with_skill | 12 / 14 | 0.86\* |
| without_skill | 12 / 14 | 0.94 |

\* with_skill's combined rate is dragged by the now-removed `skill_invoked`
assertions (see "Harness limitations"). On the **judge assertions alone**, the two
variants tie at 12/14 — the skill wins one case and loses one.

**Aggregate lift on tune ≈ 0.** Not because the skill is inert, but because the
base model already de-slops well (the `without_skill` outputs name AI tells,
binary-contrast templates, etc. unprompted). The value of this run is per-case
discrimination, not the headline average.

## What discriminated

- **SKILL-LEGAL-02 — skill better (1.0 vs 0.5).** The bare model stripped the hedge
  `arguably` from the legal sentence (and argued it was a "stacked hedge"); the
  skill kept both `arguably` and `Section 12(b)`. This is exactly the
  fact/negation-preservation the skill exists to protect.
- **SKILL-DONOHARM-01 — skill worse (0.0 vs 1.0).** The real finding. Given
  already-clean prose, the bare model said "leave it." The skill *fabricated* a
  problem ("too-perfect symmetry", "voiceless") and rewrote it, injecting a wry
  aside that wasn't in the original. This reproduces the documented do-no-harm gap:
  the skill has no firm exit for clean text and over-edits when invoked.
- **SKILL-RUBRIC-01 — both fail (0.5 each).** Both strip the jargon; neither adds
  genuine voice, staying "clean but generic." The rubric-gaming concern is real and
  catches the skill *and* the baseline.

The other 11 tune cases are saturated — both variants pass. The harness's own lint
auto-flagged `FRAGMENT-01`, `LEGAL-02`, `STACCATO-01` as
`saturated/non-discriminating` on their **objective** (script) assertion: the
deterministic backstops pass for both variants, so they confirm correctness but
don't measure lift. That matches the design — the script assertions are a
regression guard; the judge assertions carry the behavioral signal.

## Actionable for the skill

1. **Do-no-harm exit (highest priority).** `SKILL-DONOHARM-01` failed by
   over-editing. The skill needs a real "already clean → return as-is and say so"
   branch that triggers before the rewrite path, not just a warning in the prose.
2. **Voice injection for the warm/rubric path.** `SKILL-RUBRIC-01` shows that
   stripping jargon without adding specificity scores as bland. The warm preset
   should push for a concrete detail, not just removal.

## Harness limitations found (so the next run is clean)

- **`skill_invoked` is unmeasurable here.** The headless `claude -p` runner emits
  no invocation telemetry, so those assertions always fail and produced spurious
  "with-skill failure" flags on `DONOHARM-01` and `MODE-01`. Removed from the
  manifest; `MODE-01`'s judge assertions actually passed.
- **The skill's scripts can't run in the runner.** Three `with_skill` runs
  (`FRAGMENT-01`, `LEGAL-02`, `NOINVENT-01`) reported "the Bash scan is blocked by
  permissions" and fell back to manual diagnosis. A faithful benchmark must run the
  skill with permission to execute `python3 scripts/*.py` (e.g. an allow-list for
  `Bash(python3 *)`), or the skill is evaluated without its own tooling.
- **`benchmark` crashes on a null judge score.** When the judge omits a numeric
  `score` (it's optional), the merge does `score >= threshold` with `score=None`
  and raises `TypeError`. Worked around by coercing null scores to the `passed`
  boolean (`runs/tune/judge.fixed.jsonl`). Worth an upstream issue.

## Reproduce

```bash
skill-benchmark prepare evals/shared-benchmark.json --split tune --out runs/tune/tasks.jsonl
python3 evals/run_local.py runs/tune/tasks.jsonl --jobs 5
skill-benchmark judge evals/shared-benchmark.json --runs runs/tune --split tune \
  --judge-cmd 'claude -p' --out runs/tune/judge.jsonl
# coerce optional null scores (harness bug workaround)
python3 - <<'PY'
import json
rows=[json.loads(l) for l in open('runs/tune/judge.jsonl') if l.strip()]
for r in rows:
    if r.get('score') is None: r['score']=1.0 if r.get('passed') else 0.0
    r.setdefault('threshold',1)
open('runs/tune/judge.fixed.jsonl','w').write('\n'.join(json.dumps(r) for r in rows)+'\n')
PY
skill-benchmark benchmark evals/shared-benchmark.json --runs runs/tune --split tune \
  --allow-scripts --judge-results runs/tune/judge.fixed.jsonl --out runs/tune/benchmark.json
```
