# Pack: Facts

Use this pack for facts and constraints that must survive a rewrite. Do not judge style or phrase quality.

## Look For

- Constraints from `extract_constraints.py`: numbers, dates, times, names, URLs, emails, quoted text, code identifiers, currencies, percentages, units, ranges.
- Negations, conditionals, and scope words surfaced by preservation validation: "not", "unless", "except", "only", "must", "may", "can", "at least", "no more than".
- Approximation traps: "roughly 60%" is not "60%"; "Q2" is not "June"; "under 500 ms" is not "500 ms".
- Proper-noun and party relationships: Apple sued Qualcomm is not Qualcomm sued Apple.
- Technical literals: API names, flags, file paths, version numbers, protocol names.

## Emit

Return JSON findings only:

```json
{"span":"roughly 60%","rule":"approximate_quantity","pack":"pack-facts","severity":"hard","note":"Keep the approximation marker with the number."}
```

Use `hard` for exact facts, negations, scope, and quantities. Use `soft` for phrasing that appears factual but may be compressible.

## Examples

- "p99 latency fell to 180 ms on June 18" -> report p99, 180 ms, June 18.
- "roughly 60%" -> report the approximation and number together.
- "The team improved performance." -> no finding; style claim without a concrete constraint.
- "`--strict` failed on v2.1.0" -> report flag and version.
