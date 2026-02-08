# unslop

Remove AI writing patterns from prose. Two-pass system: diagnosis → reconstruction.

---

## Arguments

- `--preset`: Voice style (crisp | warm | expert | story). Default: crisp
- `--strict`: Fail if score < 32/40
- Input: Text to transform (direct argument, file path, or stdin)

## Maintenance Arguments

- `--add-phrase "phrase"`: Add a banned phrase to taboo-phrases.md
- `--add-structure "pattern|fix"`: Add a structural pattern to avoid
- `--list-phrases`: Show all banned phrases
- `--list-structures`: Show all structural patterns

---

## Workflow

### Pass 1: Diagnosis

Before rewriting, analyze the input:

1. **Read reference materials**:
   - `<skill-path>/references/taboo-phrases.md` - banned phrases and patterns
   - `<skill-path>/references/rubric.md` - 8 scoring criteria
   - `<skill-path>/references/fact-preservation.md` - what must survive

2. **Run constraint extraction**:
   ```bash
   python3 <skill-path>/scripts/extract_constraints.py <<< "$INPUT"
   ```
   Save output - these facts MUST survive transformation.

3. **Run banned phrase scan on original**:
   ```bash
   python3 <skill-path>/scripts/banned_phrase_scan.py <<< "$INPUT"
   ```
   Note all violations to address.

4. **Read selected preset**:
   - `<skill-path>/presets/crisp-human.md` (default)
   - `<skill-path>/presets/warm-human.md`
   - `<skill-path>/presets/expert-human.md`
   - `<skill-path>/presets/story-lean.md`

5. **Identify**:
   - Audience (technical, general, executive)
   - Content type (article, email, social, documentation)
   - Tone target from preset

### Pass 2: Reconstruction

Rewrite the text following these rules:

1. **Eliminate all AI-isms** from taboo-phrases.md
2. **Follow preset voice** characteristics
3. **Preserve all constraints** from extraction step
4. **Apply rubric criteria**:
   - Directness: No hedging, no throat-clearing
   - Natural rhythm: Vary sentence length (8-25 words)
   - Concrete verbs: Specific actions, not abstractions
   - Reader trust: No over-explaining
   - Human authenticity: No performative emphasis
   - Content density: Substance over filler
   - Fact preservation: All numbers, names, dates intact
   - Template avoidance: No AI structural clichés

### Pass 3: Validation

After rewriting, validate:

1. **Check fact preservation**:
   ```bash
   python3 <skill-path>/scripts/validate_preservation.py original.txt transformed.txt
   ```
   Must exit 0.

2. **Scan for remaining AI-isms**:
   ```bash
   python3 <skill-path>/scripts/banned_phrase_scan.py <<< "$OUTPUT"
   ```
   Must have zero violations.

3. **Check readability metrics**:
   ```bash
   python3 <skill-path>/scripts/readability_metrics.py <<< "$OUTPUT"
   ```
   Review flags for issues.

4. **Check change percentage**:
   ```bash
   python3 <skill-path>/scripts/diff_check.py original.txt transformed.txt
   ```
   Flag if >40% changed (may indicate over-editing).

5. **Score against rubric** (8 criteria, 1-5 each):
   - If `--strict` and score < 32/40, iterate

---

## Output Format

Return:

```
## Transformed Text

[The humanized version]

## Validation

- Constraints: [X]/[Y] preserved
- AI-isms: [N] remaining (list if any)
- Readability: Grade [X], variance [Y]
- Change: [X]% from original
- Score: [X]/40

## Changes Made

- [List of major transformations applied]
```

---

## Quick Examples

### Input
> Here's the thing: building products is hard. Not because the technology is complex. Because people are complex. Let that sink in.

### Output (crisp preset)
> Building products is hard—not the technology, the people.

### Input
> In today's fast-paced business environment, it's becoming increasingly important for organizations to leverage their core competencies while navigating the complex landscape of digital transformation.

### Output (crisp preset)
> Companies need to use their strengths while going digital.

---

## Reference File Locations

When this skill runs, these paths are relative to the skill installation directory:

- `references/taboo-phrases.md` - Comprehensive banned phrase list
- `references/rubric.md` - 8-criteria scoring system
- `references/edit-library.md` - Before/after transformation examples
- `references/fact-preservation.md` - Constraint preservation rules
- `presets/*.md` - Voice presets
- `scripts/*.py` - Validation scripts
- `assets/examples/*.md` - Extended examples by content type

---

## Maintenance Commands

### Add a banned phrase
When you discover a new AI-ism, add it:

```bash
/unslop --add-phrase "new phrase here"
```

This appends to `references/taboo-phrases.md` in the appropriate section.

### Add a structural pattern
When you identify a new AI structure pattern:

```bash
/unslop --add-structure "pattern description|suggested fix"
```

This appends to the structural patterns section of `references/taboo-phrases.md`.

### List current phrases
Review what's currently banned:

```bash
/unslop --list-phrases
```

### List current structures
Review structural patterns:

```bash
/unslop --list-structures
```

---

## Usage Notes

1. **First pass is read-only** - Diagnosis doesn't change anything
2. **All facts must survive** - Never sacrifice accuracy for style
3. **Presets are guides, not constraints** - Adapt to content
4. **When in doubt, cut** - Shorter is almost always better
5. **Validation is mandatory** - Don't skip the scripts
