# unslop

An agent skill for humanizing AI-generated content.

## What It Does

Removes predictable AI writing patterns from prose at two levels: phrase-level tells ("delve", "it's worth noting", "stands as a testament") and document-level structure (uniform sentence rhythm, moralizing codas, bold-header listicles, connective paragraph scaffolds). Two modes:

1. **Audit only**: Analyze input for AI-isms, severity, and context-dependent flags without rewriting
2. **Rewrite**: Diagnose, then rewrite following a preset voice while eliminating patterns

It is equally deliberate about what it does *not* touch: literal domain usage (a horse harness, a load-bearing wall, financial leverage), load-bearing hedges and absolutes in legal, medical, security, and scientific text, and already-human writing that just needs to be left alone.

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

The Python validation scripts work independently (stdlib only, no dependencies):

```bash
# Extract constraints (facts that must survive)
python3 scripts/extract_constraints.py < input.txt

# Scan for phrase-level AI-isms
python3 scripts/banned_phrase_scan.py < input.txt

# Scan including quoted examples and blockquotes
python3 scripts/banned_phrase_scan.py --include-quoted < input.txt

# Scan for document-level structural tells (burstiness, codas, scaffolds)
python3 scripts/structure_scan.py < input.txt
python3 scripts/structure_scan.py --genre docs < README.md    # reference-doc carve-outs
python3 scripts/structure_scan.py --genre social < post.txt   # social-cadence carve-outs

# Check readability metrics
python3 scripts/readability_metrics.py < input.txt

# Validate fact preservation
python3 scripts/validate_preservation.py original.txt transformed.txt

# Strict mode: negation/scope/modality drift fails instead of warning
# (use for legal, medical, security, scientific text)
python3 scripts/validate_preservation.py --strict original.txt transformed.txt

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

### Business Jargon (collocation-gated)
- "Navigate challenges" → "Handle problems"
- "Leverage synergies" → "Use"
- "Deep dive" → "Analysis"
- "Game-changer" → (cut or use specific claim)

Gated words only flag in their jargon collocations. "Sailors navigate", "3:1 leverage", "a wedge into the kerf", and "Garner, North Carolina" all pass clean.

### Structural Patterns
- "Not because X. Because Y." → State Y directly
- "It's not the tooling. It's not the process. It's the culture." → State the point
- "Why does this matter? Because..." → Cut the self-Q&A
- "The result? A 40% drop." → "The result was a 40% drop."
- "Whether you're a seasoned developer or just starting out..." → Address the actual reader

### Macro Structure (document level)
- Uniform 15-18-word sentences everywhere → vary the rhythm
- "Ultimately, this reminds us that..." codas → just stop
- "However," / "Moreover," / "Furthermore," opening every paragraph → real topic sentences
- Bold-phrase-colon listicles standing in for prose
- One-line-paragraph LinkedIn staccato (outside social copy)

See `references/taboo-phrases.md` for the complete catalog.

## What Gets Protected

Do-no-harm is half the product:

- **Register guards**: "never store secrets", "may cause drowsiness", "does not establish causation", and "notwithstanding anything to the contrary" are content, not filler. The `--strict` preservation mode makes dropping them a hard failure.
- **Literal vocabulary**: construction, law, medicine, finance, sailing, code. Every contextual pattern ships with a false-positive eval row proving the literal sense survives.
- **Quoted examples are exempt by default**: tutorials and docs should not self-flag their own bad examples.
- **Facts**: numbers, names, dates, quotes, units, references (Section 12(b)), and "and/or" scope survive rewrites — with magnitude-aware checking, so "$47.3M" cannot silently become "$47.3 billion" and "150 km" cannot become "150 miles".
- **Genre**: bold-label lists are correct in reference docs (`--genre docs`); staccato cadence is correct in social copy (`--genre social`); Section-roadmap abstracts are academic convention, not repetition.

## The Eval Suite Defines the Product

Every pattern, guard, and script behavior exists as an eval row first. The suite is designed to be un-gameable:

- **182 deterministic cases** in `evals/adversarial-evals.json`, run by `python3 evals/run_adversarial.py`. Every detection carries a false-negative row (the tell gets caught), a false-positive row (the literal sense survives), and a recall row (gating didn't gut detection). Deleting a scanner pattern fails the build; marking a passing case `xfail` fails the build; the expected-xfail set is pinned to exactly one documented case.
- **33 behavioral cases** in `evals/shared-benchmark.json` (generated; never hand-edit), graded with an LLM judge *and* deterministic backstops: fact tokens that must survive, banned strings that must not appear, similarity floors for do-no-harm, and scanner exit codes on the output. Splits are `tune` / `holdout` / `holdback` (sealed).
- **12 machine-readable gates** via `python3 evals/run_adversarial.py --list-gates`, mirrored in `evals/CHECKS.md`. Even the docs are eval-gated: SKILL.md's examples must pass the skill's own scanners, the scanner and catalog are held in two-way parity, and the gate-matrix doc is pinned to the runner.

```bash
python3 evals/run_adversarial.py            # the deterministic suite
python3 evals/run_adversarial.py --only FP  # a category slice (parallelizes well)
evals/run_behavioral.sh tune                # the behavioral layer (needs claude -p)
```

See `evals/CHECKS.md` for the full gate matrix and the parallel check protocol, and `CLAUDE.md` / `AGENTS.md` for the eval-first contribution rules.

## Tiered Execution for Smaller Models

The skill works single-agent, but `references/pipeline.md` documents a cost-tiered path for orchestrating harnesses:

1. **Tier 0 (free)**: deterministic scripts run first — phrase scan, structure scan, constraint extraction.
2. **Tier 1 (cheap, parallel)**: small detector agents each get one compact rule-pack from `references/packs/` (~30 lines each: phrases, structure, register guards, voice, facts) and a chunk of text, and emit JSON findings. A small model with one narrow rulebook beats a small model with a 250-line monolith it will half-read.
3. **Tier 2 (one strong call)**: a single capable model rewrites with the merged findings handed to it.
4. **Tier 0 again**: every validation gate re-runs on the output; failures block.

Pack integrity (coverage of all scanner categories, size budgets, self-containment) is itself enforced by the eval suite via `scripts/check_packs.py`.

## Supported Agents

This skill follows the [Agent Skills specification](https://agentskills.io) and works with:

- Claude Code
- Cursor
- Codex
- OpenCode
- Cline
- Roo Code
- And [35+ other agents](https://github.com/vercel-labs/skills#supported-agents)

## Project Structure

```
unslop/
├── SKILL.md                    # Main skill file (single-agent path + pointers)
├── README.md                   # This file
├── references/
│   ├── taboo-phrases.md       # Authoritative pattern catalog (incl. macro structure)
│   ├── pipeline.md            # Tiered execution architecture
│   ├── packs/                 # Small detector rule-packs + manifest
│   ├── maintenance.md         # Add/list/wiki-sync procedures (eval-first)
│   ├── rubric.md              # Scoring criteria
│   ├── edit-library.md        # 24 transformation examples
│   ├── fact-preservation.md   # What to preserve
│   └── personality-guide.md   # Voice and personality guidance
├── presets/                   # crisp / warm / expert / story voice deltas
├── scripts/
│   ├── banned_phrase_scan.py  # Phrase-level detection (severity, quote exemptions)
│   ├── structure_scan.py      # Document-level detection (genre carve-outs)
│   ├── extract_constraints.py # Find must-preserve facts
│   ├── validate_preservation.py # Verify facts survived (--strict for regulated text)
│   ├── readability_metrics.py # Grade level, variance, staccato
│   ├── diff_check.py          # Change percentage
│   ├── check_packs.py         # Rule-pack integrity gate
│   └── wiki_sync.py           # Wikipedia source page sync
├── evals/
│   ├── adversarial-evals.json # Source of truth: 182 script + 33 skill cases
│   ├── run_adversarial.py     # Deterministic runner (--only, --case, --list-gates)
│   ├── run_behavioral.sh      # One-command behavioral run
│   ├── build_shared_benchmark.py # Generates shared-benchmark.json
│   ├── CHECKS.md              # Machine-readable gate matrix + parallel protocol
│   └── check_*.py             # Parity, doc, example, and pack gates
└── assets/
    └── examples/              # Before/after sets: article, LinkedIn, sales
```

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

## Wikipedia Auto-Update

The rules in this skill are partially derived from Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) guide. The skill can sync itself with that page to pick up new patterns as Wikipedia editors add them.

```bash
# Tell the skill to check Wikipedia and update itself
/unslop --wiki-sync
```

This checks the Wikipedia page for changes, diffs against the last sync, and updates `taboo-phrases.md` and `banned_phrase_scan.py` with any new patterns — eval rows first, per `references/maintenance.md`. Wikipedia-specific patterns (broken wikitext, DOI issues, etc.) are skipped automatically.

State is stored in `scripts/.wiki_sync_state.json` (gitignored). First run treats all content as new.

## Maintenance

All maintenance is eval-first: the row lands red in `evals/adversarial-evals.json` before any scanner or catalog edit makes it green. `references/maintenance.md` has the full procedures for:

- Adding a banned phrase (`--add-phrase`) — needs a false-negative row plus a literal-use protection row
- Adding a structural pattern (`--add-structure`)
- Listing current phrases and patterns
- Wikipedia sync

## Examples

See `assets/examples/` for extended before/after transformations:

- **Articles**: Technical writing, thought leadership
- **LinkedIn**: Professional social posts
- **Sales**: Product launches, cold outreach, case studies

## Philosophy

AI-generated text follows predictable patterns that humans recognize. This skill doesn't just find-and-replace words—it restructures content to read like a human wrote it, and it refuses to "fix" writing that was never broken.

Key principles:
- **Cut ruthlessly**: If removal doesn't change meaning, remove it
- **Trust the reader**: They don't need "let that sink in"
- **Facts are sacred**: Numbers, names, dates, negations, and scope survive unchanged
- **Structure matters**: Binary contrasts, self-Q&A, uniform rhythm, and moralizing codas are tells
- **Do no harm**: Register hedges, literal vocabulary, and human writing stay intact
- **Quoted examples are exempt by default**: Tutorials and docs should not self-flag their own bad examples
- **The eval suite defines the product**: If a behavior matters, there is a row that fails without it

## Requirements

- Python 3.8+
- Any supported coding agent

## License

MIT
