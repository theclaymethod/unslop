# UNSLOP core rewrite contract

## Goal

Repair concrete AI-writing or clarity defects. Leave everything else unchanged;
prefer a no-op to an uncertain edit.

## Findings

Quote the smallest defective span and explain the contextual defect: formulaic
framing, empty or inflated abstraction, unsupported rhetorical certainty,
opaque or mixed metaphor, misleading heading, needless repetition, or clear
internal contradiction or ambiguity. Track every hard scanner match and other
defect as confirmed or protected, with a reason; repair every confirmed span.
One repair does not excuse another nearby defect.

Do not fact-check or infer truth from the date or outside knowledge. Missing
proof alone does not make a plan, offer, future date, promotion, technical term,
literal phrase, or attribution defective.

Compare the source's claims. Qualify a status contradicted by observations.
Explicitly reject every initial, conditional, or repeat action that exceeds a
stated limit; a hedge does not make it safe. Preserve evidence and quantities.
Keep attributed claims intact and state conflicts separately. Make no edit when
nearby prose already states the conflict and uncertainty. Attribution does not
protect a separate operative recommendation.

A scanner match alone never authorizes an edit. Protect literal, domain-valid,
quoted, attributed, accurately caveated, or genre-natural uses. In ordinary
business prose, confirm stock praise, filler, or vague evaluation only when
context supplies no mechanism, definition, action, or measure. A noun referent
alone is insufficient: "game-changer for the product" stays vague unless the
text says what changes. "Actionable" is valid with defined actions; "raises the
bar" is valid when literal or measured. Soft cadence and document-shape scores
never authorize edits alone.

For headings and slide titles, replace inanimate agency, tool personification,
or vague transformation with the actor, test, mechanism, result, decision, or
completion criterion. Renaming the same abstraction is not a repair. When macro
cleanup is requested, remove connective scaffolding and a moralizing recap coda,
including repeated facts; its lesson is not protected.

Inspect slogans and closing calls to action even when tools are quiet. Flag
false equivalence, contradicted certainty, empty abstraction, or incompatible
metaphors. Protect concrete promotions, genuine aphorisms, capped offers, future
plans, and concrete calls to action unless the source contradicts them. A stock
journey or milestone sentence adding no fact, action, or claim is empty.

## Rewrite

Edit only sentences with confirmed findings, using the smallest repair. Copy
every other sentence byte-for-byte in its original order and paragraph. With no
findings, return the source exactly.

Preserve facts, quantities, dates, names, quotations, citations, code, units,
scope, uncertainty, attribution, register, and meaning. Add no claims, advice,
personality, anecdote, certainty, or conclusion. Do not substitute stock phrases
or create staccato anti-slop prose. Preserve force-bearing "never", "must", and
"all" exactly in safety, security, legal, and technical rules. Presets change
delivery, not facts. For lists, return one validated replacement per item.

For audit-only requests, report findings and protections without rewriting;
report each requested load-bearing span separately. Exact no-op applies to
rewrites, not audits that must report protections.

## Decision rule

Return a finding only when the contextual defect is clearer than preservation.

## Validation

After every rewrite or voiced draft, run:

```bash
python3 scripts/validate_preservation.py original.txt transformed.txt
python3 scripts/banned_phrase_scan.py <<< "$OUTPUT"
python3 scripts/structure_scan.py <<< "$OUTPUT"
python3 scripts/silhouette_scan.py <<< "$OUTPUT"
python3 scripts/readability_metrics.py <<< "$OUTPUT"
python3 scripts/diff_check.py original.txt transformed.txt
```

Block preservation loss, introduced hard or `anti_slop_register` hits,
unjustified structural damage, corroborated or hard silhouette damage, staccato,
and strict-mode scores below 32/40. Use preservation `--strict` for legal,
medical, security, or scientific text. Preexisting soft cadence and
uncorroborated soft silhouette warnings are advisory.

For remaining structure damage, pass exact findings to
`evals/run_structure_climb.py`. Re-read negations, conditions, scope, certainty,
and party relationships.
