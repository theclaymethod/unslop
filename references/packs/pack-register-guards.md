# Pack: Register Guards

Use this pack to find wording that must survive a rewrite. Do not flag ordinary slop phrases and do not rewrite. This pack prevents harm.

## Look For

- Legal scope and negation: "arguably", "may", "shall", "must", "unless", "except", "not", "does not", section references, liability limits, indemnity terms.
- Medical and scientific uncertainty: "may cause", "can increase", "studies suggest", "preliminary", "observational", "does not establish causation", confidence limits, cohort limits.
- Security and safety absolutes: "never", "always", "must", "all input", "no secrets", "do not mix", when they define a rule or warning.
- Scope words and quantities: "most", "some", "only", "at least", "no more than", percentages, ranges, dates, named parties.
- Anti-dehedging traps: a phrase that looks cautious but carries the claim's certainty, exception, or legal burden.

Run on the whole text, not paragraph chunks, because scope can be established earlier than the sentence being rewritten.

## Emit

Return JSON findings only:

```json
{"span":"arguably does not rise to gross negligence","rule":"legal_negation_scope","pack":"pack-register-guards","severity":"hard","note":"Hedge and negation are load-bearing; preserve them exactly."}
```

Every finding is a preservation constraint. Use `hard` when changing it could invert or strengthen the claim; `soft` when it is likely load-bearing but needs human review.

## Examples

- "The incident arguably does not rise to gross negligence under Section 12(b)." -> report the full legal hedge/negation span.
- "Users should never store secrets in client-side code." -> report "never store secrets".
- "It is worth noting that the button is blue." -> no finding; ordinary filler belongs to another pack.
- "The trial may cause drowsiness in some patients." -> report "may" and "some patients".
