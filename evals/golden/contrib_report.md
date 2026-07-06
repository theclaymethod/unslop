# Add significance_inflation pattern: durable bridge

## The specimen

> The rollout guide keeps saying the migration path gives teams a durable bridge between the old queue and the new worker pool, but it never explains the retry contract.

- Source genre: technical rollout note
- Date: 2026-07-06
- Redaction note: none

## Why it's an AI-ism

`Durable bridge` inflates a migration detail into a vague promise. It sounds reassuring without naming the compatibility behavior, failure mode, or owner.

## Detection

- Pattern added: `durable bridge`
- Severity: soft
- Gating rationale: flag metaphorical migration praise, protect literal construction
- Catalog entry location: references/taboo-phrases.md

## Evals

| row id | kind | what it pins |
|---|---|---|
| CONTRIB-FN-durable-bridge | FN | exact specimen flags `durable bridge` |
| CONTRIB-FP-durable-bridge | FP | literal-use protection for `durable bridge` |

The FN stdin is the unmodified specimen after approved redaction.

## Gate results

### contribute-slice

```text
PASS CONTRIB-01 precheck names covering pattern
PASS CONTRIB-02 precheck accepts uncaught tell
PASS CONTRIB-03 scaffold preserves specimen bytes
```

## Checklist

- [ ] eval-first (row was red before the pattern)
- [ ] literal-use FP row included
- [ ] REC row if an existing word was gated
- [ ] catalog + scanner parity green
- [ ] coverage gate green (pattern exercised)
- [ ] snippet publication approved by the user
