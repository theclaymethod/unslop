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

For every audit or rewrite, read [references/core-contract.md](references/core-contract.md).
It is the single behavior contract. Command files define routing and mechanics;
presets supply optional voice, but neither can override the core contract.

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

### Routing by phrase

Sub-flows are reachable by their natural names without being top-level verbs.
When the user says any of these, load the named file and jump to the flow:

| The user says | Go to |
|---------------|-------|
| `audit` / "just flag it" / "don't change anything" | [references/commands/cleanup.md](references/commands/cleanup.md#report-only) |
| `review` / "review this before I publish" | [references/commands/cleanup.md](references/commands/cleanup.md#report-only) |
| `harvest` / "what writing of mine do you have?" | [references/commands/teach.md](references/commands/teach.md#1-gather-samples-harvest) |
| `calibrate` / "the A/B game" / "quiz me on my voice" | [references/commands/teach.md](references/commands/teach.md#calibrate) |
| `refine` / "keep pushing until it sounds like me" | [references/commands/mimic.md](references/commands/mimic.md#refine) |
| voice check / "does this sound like me?" | [references/commands/mimic.md](references/commands/mimic.md#voice-check) |
| "found a new AI-ism" / "add this tell" | [references/commands/contribute.md](references/commands/contribute.md) |

## Interface

| Argument | Description | Default |
|----------|-------------|---------|
| `--preset` | Voice style: `crisp`, `warm`, `expert`, `story` | `crisp` |
| `--strict` | Fail if rubric score < 32/40 | false |
| `--report` | Flag AI patterns without changing the text (cleanup) | false |
| Input | Text to transform (argument, file path, or stdin) | required |

Read one preset from `presets/` before writing.

| Preset | Style | Best For |
|--------|-------|----------|
| `crisp` | Short, direct, no fluff | Technical writing, documentation |
| `warm` | Friendly, conversational | Emails, blog posts |
| `expert` | Authoritative, confident | Thought leadership, articles |
| `story` | Narrative flow, show don't tell | Case studies, personal posts |

Rewrite, preservation, register, and validation behavior lives only in
`references/core-contract.md`; do not recreate or override those rules here.

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

## Reference Files

| File | When to Read |
|------|-------------|
| `references/commands/*.md` | The routed command flows (rewrite, cleanup, teach, mimic, contribute). |
| `references/pipeline.md` | Orchestrated tiered execution for multi-agent harnesses. |
| `references/taboo-phrases.md` | Authoritative phrase catalog and scanner categories. |
| `references/fact-preservation.md` | Constraint preservation rules. |
| `references/rewrite-examples.md` | Executable before/after examples. |
| `references/{mimic,harvest,calibrate}.md` | Voice-tool internals loaded by their routed command. |
| `references/{rubric,edit-library,maintenance}.md` | Strict scoring, examples, and contribution procedures. |
| `presets/*.md` | Voice-specific deltas. |

## Maintenance

The eval contracts define the product. Add scanner examples eval-first in
`evals/fixtures/contracts/scanner-examples.json`; use
`evals/adversarial-evals.json` for agent behavior and routing. Do not edit legacy
`evals/evals.json`. New patterns need a false-negative example and a
false-positive protection example. Agent behavior changes need a `skill` row
and a regenerated shared benchmark. For the
concrete procedures (add a phrase or structure, list current patterns, sync with
Wikipedia's signs-of-AI-writing page), read `references/maintenance.md`. Found a
new AI-ism in the wild? `references/commands/contribute.md` turns the exact
snippet into a contract example and a structured PR, keeping both user-confirmation gates.
