# Handoff

Pick-up notes for continuing this work in a local Claude Code session. A fresh
session has none of the prior chat memory — this file plus the repo is the context.

## Where things are

- **Branch:** `claude/skill-eval-adversarial-264jen` (PR #1). All work is committed
  and pushed; the working tree is clean. Nothing lives only in the cloud session.
- **What was done (in order):** built an adversarial eval suite + critique;
  fixed the script-level bugs it exposed; hardened all scripts + the runner and
  added CI; expanded the pattern catalog from Wikipedia and the Berens–Kobak
  PubMed study; ran an adversarial audit of the *writing the skill produces*,
  found it traded slop for a detectable "anti-slop" register, fixed that at the
  root (gold examples + scanner + SKILL guards), and re-ran the adversary to
  confirm the thesis is now refuted.

### File map

| Path | What it is |
|------|-----------|
| `evals/adversarial-evals.json` | 77 cases: 51 deterministic `script` + 26 behavioral `skill`. |
| `evals/run_adversarial.py` | Runner for the **script** cases (PASS/FAIL/XFAIL/XPASS). |
| `evals/fixtures/` | Input pairs for file-based cases. |
| `evals/CRITIQUE.md` | The skill + eval critique and defect table. |
| `evals/ADVERSARIAL-WRITING-ANALYSIS.md` | The writing-quality red-team + re-test verdict. |
| `.github/workflows/evals.yml` | CI: compiles scripts, runs the script harness. |

### Run it locally

```bash
git fetch origin && git checkout claude/skill-eval-adversarial-264jen && git pull
python3 evals/run_adversarial.py            # expect 50 PASS / 1 XFAIL / 0 FAIL
python3 evals/run_adversarial.py --list-skill   # the 26 behavioral cases
```

The single XFAIL (FP-06, literal "delve into a place") is a documented regex limit,
kept on purpose.

## Next task: adopt adewale/skill-eval-harness for the behavioral layer

`run_adversarial.py` grades the **Python tooling** deterministically (does the
scanner flag X, does validation fail). It does **not** run the skill or grade the
skill's prose — the 26 `skill` cases are currently judged by hand. The
[skill-eval-harness](https://github.com/adewale/skill-eval-harness) is a mature
tool that fills exactly that gap. Keep both layers; they are complementary.

### Why it fits

- **`judge` assertions + deferred judge flow** (`skill-benchmark judge --judge-cmd
  'claude -p'`) → automates our 26 behavioral cases instead of hand-grading.
- **`with_skill` / `without_skill` variant pairing + paired deltas** → proves the
  skill *causes* the improvement (lift), not that the output happened to be fine.
  Our suite never measures lift; this is the biggest missing signal.
- **Leakage lint + saturation/no-lift detection** → our `FN-*`/`DET-*` cases put
  the target phrase in the prompt; that's fine for deterministic scanner detection
  but the lint correctly flags it as saturation-prone for *skill* cases. Use lift,
  not phrase-presence, to score behavioral cases.
- **splits (tune/holdout/holdback)** → guards against overfitting the skill to its
  own evals (a real risk after this much iteration).

### Concrete steps

1. `uv tool install git+https://github.com/adewale/skill-eval-harness.git` (pin a tag).
2. Author `evals/shared-benchmark.json` (the harness's required manifest). Map each
   behavioral `skill` case from `adversarial-evals.json` to a case with
   `variants: [with_skill, without_skill]`, `prompt`, `expected_behavior`, and
   `assertions`. Translate our `judge` checks to the harness `judge`/`rubric` type
   and our content checks to `contains_any` / `excludes_any` / `regex`.
   - Worked examples to port first (highest signal): `SKILL-FRAGMENT-01`,
     `SKILL-HEDGE-03`, `SKILL-LEGAL-02`, `SKILL-STACCATO-01`, `SKILL-NOINVENT-01`.
   - For the anti-slop and fact checks, use a `script` assertion that runs our own
     `scripts/banned_phrase_scan.py` / `validate_preservation.py` over the run's
     `output.md` — reuse the tooling we already hardened.
3. `skill-benchmark validate evals/shared-benchmark.json` (catches leakage + fixture issues).
4. `skill-benchmark prepare ... --split tune` → run via a local Claude Code runner →
   `skill-benchmark grade ... --judge-cmd 'claude -p'` → `skill-benchmark benchmark`.
5. Wire the deterministic half into `.github/workflows/evals.yml`; keep the judge
   half manual/local (needs model calls + credentials).

### Why this is a local task, not a cloud one

The harness executes the skill through a real runner (Claude Code / Codex) and the
judge calls a model (`claude -p`) — both want your local CLI, credentials, and
possibly API tokens, which is cleaner in a local session than in this sandbox.
