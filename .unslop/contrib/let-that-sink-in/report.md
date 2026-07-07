# Add emphasis_crutch pattern: Let that sink in

## The specimen

> The launch memo ends with a warning instead of evidence. Let that sink in before you ask what changed.

- Source genre: TODO: source genre
- Date: 2026-07-06
- Redaction note: none

## Why it's an AI-ism

TODO: explain why this phrase is a reusable AI-writing tell in 2-4 sentences.

## Detection

- Pattern added: TODO: regex or phrase for `Let that sink in`
- Severity: TODO: hard or soft
- Gating rationale: TODO: explain literal-use boundary
- Catalog entry location: references/taboo-phrases.md

## Evals

| row id | kind | what it pins |
|---|---|---|
| CONTRIB-FN-let-that-sink-in | FN | exact specimen flags `Let that sink in` |
| CONTRIB-FP-let-that-sink-in | FP | literal-use protection for `Let that sink in` |

The FN stdin is the unmodified specimen after approved redaction.

## Gate results

red-first: already green; proposed pattern appears active

## Checklist

- [ ] eval-first (row was red before the pattern)
- [ ] literal-use FP row included
- [ ] REC row if an existing word was gated
- [ ] catalog + scanner parity green
- [ ] coverage gate green (pattern exercised)
- [ ] snippet publication approved by the user
