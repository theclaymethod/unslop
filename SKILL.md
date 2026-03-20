---
name: unslop
description: Remove AI writing patterns from prose using a two-pass system (diagnosis then reconstruction). Use this skill when editing, reviewing, or rewriting AI-generated content to make it sound human. Triggers on requests to "humanize", "de-slop", "fix AI text", "make it sound human", "remove AI patterns", or when reviewing text that contains obvious AI tells like "Here's the thing:", "Let that sink in", or "In today's fast-paced landscape". Also use when the user pastes text and says it "sounds like ChatGPT", "sounds robotic", "needs to sound more natural", or asks you to "clean up" drafted content before publishing. Even if they don't use the word "slop", if the text has visible AI patterns, this skill applies.
license: MIT
metadata:
  author: claytonkim
  version: "2.0.0"
---

# Unslop

Humanize AI-generated prose. Two passes: diagnose what's wrong, then reconstruct without the tells.

## When to Use

- User asks to "humanize", "de-slop", or "make it sound human"
- Editing AI-generated drafts, emails, articles, social posts
- Text contains AI patterns (throat-clearing, binary contrasts, em-dash abuse, emphasis crutches)
- User says text "sounds like AI" or "sounds robotic"
- Reviewing content before publishing
- User pastes text and asks to "clean it up" or "make it natural"

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

Read the selected preset file from `presets/` (e.g., `presets/crisp-human.md`) before writing. Each preset has specific voice rules, structural patterns, and a quality checklist.

## Workflow

### Pass 1: Diagnosis

Before rewriting anything, understand what's wrong. This prevents blind rewriting that loses meaning.

1. **Read the relevant references** based on what you see in the input:
   - `references/taboo-phrases.md` — the complete catalog of ~200 banned phrases across 24 categories, with regex patterns for detection. This is the authoritative list; read it on first use and refer back for edge cases.
   - `references/rubric.md` — 8 scoring criteria (directness, rhythm, verbs, trust, authenticity, density, fact preservation, template avoidance), 5 points each.
   - `references/fact-preservation.md` — rules for what must survive transformation unchanged (numbers, names, dates, URLs, quotes, technical terms).

2. **Extract constraints** from the input — facts that must survive:
   ```bash
   python3 scripts/extract_constraints.py <<< "$INPUT"
   ```
   This outputs JSON with every number, date, name, URL, and quote that must appear in your output.

3. **Scan for AI patterns**:
   ```bash
   python3 scripts/banned_phrase_scan.py <<< "$INPUT"
   ```
   This returns violations grouped by category and severity (hard = always an AI tell, soft = context-dependent).

4. **Read the selected preset** from `presets/` and note its voice rules.

5. **Identify**: audience, content type, tone target. A LinkedIn post needs different treatment than a technical doc.

### Pass 2: Reconstruction

Rewrite the text. The references you read in Pass 1 are your guide — don't duplicate their rules here, just apply them.

Core principles (the why behind the rules):
- **Em-dashes are the #1 AI punctuation tell.** Default to zero. Use periods, commas, or parentheses instead. If one is absolutely necessary, max one per several paragraphs.
- **AI text delays the point.** Cut everything before the actual claim. "Here's the thing:" is throat-clearing. "Let that sink in." is an emphasis crutch. Just state the thing.
- **AI inflates significance.** "Stands as a testament to" means "is". "Pivotal moment" is almost never pivotal. Replace inflation with the specific fact.
- **AI avoids commitment.** "It's worth noting that" hedges. "Some experts argue" hides behind unnamed sources. Make claims directly or cite specifically.
- **Facts are sacred.** Every number, name, date, and URL from the original must appear in your output unchanged. Style is negotiable; accuracy is not.
- **Shorter is almost always better.** If cutting a sentence doesn't change the meaning, cut it. AI pads; humans compress.

Follow the preset voice characteristics for sentence length, paragraph structure, and tone. Refer to `references/edit-library.md` for 24 before/after transformation examples if you need guidance on specific pattern types.

For guidance on adding genuine human voice (not just removing AI tells), read `references/personality-guide.md`. Clean text that's still anonymous and voiceless scores a 3/5 on authenticity — aim for 4+.

### Validation

After rewriting, verify your work:

1. **Fact preservation** — confirm all constraints survived:
   ```bash
   python3 scripts/validate_preservation.py original.txt transformed.txt
   ```

2. **Remaining AI patterns** — check your output is clean:
   ```bash
   python3 scripts/banned_phrase_scan.py <<< "$OUTPUT"
   ```

3. **Readability metrics** — check rhythm and variance:
   ```bash
   python3 scripts/readability_metrics.py <<< "$OUTPUT"
   ```

4. **Change percentage** — flag if >40% changed (may indicate over-editing):
   ```bash
   python3 scripts/diff_check.py original.txt transformed.txt
   ```

5. **Score against rubric** — 8 criteria x 5 points = 40 max. Passing: 32/40 (80%). See `references/rubric.md` for detailed scoring.

## Output Format

Adapt output to the context. For a quick fix, just return the cleaned text. For a thorough review, include validation:

**Minimal** (default for short text / quick fixes):
```
[The humanized text]
```

**Detailed** (for `--strict` mode or when user asks for analysis):
```markdown
## Transformed Text

[The humanized version]

## Validation

- Constraints: [X]/[Y] preserved
- AI patterns: [N] remaining (was [M])
- Readability: Grade [X], sentence variance [Y]
- Change: [X]% from original
- Score: [X]/40

## Changes Made

- [List of major transformations applied]
```

## Quick Examples

**Input:**
> Here's the thing: building products is hard. Not because the technology is complex. Because people are complex. Let that sink in.

**Output (crisp):**
> Building products is hard. Not the technology. The people.

**Input:**
> In today's fast-paced business environment, it's becoming increasingly important for organizations to leverage their core competencies while navigating the complex landscape of digital transformation.

**Output (crisp):**
> Companies need to use their strengths while going digital.

## Reference Files

Located in this skill's directory. Read them as needed — don't front-load everything into context.

| File | When to Read |
|------|-------------|
| `references/taboo-phrases.md` | First use, then for edge cases. ~200 phrases across 24 categories with detection regex. |
| `references/rubric.md` | When scoring output or in `--strict` mode. 8 criteria, detailed rubrics. |
| `references/edit-library.md` | When unsure how to transform a specific pattern. 24 before/after examples. |
| `references/fact-preservation.md` | When input has lots of data, names, or quotes. Constraint rules. |
| `references/personality-guide.md` | When output is clean but soulless. How to add genuine voice. |
| `presets/*.md` | After preset selection. Voice-specific rules, patterns, checklists. |
| `assets/examples/*.md` | For extended before/after examples by content type (article, LinkedIn, sales). |

## Scripts

All scripts accept stdin or file path arguments and output JSON. Run from the skill directory.

| Script | Purpose | When to Run |
|--------|---------|-------------|
| `scripts/extract_constraints.py` | Extract must-preserve facts | Before rewriting |
| `scripts/banned_phrase_scan.py` | Detect AI patterns with severity | Before and after rewriting |
| `scripts/validate_preservation.py` | Verify facts survived | After rewriting |
| `scripts/readability_metrics.py` | Sentence variance, grade level | After rewriting |
| `scripts/diff_check.py` | Change percentage | After rewriting |
| `scripts/wiki_sync.py` | Sync with Wikipedia AI patterns | On `/unslop --wiki-sync` |

## Maintenance Commands

| Command | Action |
|---------|--------|
| `/unslop --add-phrase "phrase"` | Add banned phrase |
| `/unslop --add-structure "pattern\|fix"` | Add structural pattern |
| `/unslop --list-phrases` | List all banned phrases |
| `/unslop --list-structures` | List structural patterns |
| `/unslop --wiki-sync` | Sync with Wikipedia for new AI patterns |

### Wiki Sync (`/unslop --wiki-sync`)

Syncs pattern rules with Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) page. Run periodically to pick up new patterns.

**Steps:**

1. Check for updates: `python3 scripts/wiki_sync.py check` (exit 0 = no updates)
2. Get structured diff: `python3 scripts/wiki_sync.py diff` (JSON output with change type, section, words)
3. For each new word/phrase: add to `references/taboo-phrases.md` in the matching section, and add to `scripts/banned_phrase_scan.py` BANNED_PHRASES dict with category, severity, and suggestion.
4. Verify: `python3 scripts/banned_phrase_scan.py < /dev/null` (confirm no syntax errors)

Only add phrases that are genuine AI writing tells for general prose. Skip Wikipedia-specific patterns (broken wikitext, DOI issues, etc.).

## Key Principles

1. **Diagnosis before writing** — understand what's wrong before fixing
2. **Facts are sacred** — never sacrifice accuracy for style
3. **Presets guide, don't constrain** — adapt to content type
4. **When in doubt, cut** — shorter is almost always better
5. **Validation is mandatory** — run the scripts, especially fact preservation
