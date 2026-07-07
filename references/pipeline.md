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
| Detection packs | cheapest tier (see Model Parity) | JSON is malformed or pack scope is violated |
| Span replacement / short rewrite | cheapest tier; gates carry safety (parity 2026-07-06: 8/8) | output fails a blocking gate twice |
| Full rewrite of register-sensitive text (legal, medical, security, load-bearing hedges) | strongest practical model + mandatory Tier-0 re-scan | start here; cheap tiers erode register |
| Macro structure (restructuring, coda/preview removal) | machine-gated, never self-checked — surface via Tier-0 scan | never trust a model's own macro self-check |
| Judge/eval | model specified by `evals/BEHAVIORAL-EVALS.md` | benchmark protocol changes |

The model-dependent rows above are not set by taste. They are set by
`evals/run_model_parity.py` (see Model Parity), whose live matrix was recorded 2026-07-06:
span replacement clears on the cheapest tier because the output gates carry safety, while
full rewrites of register-sensitive text and any macro restructuring escalate to the
strongest practical model with a Tier-0 re-scan. Re-run the harness when the model features
change and update these rows from its output.

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

Live matrix recorded **2026-07-06**. `evals/run_model_parity.py` re-measures on demand;
rerun it after any change to the co-writer, mimic, or detector-pack model features and
update these tables from its output.

**Task B — span replacement.** One seeded finding (span + rationale) per trial, graded on
the co-writer contract: the replacement removes the flagged tell, adds no new one (both
scanners), preserves every fact/number/negation, and stays span-minimal. Eight seeded
findings per model.

| Model | Kind | Task B pass rate |
|---|---|---:|
| claude-haiku | claude-cli | 8/8 |
| claude-sonnet | claude-cli | 8/8 |
| gpt-5.4-mini | openrouter | 8/8 |
| gpt-5.5 | openrouter | 8/8 |
| claude-opus | claude-cli | 7/8 |

The single miss was opus dropping the fact "8:30" from a replacement — caught by
`validate_preservation`, not by model choice. On the mechanical span contract the cheapest
tier ties the flagships; the gates carry safety, the tier does not.

**Behavioral parity matrix — full rewrites.** Eight register/structure cases per model,
graded deterministically across both the Anthropic and GPT spectrums.

| Model | Kind | Full-rewrite pass rate |
|---|---|---:|
| claude-opus | claude-cli | 7/8 |
| gpt-5.4-mini | openrouter | 7/8 |
| claude-sonnet | claude-cli | 6/8 |
| gpt-5.5 | openrouter | 6/8 |
| claude-haiku | claude-cli | 5/8 |
| gpt-5.4-nano | openrouter | 5/8 |

`MACRO-01` (`structure_clean`) failed for all six models, opus included: each kept a
conclusion coda the prose instruction told it to drop. No model self-checks macro structure
from prose. The cheap-tier misses were register and fact erosion in full rewrites — softened
`never`/`all`, a dropped `roughly`, a dropped legal `arguably`/negation, an emitted
`X, not Y` contrastive tail. The lab ladders are symmetric (7/6/5 on both spectrums).

**Measured conclusions.**

- **Span replacement = cheapest tier, with gates on.** The output gates enforce fact and
  tell safety, so the smallest model is safe for span-minimal replacement.
- **Full rewrites of register-sensitive text = frontier.** Legal, medical, security, or any
  text with load-bearing hedges/negation goes to the strongest practical model with a
  mandatory Tier-0 re-scan; cheap models erode register in unsupervised full rewrites.
- **Macro structure = always machine-gated, never self-checked.** A Tier-0 scan surfaces it
  as an explicit directive, because no model, flagship included, reliably catches it from
  prose instructions.

### Open-weights spot check — 2026-07-07

Live matrix run against the current open-weights flagships of three Chinese labs, each the
newest general chat release of its family on OpenRouter: DeepSeek V4 Pro
(`deepseek/deepseek-v4-pro`), Kimi K2.6 (`moonshotai/kimi-k2.6`), and GLM 5.2
(`z-ai/glm-5.2`). Same harness and contracts as above; six detection fixtures (Task A) and
six replacement fixtures (Task B) per model. Models file:
`evals/fixtures/parity/models_openweights.json`.

| Model | Kind | Task A mean recall | Task A false findings | Task B pass rate |
|---|---|---:|---:|---:|
| glm-5.2 | openrouter | 1.00 | 0 | 6/6 |
| deepseek-v4-pro | openrouter | 0.92 | 1 | 6/6 |
| kimi-k2.6 | openrouter | 0.92 | 0 | 6/6 |

All three clear the span-replacement contract at 6/6, and the only detection misses were
one seeded voice span apiece (fixture A4) for DeepSeek and Kimi; on both model-dependent
surfaces the open-weights flagships sit level with the recorded GPT and Anthropic ladders.

## Cost Note

For a 1000-word document:

| Path | Calls | Approx tokens |
|---|---:|---:|
| Tier 0 | local scripts | free |
| Tier 1 | about 5 small detector calls | about 10k small-model tokens |
| Tier 2 | one rewrite call | source + findings + preset |
| Monolithic | one large call with full skill and all references | often 8k-15k strong-model tokens before output |

The tiered path spends cheap tokens on detection, reserves the stronger model for rewriting, and gives the final Tier 0 gates authority.
