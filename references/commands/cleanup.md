# /unslop cleanup

Surface AI patterns as reviewable edits the user accepts or rejects, rather than
a finished rewrite. Agent-invoked, never a background daemon. Route here on
`/unslop cleanup` or when the user wants suggestions instead of a silent rewrite.
Set `$INPUT` to the source.

## Report-only variant

When the user says "flag only", "just detect", "audit only", "don't change
anything", or passes `--report`, change nothing. Scan and report:

```bash
python3 scripts/banned_phrase_scan.py <<< "$INPUT"
python3 scripts/structure_scan.py <<< "$INPUT"
python3 scripts/silhouette_scan.py <<< "$INPUT"
python3 scripts/readability_metrics.py <<< "$INPUT"
```

Report each issue by span, category, severity, and why it reads as machine-
written, separating clear problems from register-dependent judgment calls (the
audit-only shape in SKILL.md **Output Format**). Re-read negations, scope, and
certainty yourself; the scanners are necessary, not sufficient.

## Suggestion flow

```bash
python3 scripts/suggest.py document.md            # emit suggestions
python3 scripts/suggest.py doc.md --apply-replacements repl.json   # merge model replacements
python3 scripts/check_suggestions.py suggestions.json              # blocking contract gates
```

- **Detection is cheap and deterministic.** `suggest.py` runs both scanners and
  emits LSP-style suggestions `{span, severity, category, rationale,
  suggested_replacement, phrased_as_question}`, ordered and non-overlapping.
- **Replacement generation is delegated to a stronger model.** `suggest.py`
  leaves `suggested_replacement` null; the stronger model fills them, merged back
  via `--apply-replacements`.
- **Hard findings** become direct replacements; **soft findings** are register-
  dependent, so their rationale is phrased as a question
  (`phrased_as_question: true`).
- **Suggestions are surfaced to the user, never silently applied.**

## Contract gates

`check_suggestions.py` is the blocking contract. Every replacement clears all
four gates or it is rejected:

- `span-minimality`: the edit changes only its span (a whole-sentence rewrite
  fails).
- `replacement-scanner`: each replacement passes both scanners in isolation and
  adds no new violation in context.
- `accept-all`: applying every suggestion yields a document that passes both
  scanners with `validate_preservation` exit 0 versus the original.
- `span-overlap`: spans must not overlap.

Non-English input is declined the way the scanners decline it: `suggest.py`
returns `non_english: true` with no suggestions. For a full rewrite instead of
suggestions, route to `references/commands/rewrite.md`.
