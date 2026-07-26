# /unslop rewrite

The default command. Bare `/unslop <text>` routes here. Two passes: diagnose,
then reconstruct under the register guards, then prove the result with the gates.

Input arrives as an argument, a file path, or stdin. Set `$INPUT` to the source
and `$OUTPUT` to your rewrite.

## Pass 1 — diagnose

1. Extract the facts and constraints that must survive:
   ```bash
   python3 scripts/extract_constraints.py <<< "$INPUT"
   ```
2. Scan the source so the rewrite answers evidence, not a hunch:
   ```bash
   python3 scripts/banned_phrase_scan.py <<< "$INPUT"
   python3 scripts/structure_scan.py <<< "$INPUT"
   python3 scripts/silhouette_scan.py <<< "$INPUT"
   python3 scripts/readability_metrics.py <<< "$INPUT"
   ```
   Pass `--genre docs` or `--genre social` only when the input truly belongs to
   that genre. Add `banned_phrase_scan.py --include-quoted` only when the user
   wants quoted examples audited too.
3. Note the traits that make the draft sound like a person, per SKILL.md
   **Preservation**. Three to five is enough. If every scan in step 2 came back
   clean, stop here, return the text unchanged, and say it was already clean
   rather than reaching for something to fix.
4. Read the selected preset from `presets/`. Reach for
   `references/taboo-phrases.md` on phrase edge cases,
   `references/fact-preservation.md` on dense facts, `references/rubric.md` for
   strict scoring, and `references/personality-guide.md` only when a clean draft
   still reads as anonymous.

## Pass 2 — reconstruct

Rewrite under the SKILL.md **Rewrite Principles**, **Preservation**, and
**Register Guards**. Cut the throat-clearing, keep every fact and guard word,
match the preset, and never trade AI slop for anti-slop cadence. Scope the edit
to the findings from Pass 1, and carry the traits you noted in step 3 through
the rewrite so the paragraph still reads as the same writer. Findings bound the
diff. If a gate fails twice after rewrite,
escalate the model tier instead of piling on prompt rules.

## Validate

Run the full gate battery from SKILL.md **Validation** on `$OUTPUT` before
returning it. A hard banned-phrase hit, a structure or silhouette flag, an
`anti_slop_register` hit, a dropped constraint, or staccato cadence all block
the return. Use `validate_preservation.py --strict` for legal, medical,
security, or scientific text.

Return the cleaned text only, unless the user asked for the strict analysis
block in SKILL.md **Output Format**.

For multi-agent execution, use `references/pipeline.md`; for orchestrated
detector packs, use `references/packs/`.
