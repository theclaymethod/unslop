# unslop: Product Doctrine

Here live the product decisions that govern the repo. CLAUDE.md holds the
contribution rules; this file holds the why. When a change conflicts with this document,
one of the two is wrong, and deciding which requires a human.

## Identity and shape

unslop is an open-source tool packaged as an agent skill. The repo is the artifact. There
is no published package, and none is planned unless distribution truly requires it. Entry
points are plain scripts under `scripts/`, runnable by any host agent.

The host agent is the runtime. Linting runs when an agent invokes it during writing — not
as a pre-commit hook, not as a daemon, not as an editor extension. Integrations beyond the
agent are other people's projects.

The eval suite defines the product. Every behavior worth having is pinned by a row that
fails without it. This is constitutional, not aspirational: coverage gates make it
structurally impossible to add a detection pattern without eval rows, and the docs
themselves are gate-checked for drift.

## The axis

The product spans one axis. On the left sits removal: detect AI writing patterns and strip
them. On the right sits reconstruction: write the way a specific human writes. Product weight
sits roughly 70/30 toward the left.

The left end is deterministic, cheap, CI-friendly, and objectively benchmarkable. It is
the trust asset. The right end is generative and register-sensitive, and it operates under
the left end's constitution: every mimic or rewrite output must pass every removal gate. A
voice rewrite that reintroduces slop is a failure, full stop... which is itself a phrase
the scanner would flag, so: a failure, period. The gates apply to this document too.

## Bounds

- Refuse almost nothing. The tool removes AI-isms; it is not a taste arbiter. Literary
  prose is in bounds. Long documents are in bounds via chunking.
- English only. Non-English input gets a cheap detection and a clear decline — the one
  graceful refusal in the product.
- Mimicry accepts any writing style the user supplies samples for. There is no rights or
  attestation machinery; the sheet of samples is the only credential.

## Feature surface

**Always-on linting.** Deterministic scanners (phrase, structure, silhouette) are the
free, always-on layer. Model-based detection exists only for judge-only pattern families
and uses the cheapest capable model, per measured parity data rather than assumption.

**Co-writer mode.** On detection, findings surface to the user as structured suggestions
(span, severity, rationale, proposed replacement), never as silent rewrites. Hard findings
propose replacements; soft findings ask questions. Contract gates make "accept all" safe
by construction: replacements are span-minimal, scan clean, and preserve every constraint.

**Teach and mimic.** `teach` distills writing samples into a voice: a machine profile
(`profile.json`, the deterministic referee) and a layered voice card (`card.md` plus
situation sheets) that any generating model can follow in context. Teach is interactive
and coverage-driven — it classifies what the samples demonstrate and prompts for what is
missing. Dimensions with no sample evidence get no sheet and are listed as uncovered;
the card never fabricates. `mimic` writes with the card, scored against the profile, with
all removal gates blocking. An internal refine loop hill-climbs the card against held-out
samples, with a divergence guard against reward hacking.

**Harvest.** Cheap agents bootstrap the teach corpus from chat transcripts and designated
folders. Authorship separation is the product: assistant-authored text in a voice profile
would teach the exact register unslop removes. Deterministic parsing separates turns, a
scanner tripwire flags suspicious candidates, and nothing enters a profile without human
approval.

**Calibrate.** An A/B preference game gathers voice signal at tap-level effort. Pairs are
dimension-controlled minimal edits of the user's own passages, mostly produced by
deterministic transforms. Preferences aggregate per dimension with confidence bounds,
actively targeting the least-known dimension, and conflicts with sample-measured values
surface to the user rather than being silently resolved.

**Contribute.** A wild-caught AI-ism becomes an eval row built from the exact specimen,
verified red-first, and a structured PR into this repo. Redaction never alters the
specimen's tell, publication requires explicit user approval, and the pipeline runs fully
offline until the user says otherwise.

## Model tiering

Tiering is measured, not assumed; `evals/run_model_parity.py` re-measures it and
`references/pipeline.md` records the current table. The standing conclusions from the
2026-07-06 runs:

- Span-scoped replacement is safe on the cheapest tier. The gates carry the safety — the
  single bench failure was the most expensive model dropping a fact, caught by the
  preservation gate.
- Full rewrites of register-sensitive text erode hedges, absolutes, and legal negations
  on cheap tiers. That work belongs to frontier models, re-scanned afterward.
- Macro structure defeated every model tested. No model self-checks document shape from
  prose instructions; structure is always machine-detected and machine-gated.

Touching a model-dependent feature means re-running the parity evals across
both the GPT and Anthropic spectrums.

## Growth

Detection catalogs decay as generators evolve. Growth comes from adversarial refresh:
live bench outputs supply fresh specimens, contribute turns each specimen into a
red-first row, and coverage enforcement keeps every new pattern exercised. Yesterday's
miss becomes tomorrow's regression test, and nothing relies on anyone's good habits.
The agent-runnable procedure and its staleness signal live in `references/refresh.md`.
