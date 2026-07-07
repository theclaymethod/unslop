---
name: unslop
description: Remove AI writing patterns from prose using either audit-only detection or a two-pass rewrite flow (diagnosis then reconstruction). Use this skill when editing, reviewing, or rewriting AI-generated content to make it sound human. Triggers on requests to "humanize", "de-slop", "fix AI text", "make it sound human", "remove AI patterns", or when reviewing text that contains obvious AI tells like "Here's the thing:", "Let that sink in", or "In today's fast-paced landscape". Also use when the user pastes text and says it "sounds like ChatGPT", "sounds robotic", "needs to sound more natural", or asks you to "clean up" drafted content before publishing.
license: MIT
user-invocable: true
argument-hint: "[teach · cleanup · rewrite · mimic] [input]"
metadata:
  author: claytonkim
  version: "2.3.0"
---

# Unslop

Humanize AI-generated prose. Audit first. Rewrite only when the user asks for a rewrite.

## Routing

**When the user invokes a sub-command (`/unslop teach ...`, `/unslop cleanup
...`), you MUST read `references/commands/<command>.md` before acting.
Non-optional — the command file defines the flow, and skipping it drops steps the
user expects.** A bare `/unslop <text>` with no leading command word defaults to
`rewrite`. If the first word does not match a command but the intent clearly maps
to one (e.g. "flag the AI tells, don't change anything" → `cleanup` report-only),
load that command file and proceed as if invoked.

| Command | Purpose | File |
|---------|---------|------|
| `rewrite` | Default two-pass de-slop: diagnose, reconstruct under the guards, validate. | [references/commands/rewrite.md](references/commands/rewrite.md) |
| `cleanup` | Co-writer: cheap detection, reviewable suggestions with contract gates; includes report-only "flag, change nothing". | [references/commands/cleanup.md](references/commands/cleanup.md) |
| `teach` | Agent-driven voice building: harvest, approve, profile, layered card, scored demo. | [references/commands/teach.md](references/commands/teach.md) |
| `mimic` | Voiced drafting or rewriting under the full gates; refine loop when one pass falls short. | [references/commands/mimic.md](references/commands/mimic.md) |
| _maintenance_ | Turn a wild AI-ism into an eval row and a PR (not a top-level verb). | [references/commands/contribute.md](references/commands/contribute.md) |

The shared doctrine below — register guards, validation gates and blocking
semantics, output formats, the script and reference tables — applies to every
command. The command files hold the flows; this file holds the constitution.

## When to Use

- User asks to humanize, de-slop, clean up, or make text sound natural.
- Drafts contain obvious AI tells: throat-clearing, scaffolded conclusions,
  inflated significance, em-dash abuse, or staccato fragment drama.
- User asks for an audit, scan, or review of prose before publishing.

## Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--preset` | Voice style: `crisp`, `warm`, `expert`, `story` | `crisp` |
| `--strict` | Fail if rubric score < 32/40 | false |
| `--report` | Flag AI patterns without changing the text (cleanup) | false |
| Input | Text to transform (argument, file path, or stdin) | required |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/voice_profile.py` | Build a deterministic stylometric voice profile from same-genre samples. |
| `scripts/voice_score.py` | Score a candidate against a voice profile with impostor-calibrated metrics and copy-gate reporting. |
| `scripts/voice_card.py` | Distill a profile plus samples into a layered, pack-sized voice card (core sheet plus per-situation sheets). |
| `evals/run_mimic_refine.py` | Iterative `--refine` hill-climb toward a voice under the removal gates, with A/DEV splits and a divergence guard. |
| `evals/mimic_stats.py` | Paired BCa-bootstrap and sign-flip stats for comparing mimic outputs to baselines. |

## Voice Presets

Read one preset from `presets/` before writing.

| Preset | Style | Best For |
|--------|-------|----------|
| `crisp` | Short, direct, no fluff | Technical writing, documentation |
| `warm` | Friendly, conversational | Emails, blog posts |
| `expert` | Authoritative, confident | Thought leadership, articles |
| `story` | Narrative flow, show don't tell | Case studies, personal posts |

## Rewrite Principles

- Cut throat-clearing and scaffolding. Start with the claim.
- Replace inflated importance with the concrete fact.
- Prefer short, direct sentences, but avoid telegraphic staccato.
- Use em-dashes sparingly. A single appositive dash can be fine; clusters are a
  tell. Never trade a dash for a comma splice; if a dash is wrong, use a period.
- Facts are sacred: numbers, names, dates, URLs, quotes, code identifiers, units,
  and scope words must survive.
- Do not invent first-person experience, anecdotes, or certainty the source does
  not support.
- Do not replace AI slop with anti-slop register: "Not X. Y.", forced punch
  endings, or runs of tiny fragments.

## Register Guards

Before removing a hedge or strengthening a sentence, check whether the register
requires it:

- Legal: keep hedges, negations, exceptions, section references, liability terms,
  and scope words.
- Medical/scientific: keep uncertainty, study limits, cohort limits, causation
  limits, and adverse-effect qualifiers.
- Security/safety: keep forceful absolutes such as "never", "must", "all input",
  and "do not" when they define a rule.
- Technical docs: keep precise terms, flags, API names, version numbers, file
  paths, and code semantics.

If a gate fails twice after rewrite, escalate model tier rather than adding more
prompt rules. The failure is execution quality.

## Validation

Run after every rewrite or voiced draft:

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
- Any `structure_scan.py` flag unless the actual genre justifies `--genre docs` or
  `--genre social`.
- Any `silhouette_scan.py` flag (`silhouette_penalty >= 1.0`) unless the genre
  justifies it: `--genre docs` retains the outline-following tell
  (`heading_preview`) because reference docs still should not read as a
  preview-then-fulfill template.
- Preservation warnings that show a dropped or changed negation, hedge, scope
  word, number, date, name, quote, URL, unit, or code identifier. The default
  gate warns without failing; run `validate_preservation.py --strict` for legal,
  medical, security, or scientific text so these exit non-zero.
- Staccato cadence in readability metrics.
- Rubric score below 32/40 in strict mode.

Validation scripts are necessary but not enough. Re-read negations, conditionals,
scope, certainty, and party relationships yourself.

## Output Format

For a quick rewrite, return the cleaned text only. For audit-only (cleanup
`--report`):

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
| `references/commands/*.md` | The routed command flows (rewrite, cleanup, teach, mimic, contribute). |
| `references/pipeline.md` | Orchestrated tiered execution for multi-agent harnesses. |
| `references/mimic.md` | Teach/mimic internals: card anatomy, scoring, baselines, the `--refine` loop. |
| `references/harvest.md` | Harvest adapter internals, contamination tripwire, privacy rules. |
| `references/calibrate.md` | The teach A/B calibration game: pairs, scoring, conflict surfacing. |
| `references/packs/*.md` | Small detector-agent rule packs. |
| `references/taboo-phrases.md` | Authoritative phrase catalog and scanner categories. |
| `references/fact-preservation.md` | Constraint preservation rules. |
| `references/rubric.md` | Strict scoring. |
| `references/edit-library.md` | Transformation examples when a pattern is unclear. |
| `references/personality-guide.md` | Adding genuine voice without fake personality. |
| `references/maintenance.md` | Pattern add/list procedures and Wikipedia sync. |
| `presets/*.md` | Voice-specific deltas. |
| `assets/examples/*.md` | Extended before/after examples by content type. |

## Maintenance

The eval suite defines the product. Add or change patterns eval-first in
`evals/adversarial-evals.json`; do not edit `evals/evals.json`. New scanner
patterns need one false-negative row and one false-positive protection row. Agent
behavior changes need a `skill` row and a regenerated shared benchmark. For the
concrete procedures (add a phrase or structure, list current patterns, sync with
Wikipedia's signs-of-AI-writing page), read `references/maintenance.md`. Found a
new AI-ism in the wild? `references/commands/contribute.md` turns the exact
snippet into an eval row and a structured PR, keeping both user-confirmation gates.
