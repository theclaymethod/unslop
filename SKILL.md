---
name: unslop
description: Remove AI writing patterns from prose using a two-pass system (diagnosis → reconstruction). Use this skill when editing, reviewing, or rewriting AI-generated content to make it sound human. Triggers on requests to "humanize", "de-slop", "fix AI text", "make it sound human", "remove AI patterns", or when reviewing text that contains obvious AI tells like "Here's the thing:", "Let that sink in", or "In today's fast-paced landscape".
license: MIT
metadata:
  author: claytonkim
  version: "1.0.0"
---

# Unslop

Comprehensive skill for humanizing AI-generated content. Two-pass system: diagnosis → reconstruction with validation.

## When to Use

Apply this skill when:
- User asks to "humanize" or "de-slop" text
- Editing AI-generated drafts, emails, articles, or social posts
- Text contains obvious AI patterns (throat-clearing, binary contrasts, emphasis crutches)
- User says text "sounds like AI" or "sounds robotic"
- Reviewing content before publishing
- User asks to "make it sound more natural" or "like a human wrote it"

## Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--preset` | Voice style: `crisp`, `warm`, `expert`, `story` | `crisp` |
| `--strict` | Fail if rubric score < 32/40 | false |
| Input | Text to transform (argument, file path, or stdin) | required |

## Voice Presets

| Preset | Style | Best For |
|--------|-------|----------|
| `crisp` | Short, direct, no fluff | Technical writing, documentation |
| `warm` | Friendly, conversational | Emails, blog posts |
| `expert` | Authoritative, confident | Thought leadership, articles |
| `story` | Narrative flow, show don't tell | Case studies, personal posts |

## Workflow

### Pass 1: Diagnosis

Before rewriting, analyze the input:

1. **Read reference materials** from this skill's directory:
   - `references/taboo-phrases.md` - banned phrases and patterns
   - `references/rubric.md` - 8 scoring criteria
   - `references/fact-preservation.md` - what must survive

2. **Extract constraints** (facts that must survive):
   ```bash
   python3 <skill-path>/scripts/extract_constraints.py <<< "$INPUT"
   ```

3. **Scan for AI-isms**:
   ```bash
   python3 <skill-path>/scripts/banned_phrase_scan.py <<< "$INPUT"
   ```

4. **Read the selected preset** from `presets/` directory

5. **Identify**: audience, content type, tone target

### Pass 2: Reconstruction

Rewrite following these rules:

1. **Eliminate all AI-isms** cataloged in taboo-phrases.md
2. **Follow preset voice** characteristics
3. **Preserve all constraints** (numbers, names, dates, URLs)
4. **Apply rubric criteria**:
   - Directness: No hedging, no throat-clearing
   - Natural rhythm: Vary sentence length (8-25 words)
   - Concrete verbs: Specific actions, not abstractions
   - Reader trust: No over-explaining
   - Human authenticity: No performative emphasis
   - Content density: Substance over filler
   - Fact preservation: All facts intact
   - Template avoidance: No AI structural clichés

### Pass 3: Validation

After rewriting, validate:

1. **Fact preservation**:
   ```bash
   python3 <skill-path>/scripts/validate_preservation.py original.txt transformed.txt
   ```

2. **Remaining AI-isms**:
   ```bash
   python3 <skill-path>/scripts/banned_phrase_scan.py <<< "$OUTPUT"
   ```

3. **Readability metrics**:
   ```bash
   python3 <skill-path>/scripts/readability_metrics.py <<< "$OUTPUT"
   ```

4. **Change percentage** (flag if >40%):
   ```bash
   python3 <skill-path>/scripts/diff_check.py original.txt transformed.txt
   ```

5. **Score against rubric** (8 criteria × 5 points = 40 max)

## Output Format

```markdown
## Transformed Text

[The humanized version]

## Validation

- Constraints: [X]/[Y] preserved
- AI-isms: [N] remaining
- Readability: Grade [X], variance [Y]
- Change: [X]% from original
- Score: [X]/40

## Changes Made

- [List of major transformations]
```

## Quick Examples

**Input:**
> Here's the thing: building products is hard. Not because the technology is complex. Because people are complex. Let that sink in.

**Output (crisp):**
> Building products is hard—not the technology, the people.

---

**Input:**
> In today's fast-paced business environment, it's becoming increasingly important for organizations to leverage their core competencies while navigating the complex landscape of digital transformation.

**Output (crisp):**
> Companies need to use their strengths while going digital.

## Common AI Patterns to Eliminate

### Throat-Clearing Openers
- "Here's the thing:"
- "The uncomfortable truth is"
- "Let me be clear"
- "It turns out"

### Emphasis Crutches
- "Full stop."
- "Let that sink in."
- "Make no mistake"

### Binary Contrasts
- "Not because X. Because Y." → State Y directly
- "X isn't the problem. Y is." → "The problem is Y"

### Business Jargon
| Avoid | Use |
|-------|-----|
| Navigate challenges | Handle problems |
| Leverage | Use |
| Deep dive | Analysis |
| Game-changer | (cut or use specific claim) |

See `references/taboo-phrases.md` for the complete list.

## Scoring Rubric

| Criterion | Points | What It Measures |
|-----------|--------|------------------|
| Directness | 1-5 | No hedging or softening |
| Natural Rhythm | 1-5 | Sentence length variance |
| Concrete Verbs | 1-5 | Specific actions |
| Reader Trust | 1-5 | No over-explaining |
| Human Authenticity | 1-5 | No performative emphasis |
| Content Density | 1-5 | Substance over filler |
| Fact Preservation | 1-5 | All facts intact |
| Template Avoidance | 1-5 | No AI structures |

**Passing score: 32/40 (80%)**

## Reference Files

Located in this skill's directory:

| File | Purpose |
|------|---------|
| `references/taboo-phrases.md` | Comprehensive banned phrase list |
| `references/rubric.md` | Detailed scoring criteria |
| `references/edit-library.md` | Before/after examples |
| `references/fact-preservation.md` | Constraint rules |
| `presets/*.md` | Voice preset instructions |
| `scripts/*.py` | Validation scripts |
| `assets/examples/*.md` | Extended examples by content type |

## Maintenance Commands

| Command | Action |
|---------|--------|
| `/unslop --add-phrase "phrase"` | Add banned phrase |
| `/unslop --add-structure "pattern\|fix"` | Add structural pattern |
| `/unslop --list-phrases` | List all banned phrases |
| `/unslop --list-structures` | List structural patterns |

## Key Principles

1. **Diagnosis before writing** - Understand violations before fixing
2. **Facts are sacred** - Never sacrifice accuracy for style
3. **Presets guide, don't constrain** - Adapt to content
4. **When in doubt, cut** - Shorter is almost always better
5. **Validation is mandatory** - Run the scripts
