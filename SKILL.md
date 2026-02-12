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
   - `references/personality-guide.md` - voice and personality guidance
   - `references/edit-library.md` - before/after transformation examples

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
2. **Replace all em-dashes** with periods, commas, or parentheses (zero em-dashes is the target)
3. **Follow preset voice** characteristics
4. **Preserve all constraints** (numbers, names, dates, URLs)
5. **Apply rubric criteria**:
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
> Building products is hard. Not the technology. The people.

---

**Input:**
> In today's fast-paced business environment, it's becoming increasingly important for organizations to leverage their core competencies while navigating the complex landscape of digital transformation.

**Output (crisp):**
> Companies need to use their strengths while going digital.

## Common AI Patterns to Eliminate

### Em-Dash Overuse (HIGH PRIORITY)
Em-dashes are the most reliable AI punctuation tell. Default to zero.
- Replace em-dashes with periods, commas, or parentheses
- Never allow multiple em-dashes per paragraph
- If one is absolutely necessary, max one per several paragraphs

### Throat-Clearing Openers
- "Here's the thing:" / "Here's why" / "Let's dive in" / "Let's unpack"
- "The uncomfortable truth is" / "It's no secret that"
- "Let me be clear" / "It turns out"

### Emphasis Crutches
- "Full stop." / "Let that sink in." / "Make no mistake"
- "Buckle up" / "Food for thought" / "It's a no-brainer"

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
| Delve | Explore, examine |
| Garner | Get, earn |
| Utilize | Use |
| Foster | Build, encourage |
| Resonate with | Matters to, connects with |

### Significance Inflation
- "stands as a testament to" → state the fact
- "pivotal moment" → be specific about what happened
- "rich tapestry" → never use
- "groundbreaking" → name the specific first
- "speaks volumes" / "sends a clear message" / "raises the bar" → just state the fact

### Promotional Language
- "nestled in the heart of" → give the actual address
- "boasts a" → "has a"
- "world-class" / "state-of-the-art" → describe specifically
- "a hidden gem" → cut
- "at the forefront of" → "leading"

### Superficial -ing Analyses
- ", highlighting..." / ", showcasing..." / ", underscoring..." → delete or give actual analysis in its own sentence

### Communication Artifacts
- "I hope this helps" / "Certainly!" / "Great question!" → cut (chatbot residue)

### Filler Setups
- "The key takeaway:" / "The bottom line:" / "It's clear that" → just state the point
- "At the intersection of" / "In an era of" → cut entirely
- "Pro tip:" / "Hot take:" / "Unpopular opinion:" → cut (meta-commentary)

### AI Vocabulary
- delve, garner, interplay, intricate, tapestry, underscore, multifaceted, paramount, burgeoning
- resonates, sheds light, strikes a balance, paints a picture, double-edged sword

See `references/taboo-phrases.md` for the complete list (~200 phrases across 24 categories).

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
| `references/taboo-phrases.md` | Banned phrases (~150 across 22 categories) |
| `references/rubric.md` | Detailed scoring criteria |
| `references/edit-library.md` | 24 before/after transformation examples |
| `references/fact-preservation.md` | Constraint rules |
| `references/personality-guide.md` | Voice and personality guidance |
| `presets/*.md` | Voice preset instructions |
| `scripts/banned_phrase_scan.py` | AI-ism detection (with severity levels) |
| `scripts/wiki_sync.py` | Wikipedia source page sync |
| `scripts/*.py` | Other validation scripts |
| `assets/examples/*.md` | Extended examples by content type |

## Maintenance Commands

| Command | Action |
|---------|--------|
| `/unslop --add-phrase "phrase"` | Add banned phrase |
| `/unslop --add-structure "pattern\|fix"` | Add structural pattern |
| `/unslop --list-phrases` | List all banned phrases |
| `/unslop --list-structures` | List structural patterns |
| `/unslop --wiki-sync` | Check Wikipedia for new AI patterns and self-update |

### Wiki Sync (`/unslop --wiki-sync`)

This command syncs the skill's pattern rules with Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) page. Run it periodically to pick up new patterns added by Wikipedia editors.

**Workflow — execute these steps in order:**

1. **Check for updates**:
   ```bash
   python3 <skill-path>/scripts/wiki_sync.py check
   ```
   If exit code is 0, report "No updates" and stop.

2. **Get structured diff**:
   ```bash
   python3 <skill-path>/scripts/wiki_sync.py diff
   ```
   Parse the JSON output. Each change has `type`, `section`, `words`.

3. **For each change with new words/phrases**, apply updates:
   - Read `references/taboo-phrases.md` — add new phrases to the matching section (use the section mapping in the diff output). Skip phrases that already exist.
   - Read `scripts/banned_phrase_scan.py` — add corresponding entries to `BANNED_PHRASES` dict with appropriate `category`, `severity` ("hard" for clear AI tells, "soft" for context-dependent), and `suggestion`.
   - If a change warrants a new before/after example, add it to `references/edit-library.md`.

4. **Verify**:
   ```bash
   python3 <skill-path>/scripts/banned_phrase_scan.py < /dev/null
   ```
   Confirm no syntax errors. Report what was added.

**Important**: Only add phrases that are genuine AI writing tells applicable to general prose. Skip Wikipedia-specific patterns (broken wikitext, DOI issues, category errors, etc.) that don't apply outside Wikipedia.

## Key Principles

1. **Diagnosis before writing** - Understand violations before fixing
2. **Facts are sacred** - Never sacrifice accuracy for style
3. **Presets guide, don't constrain** - Adapt to content
4. **When in doubt, cut** - Shorter is almost always better
5. **Validation is mandatory** - Run the scripts
