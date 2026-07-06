# Tiered Execution Pipeline

The skill still works with one agent, but orchestrators should use the cheapest executor that can do each job.

## Tier 0: Deterministic Gates

Run first on the source text:

```bash
python3 scripts/banned_phrase_scan.py <<< "$INPUT"
python3 scripts/structure_scan.py <<< "$INPUT"
python3 scripts/extract_constraints.py <<< "$INPUT"
python3 scripts/readability_metrics.py <<< "$INPUT"
```

Run again on output:

```bash
python3 scripts/banned_phrase_scan.py <<< "$OUTPUT"
python3 scripts/structure_scan.py <<< "$OUTPUT"
python3 scripts/validate_preservation.py original.txt transformed.txt
python3 scripts/readability_metrics.py <<< "$OUTPUT"
python3 scripts/diff_check.py original.txt transformed.txt
```

Output gates are blocking. Use `structure_scan.py --genre docs` or `--genre social` only when the final text truly belongs to that genre.

## Tier 1: Small Detector Agents

Run one small detector per `(pack x chunk)`. Use paragraph chunks up to about 500 words. Run `pack-register-guards` on the whole text because scope, negation, and legal/security force need context.

Detector agents only read their assigned pack from `references/packs/` and return findings:

```json
{"span":"...","rule":"...","pack":"...","severity":"hard|soft","note":"..."}
```

They do not rewrite, score, or import rules from other packs.

## Tier 2: Rewriter

Send one strong-enough rewriter the original text, merged Tier 0/Tier 1 findings, extracted constraints, and the selected preset. It rewrites from findings instead of re-running detection in prose. It must preserve register-guard and fact findings, remove phrase/structure/voice findings, and avoid introducing anti-slop-register tells.

## Model Tiers

| Job | Default executor | Escalate when |
|---|---|---|
| Tier 0 scripts | local deterministic | never; fix the script or input |
| Detection packs | smallest model that clears the parity bar (see Model Parity) | JSON is malformed or pack scope is violated |
| Short/simple rewrite | cheapest model that clears the parity bar (see Model Parity) | output fails a blocking gate twice |
| Regulated, legal, medical, security, or heavy macro rewrite | strongest practical model | start here if constraints are dense |
| Judge/eval | model specified by `evals/BEHAVIORAL-EVALS.md` | benchmark protocol changes |

The two model-dependent rows above — detection packs and replacement rewriting — are
not set by taste. They are set by `evals/run_model_parity.py` (see Model Parity). Until a
live matrix has been recorded, treat "smallest/cheapest" as provisional and default up one
tier for register-guard, legal, medical, and security text.

If Tier 2 output fails the same blocking gate twice, escalate one model tier. Do not add more rules to the prompt; the failure is execution quality.

## Model Parity

The pipeline depends on a model in exactly two places: Tier-1 pack **detection** and
Tier-2 **replacement** generation. Everything else is deterministic. Whether a cheap model
may own those surfaces is a measured question, not an assumption.

`evals/run_model_parity.py` measures it against a fixed seeded corpus:

- **Task A (detection).** Each model reads one pack file plus a short seeded chunk (the
  Tier-1 contract above) and returns JSON findings. Grading is deterministic: recall of the
  seeded findings and a count of false findings, scored against a frozen manifest. Six
  fixtures span the phrases-core, voice, and register-guard families (two are register-guard
  cases, where the load-bearing hedge must be caught).
- **Task B (replacement).** Each model is handed one seeded finding (span + rationale) and
  asked for a span-minimal replacement. Grading applies the co-writer contract: the
  replacement removes the flagged tell and adds no new one (both scanners), preserves every
  fact/number/negation, and stays span-minimal.

The matrix is config-driven — entries are `{name, kind, model_id}` where `kind` is
`claude-cli` (`claude -p --model <id>`, the Anthropic spectrum) or `openrouter` (the GPT
spectrum and others, key read from the macOS keychain service `OPENROUTER_API_KEY`). The
harness emits a per-model / per-task score table (JSON and a markdown summary) plus a
`--dry-run` mode that grades canned response fixtures with no network for the `PARITY-*`
eval rows.

**Rule (binding).** Any change to the co-writer, mimic, or detector-pack model features
must run this harness across both the GPT and Anthropic spectrums before merge, and the
detection/replacement rows of the tiering table above must be updated from its output. If
cheap models match the strong reference, use cheap everywhere; if they do not, keep the
strong model for the passes where the gap appears and record which. The `PARITY-*` rows in
`evals/adversarial-evals.json` gate the grader itself (dry-run, no network); they do not
substitute for the live run.

### Recorded results

_No live matrix recorded yet._ Fill this table from `evals/run_model_parity.py` output (a
sibling live run populates it). Columns: model, kind, Task A mean recall, Task A false
findings, Task B pass rate.

| Model | Kind | Task A recall | Task A false | Task B pass rate |
|---|---|---:|---:|---:|
| _pending live run_ | | | | |

## Cost Note

For a 1000-word document:

| Path | Calls | Approx tokens |
|---|---:|---:|
| Tier 0 | local scripts | free |
| Tier 1 | about 5 small detector calls | about 10k small-model tokens |
| Tier 2 | one rewrite call | source + findings + preset |
| Monolithic | one large call with full skill and all references | often 8k-15k strong-model tokens before output |

The tiered path spends cheap tokens on detection, reserves the stronger model for rewriting, and gives the final Tier 0 gates authority.
