# UNSLOP core rewrite contract

## Findings

Read the whole source first, including headings and endings. Find the smallest span with a concrete defect. Explain what it obscures, repeats, exaggerates, or contradicts. Empty framing can go when deletion costs no meaning. Replace vague headings or praise with the actual actor, action, or result in the source. For requested structural edits, cut redundant transitions and closing recaps.

Review each hard scanner hit. Protect quotations, literal and technical uses, measured claims, genuine offers, and language natural to the genre. A scanner hit, unusual rhythm, unsupported suspicion, or personal preference cannot justify a change. Use only the source as evidence.

Resolve internal contradictions without inventing facts. Keep attributed statements intact. When the source recommends acting on a contradicted claim, explicitly correct the recommendation as well as identifying the conflict. Reject every recommended action that exceeds an explicit limit, including repeats and conditional steps. Leave already acknowledged uncertainty intact.

## Rewrite

Edit only confirmed defects. Copy other sentences byte-for-byte in their original order and paragraphs. With no findings, return the source exactly. Preserve facts, scope, attribution, code, quotations, register and uncertainty. Keep “never”, “must” and “all” exactly where they define requirements. Return one validated replacement per list item. A preset changes delivery only.

For an audit, report each requested span and why you would repair or protect it. Leave the source intact.

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
