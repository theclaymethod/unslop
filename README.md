# unslop

An agent skill for humanizing AI-generated content.

## What It Does

Removes predictable AI writing patterns from prose using two modes:

1. **Audit only**: Analyze input for AI-isms, severity, and context-dependent flags without rewriting
2. **Rewrite**: Diagnose, then rewrite following a preset voice while eliminating patterns

## Installation

### Using Skills CLI (Recommended)

Install to any supported coding agent using [npx skills](https://github.com/vercel-labs/skills):

```bash
# Install to Claude Code (global)
npx skills add theclaymethod/unslop -g -a claude-code

# Install to multiple agents
npx skills add theclaymethod/unslop -g -a claude-code -a cursor -a codex

# Install to all detected agents
npx skills add theclaymethod/unslop -g

# List available skills first
npx skills add theclaymethod/unslop --list
```

### Manual Installation

```bash
# Clone the repo
git clone https://github.com/theclaymethod/unslop.git ~/dev/unslop

# Symlink to Claude Code skills directory
ln -s ~/dev/unslop ~/.claude/skills/unslop

# Or symlink to commands (for /unslop invocation)
ln -s ~/dev/unslop/SKILL.md ~/.claude/commands/unslop.md
```

### Standalone Scripts

The Python validation scripts work independently:

```bash
# Extract constraints (facts that must survive)
python3 scripts/extract_constraints.py < input.txt

# Scan for AI-isms
python3 scripts/banned_phrase_scan.py < input.txt

# Scan including quoted examples and blockquotes
python3 scripts/banned_phrase_scan.py --include-quoted < input.txt

# Check readability metrics
python3 scripts/readability_metrics.py < input.txt

# Validate fact preservation
python3 scripts/validate_preservation.py original.txt transformed.txt

# Check change percentage
python3 scripts/diff_check.py original.txt transformed.txt

# Check Wikipedia for pattern updates
python3 scripts/wiki_sync.py check
```

## Usage

### Basic

```bash
/unslop "Here's the thing: building products is hard. Let that sink in."
```

Output:
```
Building products is hard.
```

### With Preset

```bash
/unslop --preset=warm "Your AI-generated text here"
```

Available presets:
- `crisp` (default) - Short, direct, no fluff
- `warm` - Friendly tone, conversational
- `expert` - Authoritative, confident claims
- `story` - Narrative flow, show don't tell

### Audit Only

```bash
/unslop --audit-only "Here's what's interesting: this deck is worth reading."
```

Returns flagged AI patterns and an assessment without rewriting the text.

### Strict Mode

```bash
/unslop --strict "Text to humanize"
```

Fails if rubric score < 32/40.

## What Gets Removed

### Throat-Clearing Openers
- "Here's the thing:"
- "The uncomfortable truth is"
- "Let me be clear"
- "It turns out"

### Emphasis Crutches
- "Full stop."
- "Let that sink in."
- "Make no mistake"

### Business Jargon
- "Navigate challenges" → "Handle problems"
- "Leverage" → "Use"
- "Deep dive" → "Analysis"
- "Game-changer" → (cut or use specific claim)

### Structural Patterns
- "Not because X. Because Y." → State Y directly
- "X. That's it. That's the thing." → Complete sentences
- Three-item lists → Vary list length

### Newer Pattern Families
- Reasoning-chain leakage → "Let me think step by step" / "Breaking this down"
- Reader-steering frames → "Here's what's interesting" / "Here's what stood out"
- Acknowledgment loops → "To answer your question" / "You're asking about"
- Novelty inflation → "A concept nobody's naming" / "The insight everyone's missing"
- False concessions & parenthetical hedging → "While X is promising, Y remains..." / "(and perhaps more importantly...)"
- Numbered-list inflation → "Three key takeaways" / "Five things to know"

See `references/taboo-phrases.md` for the complete list.

## Scoring Rubric

Eight criteria, 1-5 points each (40 max):

1. **Directness** - No hedging or softening
2. **Natural Rhythm** - Sentence length variance (8-25 words)
3. **Concrete Verbs** - Specific actions, not abstractions
4. **Reader Trust** - No over-explaining
5. **Human Authenticity** - No performative emphasis
6. **Content Density** - Substance over filler
7. **Fact Preservation** - All numbers, names, dates intact
8. **Template Avoidance** - No AI structural clichés

Passing score: 32/40 (80%)

## Project Structure

```
unslop/
├── SKILL.md                    # Main skill file (with YAML frontmatter)
├── README.md                   # This file
├── references/
│   ├── taboo-phrases.md       # Banned phrases and structural patterns, incl. quote exemptions
│   ├── rubric.md              # Scoring criteria
│   ├── edit-library.md        # 24 transformation examples
│   ├── fact-preservation.md   # What to preserve
│   └── personality-guide.md   # Voice and personality guidance
├── presets/
│   ├── crisp-human.md         # Short, direct
│   ├── warm-human.md          # Friendly, conversational
│   ├── expert-human.md        # Authoritative
│   └── story-lean.md          # Narrative
├── scripts/
│   ├── extract_constraints.py # Find must-preserve facts
│   ├── validate_preservation.py # Verify facts survived
│   ├── banned_phrase_scan.py  # Detect AI-isms (with severity levels and quote exemptions)
│   ├── readability_metrics.py # Grade level, variance
│   ├── diff_check.py          # Change percentage
│   └── wiki_sync.py           # Wikipedia source page sync
└── assets/
    └── examples/
        ├── before-after-article.md
        ├── before-after-linkedin.md
        └── before-after-sales.md
```

## Supported Agents

This skill follows the [Agent Skills specification](https://agentskills.io) and works with:

- Claude Code
- Cursor
- Codex
- OpenCode
- Cline
- Roo Code
- And [35+ other agents](https://github.com/vercel-labs/skills#supported-agents)

## Wikipedia Auto-Update

The rules in this skill are partially derived from Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) guide. The skill can sync itself with that page to pick up new patterns as Wikipedia editors add them.

```bash
# Tell the skill to check Wikipedia and update itself
/unslop --wiki-sync
```

This checks the Wikipedia page for changes, diffs against the last sync, and updates `taboo-phrases.md` and `banned_phrase_scan.py` with any new patterns. Wikipedia-specific patterns (broken wikitext, DOI issues, etc.) are skipped automatically.

### Manual usage

The underlying sync script can also be run directly:

```bash
python3 scripts/wiki_sync.py check   # Check for updates (exit 0 = no changes)
python3 scripts/wiki_sync.py diff    # Structured JSON diff
python3 scripts/wiki_sync.py prompt  # Claude Code integration prompt
```

State is stored in `scripts/.wiki_sync_state.json` (gitignored). First run treats all content as new.

## Maintenance

### Add a new banned phrase

```bash
/unslop --add-phrase "new AI-ism here"
```

### Add a new structural pattern

```bash
/unslop --add-structure "pattern|fix"
```

### Review current lists

```bash
/unslop --list-phrases
/unslop --list-structures
```

## Examples

See `assets/examples/` for comprehensive before/after transformations:

- **Articles**: Technical writing, thought leadership
- **LinkedIn**: Professional social posts
- **Sales**: Product launches, cold outreach, case studies

## Philosophy

AI-generated text follows predictable patterns that humans recognize. This skill doesn't just find-and-replace words—it restructures content to read like a human wrote it.

Key principles:
- **Cut ruthlessly**: If removal doesn't change meaning, remove it
- **Trust the reader**: They don't need "let that sink in"
- **Facts are sacred**: Numbers, names, dates survive unchanged
- **Structure matters**: Binary contrasts and three-item lists are tells
- **Quoted examples are exempt by default**: Tutorials and docs should not self-flag their own bad examples

## Requirements

- Python 3.8+
- Any supported coding agent

## License

MIT
