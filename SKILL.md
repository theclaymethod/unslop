---
name: unslop
description: Remove AI writing patterns from prose using either audit-only detection or a two-pass rewrite flow (diagnosis then reconstruction). Use this skill when editing, reviewing, or rewriting AI-generated content to make it sound human. Triggers on requests to "humanize", "de-slop", "fix AI text", "make it sound human", "remove AI patterns", or when reviewing text that contains obvious AI tells like "Here's the thing:", "Let that sink in", or "In today's fast-paced landscape". Also use when the user pastes text and says it "sounds like ChatGPT", "sounds robotic", "needs to sound more natural", or asks you to "clean up" drafted content before publishing.
license: MIT
metadata:
  author: claytonkim
  version: "2.3.0"
---

# Unslop

Humanize AI-generated prose. Audit first. Rewrite only when the user asks for a rewrite.

## When to Use

- User asks to humanize, de-slop, clean up, or make text sound natural.
- Drafts contain obvious AI tells: throat-clearing, scaffolded conclusions, inflated significance, em-dash abuse, or staccato fragment drama.
- User asks for an audit, scan, or review of prose before publishing.

## Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--preset` | Voice style: `crisp`, `warm`, `expert`, `story` | `crisp` |
| `--strict` | Fail if rubric score < 32/40 | false |
| `--audit-only` | Flag AI patterns without rewriting | false |
| Input | Text to transform (argument, file path, or stdin) | required |

## Modes

- `rewrite` (default): diagnose, rewrite, then validate.
- `audit-only`: diagnose and assess without rewriting.

Use audit-only when the user says "audit only," "flag only," "scan this," "just detect," "don't rewrite," or passes `--audit-only`.

## Voice Presets

Read one preset from `presets/` before writing.

| Preset | Style | Best For |
|--------|-------|----------|
| `crisp` | Short, direct, no fluff | Technical writing, documentation |
| `warm` | Friendly, conversational | Emails, blog posts |
| `expert` | Authoritative, confident | Thought leadership, articles |
| `story` | Narrative flow, show don't tell | Case studies, personal posts |

## Execution Paths

### Single-Agent Path

Use this when you are the only executor. Follow the same tiers sequentially:

1. Extract facts and constraints:
   ```bash
   python3 scripts/extract_constraints.py <<< "$INPUT"
   ```
2. Scan the source:
   ```bash
   python3 scripts/banned_phrase_scan.py <<< "$INPUT"
   python3 scripts/structure_scan.py <<< "$INPUT"
   python3 scripts/silhouette_scan.py <<< "$INPUT"
   python3 scripts/readability_metrics.py <<< "$INPUT"
   ```
   Use `--genre docs` or `--genre social` only when the input truly belongs to that genre. Use `banned_phrase_scan.py --include-quoted` only when the user wants quoted examples audited too.
3. Read the selected preset. Read `references/taboo-phrases.md` for phrase edge cases, `references/fact-preservation.md` for dense facts, `references/rubric.md` for strict scoring, and `references/personality-guide.md` only when clean output still feels anonymous.
4. If auditing, report issues by span, category, severity, and reason. Do not rewrite.
5. If rewriting, preserve every fact and register guard, remove the real AI tells, and match the chosen preset.
6. Validate the output with the gates below before returning it.

### Orchestrated Path

For multi-agent harnesses, use `references/pipeline.md`: Tier 0 deterministic scripts, Tier 1 small detector agents over `references/packs/`, Tier 2 one rewriter, then Tier 0 validation again. The skill must still work without that file; the pipeline is an efficiency architecture, not a dependency.

## Rewrite Principles

- Cut throat-clearing and scaffolding. Start with the claim.
- Replace inflated importance with the concrete fact.
- Prefer short, direct sentences, but avoid telegraphic staccato.
- Use em-dashes sparingly. A single appositive dash can be fine; clusters are a tell. Never trade a dash for a comma splice — if a dash is wrong, use a period.
- Facts are sacred: numbers, names, dates, URLs, quotes, code identifiers, units, and scope words must survive.
- Do not invent first-person experience, anecdotes, or certainty the source does not support.
- Do not replace AI slop with anti-slop register: "Not X. Y.", forced punch endings, or runs of tiny fragments.

## Register Guards

Before removing a hedge or strengthening a sentence, check whether the register requires it:

- Legal: keep hedges, negations, exceptions, section references, liability terms, and scope words.
- Medical/scientific: keep uncertainty, study limits, cohort limits, causation limits, and adverse-effect qualifiers.
- Security/safety: keep forceful absolutes such as "never", "must", "all input", and "do not" when they define a rule.
- Technical docs: keep precise terms, flags, API names, version numbers, file paths, and code semantics.

If a gate fails twice after rewrite, escalate model tier rather than adding more prompt rules. The failure is execution quality.

## Validation

Run after every rewrite:

```bash
python3 scripts/validate_preservation.py original.txt transformed.txt
python3 scripts/banned_phrase_scan.py <<< "$OUTPUT"
python3 scripts/structure_scan.py <<< "$OUTPUT"
python3 scripts/silhouette_scan.py <<< "$OUTPUT"
python3 scripts/readability_metrics.py <<< "$OUTPUT"
python3 scripts/diff_check.py original.txt transformed.txt
```

Blocking output failures:

- Any hard banned-phrase hit.
- Any `anti_slop_register` hit, even if soft.
- Any `structure_scan.py` flag unless the actual genre justifies `--genre docs` or `--genre social`.
- Any `silhouette_scan.py` flag (`silhouette_penalty >= 1.0`) unless the genre justifies it: `--genre docs` retains the outline-following tell (`heading_preview`) because reference docs still should not read as a preview-then-fulfill template.
- Preservation warnings that show a dropped or changed negation, hedge, scope word, number, date, name, quote, URL, unit, or code identifier. The default gate warns without failing; run `validate_preservation.py --strict` for legal, medical, security, or scientific text so these exit non-zero.
- Staccato cadence in readability metrics.
- Rubric score below 32/40 in strict mode.

Validation scripts are necessary but not enough. Re-read negations, conditionals, scope, certainty, and party relationships yourself.

## Output Format

For a quick rewrite, return the cleaned text only. For audit-only:

```markdown
## Issues Found

- [Quoted issue, category, severity, why it reads as AI]

## Assessment

- [Which issues are clear problems]
- [Which issues are judgment calls or context-dependent]
```

For strict or requested analysis:

```markdown
## Transformed Text

[The humanized version]

## Validation

- Constraints: [X]/[Y] preserved
- AI patterns: [N] remaining (was [M])
- Structure: [pass/fail]
- Readability: Grade [X], sentence variance [Y]
- Change: [X]% from original
- Score: [X]/40
```

## Co-writer Mode

When a user wants findings surfaced as reviewable edits rather than a finished
rewrite, use co-writer mode. It is agent-invoked, never a background daemon.

```bash
python3 scripts/suggest.py document.md            # emit suggestions (replacements delegated)
python3 scripts/suggest.py doc.md --apply-replacements repl.json   # merge model replacements
python3 scripts/check_suggestions.py suggestions.json              # blocking contract gates
```

Split of labor:

- **Detection is cheap and deterministic.** `suggest.py` runs both scanners and
  emits LSP-style suggestions `{span, severity, category, rationale,
  suggested_replacement, phrased_as_question}`, ordered and non-overlapping.
- **Replacement generation is delegated to a stronger model.** `suggest.py`
  leaves `suggested_replacement` null; a stronger model fills the replacements,
  merged back via `--apply-replacements`.
- **Hard findings** are stated as direct replacements. **Soft findings** are
  register-dependent judgment calls, so their rationale is phrased as a question
  (`phrased_as_question: true`).
- **Suggestions are surfaced to the user, never silently applied.**

`check_suggestions.py` is the blocking contract. Every proposed replacement must
clear all four gates or it is rejected:

- `span-minimality` — the edit changes only its span (no shared leading/trailing
  whole words; a whole-sentence rewrite fails).
- `replacement-scanner` — each replacement passes both scanners in isolation and
  introduces no new violation in context.
- `accept-all` — applying every suggestion yields a document that passes both
  scanners with `validate_preservation` exit 0 versus the original.
- `span-overlap` — spans must not overlap.

Non-English input is declined the same way as the scanners: `suggest.py` returns
`non_english: true` with no suggestions.

## Quick Examples

**Input:**
> Here's the thing: building products is hard. Not because the technology is complex. Because people are complex. Let that sink in.

**Output (crisp):**
> Building products is hard, and not because the technology is complex. People are complex, and they are the part you cannot refactor.

**Input:**
> In today's fast-paced business environment, it's becoming increasingly important for organizations to leverage their core competencies while navigating the complex landscape of digital transformation.

**Output (crisp):**
> Companies need to use their strengths while going digital.

## Reference Files

| File | When to Read |
|------|-------------|
| `references/pipeline.md` | Orchestrated tiered execution. |
| `references/packs/*.md` | Small detector-agent rule packs. |
| `references/taboo-phrases.md` | Authoritative phrase catalog and scanner categories. |
| `references/fact-preservation.md` | Constraint preservation rules. |
| `references/rubric.md` | Strict scoring. |
| `references/edit-library.md` | Transformation examples when a pattern is unclear. |
| `references/personality-guide.md` | Adding genuine voice without fake personality. |
| `references/harvest.md` | Bootstrapping teach samples from transcripts and writing folders. |
| `references/calibrate.md` | The teach A/B calibration game: dimension-controlled pairs, scoring, conflict surfacing. |
| `references/maintenance.md` | Pattern add/list procedures and Wikipedia sync. |
| `presets/*.md` | Voice-specific deltas. |
| `assets/examples/*.md` | Extended before/after examples by content type (article, LinkedIn, sales). |

## Maintenance

The eval suite defines the product. Add or change patterns eval-first in `evals/adversarial-evals.json`; do not edit `evals/evals.json`. New scanner patterns need one false-negative row and one false-positive protection row. Agent behavior changes need a `skill` row and a regenerated shared benchmark. For the concrete procedures (add a phrase or structure, list current patterns, sync with Wikipedia's signs-of-AI-writing page), read `references/maintenance.md`.
