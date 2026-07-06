# Teach & Mimic

Reconstruction runs under detection's constitution: a mimic or refined output
that reintroduces slop is a failure. Every artifact here is deterministic and
testable; the model is used only to generate prose, never to score itself.

## Teach — building a voice

**The flow is agent-driven end to end.** The user should never create a
directory, convert a file, or type a command. On "teach my voice" (or any
trigger), the agent: (1) gathers samples — if none are offered, bootstrap via
`references/harvest.md` over the user's transcripts and writing folders, then
present ranked candidates with sources and flags for approval (`suspect_ai`
candidates get extra scrutiny; that human review is the contamination defense);
(2) creates `.unslop/voice/<name>/` and runs the steps below; (3) surfaces
`low_confidence` and Uncovered dimensions, prompting only for what the user's
writing will need; (4) closes with a scored demo mimic so the user sees the
loop work before trusting it.


`teach` distills a writer's samples into a reusable voice, stored under
`.unslop/voice/<name>/` (gitignored by default):

1. `scripts/voice_profile.py samples/ -o profile.json` — the machine
   fingerprint (char 3-grams, function-word delta, sentence-length EMD,
   punctuation, contractions, MTLD, word-length, impostor z-scores, GI rank).
   This is the referee the scorer uses.
2. `scripts/voice_card.py --profile profile.json --samples samples/ --out .
   --name <name>` — the **layered voice card** the generating model actually
   follows. `--name` labels the card (`# Voice card: <name>`); default `voice`.
   voice_card recomputes the profile from `--samples` and refuses (exit 2, named
   field) if the supplied `--profile` does not describe those samples, so a stale
   profile can never silently drive a card.
3. Add `--provenance` to write `provenance.json` (per-sample sha256, word
   counts, doc count, genre note, low-confidence flag) so a teach run is
   auditable.

**Sample files.** Both scripts read only `.txt` and `.md` files, recursively,
under the samples directory (nothing else — a directory of `.docx` or extensionless
files reads as empty and both scripts exit 2 with a diagnostic naming the
requirement). Convert samples to `.txt`/`.md` first.

**Sample requirements.** Use at least 5 documents, 2-3k words total, in the
**same genre** as the target. Fewer than ~2000 words or cross-genre samples set
`low_confidence` in the profile and provenance; the card still builds but its
claims are noisier. **Surface `low_confidence` to the user** — tell them the voice
is provisional and ask for more same-genre samples before trusting a mimic.
Cross-domain style attribution degrades sharply, so do not teach on blog posts
and score legal memos.

## The voice card (layered)

The card is a directory, not one file, so the generator loads only what the
current writing task needs:

- `card.md` — the always-loaded core, kept under 300 words: rhythm (median
  sentence length, IQR, burstiness), contraction habits with real examples,
  punctuation the writer uses and avoids, top sentence openers, a **Never**
  list of at/near-zero features, and an **index table** — "when writing X, read
  `card/X.md`".
- `card/<situation>.md` — one sheet per **covered** situation from the taxonomy
  (explaining-technical, anecdote, argument, disagreement, praise,
  hedging-uncertainty, numbers-data, addressing-reader, openings, closings).
  Each sheet gives how this author handles that situation, 1-3 verbatim sample
  snippets, and measured markers.

**No fabrication.** A dimension with no sample evidence gets **no sheet**; it is
named under "Uncovered" in `card.md`. The card never invents a voice the
samples cannot support.

**Coverage classification.** `voice_card.py --coverage` emits a deterministic
lexical coverage matrix over the taxonomy. It is intentionally coarse: it
DRIVES which sheets get written and which teach prompts to ask the user, and a
misclassified sentence can only add or drop a sheet — it can never change a card
claim, because claims come from measured facts and verbatim snippets. So
misclassification is low-stakes by construction. A sample set missing numeric
writing, for instance, leaves `numbers-data` uncovered and named as a gap.

**Coverage → prompt procedure.** When a dimension the target writing will need is
uncovered, ask the user for a short sample that exercises it. **Only ask for
dimensions the task requires** — do not fish for all ten. Templates:

| Dimension | Prompt to the user |
|-----------|--------------------|
| explaining-technical | "Share something you wrote that explains how a thing works or why it behaves the way it does." |
| anecdote | "Share a few sentences where you tell a small story about something that happened to you." |
| argument | "Share something you wrote that argues a position — a claim you defended." |
| disagreement | "Share something where you pushed back on or disagreed with an idea." |
| praise | "Share something where you praised or recommended something you liked." |
| hedging-uncertainty | "Share something where you were unsure and said so — thinking out loud." |
| numbers-data | "Share something you wrote that works with numbers, quantities, or measurements." |
| addressing-reader | "Share something written directly to a reader — instructions or a note to someone." |

`openings` and `closings` are structural (first/last sentence of every document)
and are covered as soon as there is one document, so they need no prompt.

The card is pack-sized (~1-2k tokens loaded) so it rides in the generation
context cheaply. Same inputs give byte-identical files.

## Mimic — writing with a voice

`mimic` is single-pass: put the relevant card sheets in context, draft or
rewrite, then run the output through **every** removal gate
(`banned_phrase_scan`, `structure_scan`, `validate_preservation`,
`readability_metrics`, `diff_check`). A mimic that scores well on voice but
trips a slop gate is rejected — voice never buys an exemption from the
constitution. Any samples the user supplies are fair game; there is no rights
or attestation machinery here.

## `--refine` — the internal hill-climb

`evals/run_mimic_refine.py` iterates when one pass is not enough. It is worth
the cost only when a single mimic keeps landing short of the target voice; most
users teach once and mimic cheaply thereafter.

Protocol (climb on A, accept on DEV, report on a sealed split):

- Split samples by document (seeded): **A** (~60%, retrieval/context pool) and
  **DEV** (~40%, acceptance). Fewer than 5 docs → refuse (exit 2).
- **LIVE (default):** each iteration assembles B prompts — the draft, the
  A-split voice card, the k=2 nearest-A samples by char-3gram cosine, and the
  current directives — and invokes `--generate-cmd` (default `claude -p`) once
  per beam, piping the prompt on stdin and reading the candidate on stdout.
  `--baseline zero|few|retrieval` selects which samples ride in the prompt (none
  / first-k / k nearest-A) and generates its candidate set through this same
  path, so the honest retrieval-few-shot competitor and the refine loop share
  one pipeline.
- **DRY-RUN:** pass `--candidates-dir DIR` and the loop reads
  `DIR/iter<i>/*.md` as that iteration's batch instead of generating them, so
  the loop logic runs with no model calls (this is how the MIMIC-* rows exercise
  it; the LIVE path is covered by a mock generator).
- **Hard gates** discard a candidate regardless of score: banned-phrase clean,
  structure clean, draft→candidate preservation, no copy-gate violation against
  A, and a 150-word floor.
- Survivors are scored against DEV (and recorded against A for the divergence
  guard) with the **full `voice_score` composite** — `0.5·(1−GI) + 0.5·` clipped
  weighted impostor-z distance against a same-genre impostor pool (`--impostors`,
  default the committed pool), seeded. This is deliberately NOT a raw weighted
  distance: a marker-stuffed candidate can minimize a raw distance and clear
  every hard gate yet be exposed by GI, so raw-distance acceptance would accept
  it over honest prose. The generator never scores itself.
- Accept an iteration only if the DEV composite improves by ≥ `min-delta`; the
  best-so-far never regresses.

### Stopping and the divergence guard

Earliest of: iteration cap, patience (N iterations without a DEV gain), or
**divergence** — the A composite improving while DEV worsens for two
consecutive iterations. Divergence is the reward-hacking signature (the model
is fitting the retrieval pool's topics, not the author's style); the loop halts
immediately and sets `reward_hacking_warning`.

### Directives and card refinement

Each iteration derives up to four ranked directives from the DEV metric deltas,
and each directive carries a proposed **card amendment** line. The best
candidate is copied to `OUT/final.md` and the amended card to
`OUT/voice-card.refined.md`.

## Scoring

The `voice_score` **composite** the refine loop accepts on is
`0.5·(1−GI) + 0.5·zsum` (lower = more author-like), where `GI` is the General
Impostors rank — the fraction of random feature-subset trials in which the
candidate beats every sampled impostor at looking like the profile — and `zsum`
is the clipped, weighted **impostor-z** distance (each per-feature distance
normalized by the impostor pool's mean/std, clipped to ±3, weighted by the WP10a
research weights). Both halves are calibrated against a same-genre **impostor
pool**, so the number rewards *beating plausible other authors*, not merely
matching aggregate surface stats. That is what defeats a marker-stuffed
candidate: it can drive a raw weighted distance down and still be far worse under
GI. Meaning preservation vs the original draft is a **separate** hard gate, never
blended into the composite. The composite is a **guide, not an oracle** — even
strong authorship verification tops out near a 93-94% ceiling, so treat
per-candidate deltas as the signal and under-claim.

## Baselines

Score refine output against paired baselines on the same drafts: zero-shot
("write like this person"), static few-shot, and **retrieval few-shot** (k
nearest-A samples — the honest competitor). Refine has to beat retrieval
few-shot to earn its cost.

## Statistics

`evals/mimic_stats.py` runs the small-n discipline: per-item paired deltas, a
BCa bootstrap CI (n=2000, seeded), and a sign-flip permutation test (exact for
≤12 items, else 20k seeded). Claim a win only when the CI lower bound > 0 **and**
p < 0.05. Anything degenerate (too few items, zero variance) reports
not-improved.

## Cost

| Step | Calls |
|------|-------|
| teach (profile + card) | free / deterministic |
| mimic | one strong generation call |
| refine | iterations × beam strong calls, plus free gate/score passes |

## Failure modes and the gate that catches each

| Failure | Symptom | Caught by |
|---------|---------|-----------|
| Topic bleed | importing what samples are *about*, not *how* they read | divergence guard (A improves, DEV worsens) |
| Verbatim copying | lifting sample phrasing | copy-gate (4-gram / LCS vs A) |
| Register lock | latching one sample's register | DEV composite vs held-out split |
| Reward hacking | self-assessed quality rising while DEV falls | divergence guard + `reward_hacking_warning` |
| Slop reintroduced | AI tells creep back into voiced prose | banned-phrase / structure gates |

For chunking long documents and the tiered execution architecture around these
steps, see `pipeline.md`.
