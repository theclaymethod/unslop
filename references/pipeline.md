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
| Detection packs | smallest available model | JSON is malformed or pack scope is violated |
| Short/simple rewrite | mid-tier model | output fails a blocking gate twice |
| Regulated, legal, medical, security, or heavy macro rewrite | strongest practical model | start here if constraints are dense |
| Judge/eval | model specified by `evals/BEHAVIORAL-EVALS.md` | benchmark protocol changes |

If Tier 2 output fails the same blocking gate twice, escalate one model tier. Do not add more rules to the prompt; the failure is execution quality.

## Cost Note

For a 1000-word document:

| Path | Calls | Approx tokens |
|---|---:|---:|
| Tier 0 | local scripts | free |
| Tier 1 | about 5 small detector calls | about 10k small-model tokens |
| Tier 2 | one rewrite call | source + findings + preset |
| Monolithic | one large call with full skill and all references | often 8k-15k strong-model tokens before output |

The tiered path spends cheap tokens on detection, reserves the stronger model for rewriting, and gives the final Tier 0 gates authority.
