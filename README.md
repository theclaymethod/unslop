# unslop

unslop strips the patterns that make writing read as machine-written, then rebuilds the prose
in a real human voice. It ships as an agent skill, and the host agent runs it while you write,
backed by deterministic scanners that any tool can call on its own.

Four commands cover the whole surface:

- `/unslop teach` builds a reusable voice from your own writing samples.
- `/unslop cleanup` flags AI tells as reviewable suggestions and changes nothing on its own.
- `/unslop rewrite` diagnoses a draft and rebuilds it under the guards (the default).
- `/unslop mimic` drafts or rewrites in a taught voice, then clears every removal gate.

Detection carries the weight, and it's cheap, deterministic, and benchmarkable, which is what
makes it the trust asset. Voice work is generative, and it runs under detection's constitution,
so any mimic or rewrite that reintroduces a tell fails, however well it matches the voice.

## Installation

### Using the Skills CLI (recommended)

Install to any supported coding agent with [npx skills](https://github.com/vercel-labs/skills):

```bash
# Install to Claude Code (global)
npx skills add theclaymethod/unslop -g -a claude-code

# Install to several agents at once
npx skills add theclaymethod/unslop -g -a claude-code -a cursor -a codex

# Install to every detected agent
npx skills add theclaymethod/unslop -g

# List available skills first
npx skills add theclaymethod/unslop --list
```

### Manual installation

```bash
git clone https://github.com/theclaymethod/unslop.git ~/dev/unslop
ln -s ~/dev/unslop ~/.claude/skills/unslop
# Or wire it as a slash command:
ln -s ~/dev/unslop/SKILL.md ~/.claude/commands/unslop.md
```

The Python scripts under `scripts/` run on their own, with no third-party dependencies, just
Python 3.8+ and the standard library. Call them from CI, a pre-publish check, or another agent,
and you never load the skill at all.

## Three Detection Layers

Detection stacks three deterministic scanners, coarse to fine. Each one returns JSON and exits
non-zero on a flag, and each carries false-positive protection rows, so a literal or domain use
never trips it.

**Phrase layer** (`scripts/banned_phrase_scan.py`). 313 banned phrases and vocabulary items,
each tagged `hard` (always a tell) or `soft` (context-dependent). Gated words fire only in
their jargon collocations. Sailors navigate, a `3:1 leverage` ratio holds, a `wedge` seats in
the kerf, and `Garner, North Carolina` stays on the map, while the same words inside
`"navigate challenges"` or `"leverage synergies"` get caught. Quoted spans, blockquotes, and
code fences get masked first, so a tutorial documenting bad writing never flags its own examples.

**Structure layer** (`scripts/structure_scan.py`). 77 structural patterns plus document-level
metrics: `sentence_burstiness`, `paragraph_cv`, `triad_density`, `bold_colon_listicle_count`,
`one_line_staccato_share`, `connective_paragraph_openers`, `signpost_density`,
`opener_unique_ratio`, `top_opener_share`, `max_consecutive_opener`,
`participial_closer_share`, `conclusion_coda`, and `summary_sandwich`. This layer catches the
rhythm tells, the uniform sentence length and the staccato runs, the moralizing codas, the
connective scaffolds that open every paragraph with `"However,"` or `"Moreover,"`, and the
bold-label listicles that stand in for prose. Genre carve-outs keep it honest, so `--genre docs`
allows the bold-label lists that reference docs really use, and `--genre social` allows the
short-line cadence that belongs in social copy.

**Silhouette layer** (`scripts/silhouette_scan.py`). This one sits a level above the surface and
scores how the ideas are arranged. It catches outline-following, recap loops, and paragraph-role
templating: body paragraphs that open on a discourse cue instead of their own claim
(`scaffold_opener_share`), opening vocabulary that disappears mid-document and returns at the
end (`callback_content`, the strongest single tell), cue-opener roles rotating like a template
(`role_entropy_bits`), intro content words reappearing as body-paragraph heads
(`preview_fulfillment`), and section headings that restate the intro's outline
(`heading_preview`). The composite `silhouette_penalty` flags at `1.0` against a committed
human reference. On the corpus in the repo it separates cleanly, with 12 of 12 AI documents
flagged and 0 of 8 human documents flagged. A cue-deletion attack collapses the scaffold metric,
so silhouette gets scored jointly with the structure scanner, as a lower fence.

## The Gamut: What Gets Removed

Every family below is cataloged in `references/taboo-phrases.md` and pinned by an eval row.
Severity is `hard` (always a tell) or `soft` (a default register guard your real voice can
override). The idea throughout is contextual gating over blunt word bans, and a pattern ships
only once a false-positive row proves the literal sense survives.

### Openers, emphasis, and inflation

| Family | Caught examples |
|--------|-----------------|
| Throat-clearing openers | `"Here's the thing:"`, `"The uncomfortable truth is"`, `"Let me be clear"`, `"It turns out"`, `"Let's dive in"`, `"Let's unpack"` |
| Emphasis crutches | `"Full stop."`, `"Let that sink in."`, `"Make no mistake"`, `"Read that again."`, `"This cannot be overstated."` |
| The "X is real" closer | `"The struggle is real."`, `"The stakes are real."` (spares the literal "is it genuine?" sense) |
| Significance inflation | `"stands as a testament to"`, `"pivotal moment"`, `"enduring legacy"`, `"rich tapestry"`, `"cornerstone of"`, `"holds great promise"` |
| False agency | `"the numbers speak for themselves"`, `"the data tells a story"`, `"paints a clear picture"` |

### Contrast, questions, and drama

| Family | Caught examples |
|--------|-----------------|
| Negative parallelism | `"It's not X, it's Y"`, `"Not only... but also"`, `"Not merely X, but Y"`, `"No X, no Y, just Z"` |
| Contrastive definitions | `"X isn't a Y, it's a Z"` (spares real corrections like `"Use pnpm, not npm."` and `"The painting is real, not a forgery."`) |
| Wh-opener self-Q&A | `"Why does this matter? Because..."`, `"What does this mean for..."`, `"Why should you care?"` |
| Cliffhanger fragments | `"[Noun]. That's it. That's the [thing]."`, `"The ___ loop."` as a standalone, `"X things. One thing."` |
| Hedge stacks | `"(and perhaps more importantly, ...)"`, `"(arguably ...)"`, `"While X is promising, Y remains a challenge"` |

### Attribution, flattery, and jargon

| Family | Caught examples |
|--------|-----------------|
| Vague attribution | `"Experts argue"`, `"Studies show"`, `"Some critics"`, and bare clause-initial `"Research indicates"` (attributed and possessive forms stay clean) |
| Reader-addressing flattery | `"Here's what's interesting"`, `"worth reading"`, `"worth your time"`, `"Whether you're a seasoned developer or just starting out"` |
| Business-jargon collocations | `"navigate challenges"`, `"leverage synergies"`, `"deep dive"`, `"circle back"`, `"move the needle"`, `"low-hanging fruit"` |
| Marketing and headline cadence | `"world-class"`, `"state-of-the-art"`, `"a hidden gem"`, two-beat imperative slogans (`"Emit 1,100 tokens. Ship 237KB."`), and headline slogan cadence firing at three or more short-line headers in one document |

### Chatbot residue and punctuation

| Family | Caught examples |
|--------|-----------------|
| Chatbot artifacts | `"I hope this helps"`, `"Certainly!"`, `"Great question!"`, `"as an AI language model"`, `"as of my knowledge cutoff"` |
| Emoji section headers | Decorative emoji standing in as headings, flagged as a formatting tell |
| Em-dash overuse | The single most reliable punctuation tell. Default is zero; two or more in one paragraph is always a hard flag |
| Reasoning-chain leaks | `"Let me think step by step"`, `"Breaking this down"`, `"Here's my thought process"` |

### Structural and silhouette families

The structure scanner adds the document-shape tells: uniform sentence rhythm, staccato
one-line-paragraph runs outside social copy, connective paragraph scaffolds, signpost density,
and moralizing codas like `"Ultimately, this reminds us that..."`. The silhouette scanner adds
the arrangement tells above. A handful of macro tells stay agent judgment instead of
scanner-enforced (both-sidesism, templated redemption arcs, over-determination, uniform
emotional register), because a scanner can't reliably tell a genuine opposing view from a
manufactured one.

## What Gets Protected

Do-no-harm is half the product. The scanners leave the following alone, and each guard has its
own eval row.

- **Register guards.** `"never store secrets"`, `"may cause drowsiness"`,
  `"does not establish causation"`, and `"notwithstanding anything to the contrary"` are
  content, not filler. In legal, medical, security, and scientific text, these hedges,
  negations, absolutes, and scope words carry meaning. `validate_preservation.py --strict`
  turns dropping one into a hard failure.
- **Literal domain usage.** Construction, mechanics, law, medicine, finance, sailing, and
  code all use the gated words literally. Every contextual pattern ships with a false-positive
  row proving the literal sense stays clean.
- **Quoted examples.** Spans in quotes, blockquotes, and code fences are exempt by default, so
  documentation never self-flags the bad writing it's teaching.
- **Facts, with magnitude awareness.** Numbers, names, dates, quotes, units, references like
  `Section 12(b)`, and `and/or` scope survive a rewrite. Magnitude-aware checking means
  `$47.3M` can't silently become `$47.3 billion`, and `150 km` can't become `150 miles`.
- **Genre carve-outs.** Bold-label lists are correct in reference docs, staccato is correct in
  social copy, and a section-roadmap abstract is academic convention rather than a tell.
- **English only.** Non-English input gets cheap detection and a clear decline. That's the one
  graceful refusal in the product, and the scanners return `non_english: true` and stop.

## Voice: teach and mimic

The right end of the axis writes the way a specific person writes. It's agent-driven end to
end, and you supply approvals and answers, never a directory or a command.

### teach

`teach` distills your samples into two artifacts under `.unslop/voice/<name>/` (gitignored):
a machine profile (`profile.json`, the deterministic referee) and a layered voice card
(`card.md` plus per-situation sheets) that any generating model follows in context.

1. **Harvest.** Cheap agents bootstrap the corpus from your chat transcripts and writing
   folders. Adapters read both Claude Code (`claude-jsonl`) and Codex CLI/Desktop
   (`codex-jsonl`) sessions, auto-detected by shape. The contamination guarantee is the whole
   point, because assistant-authored text in a voice profile would teach the exact register
   unslop removes. So the adapters drop assistant and developer turns, strip injected content
   like a
   dumped `AGENTS.md`, and run every kept candidate through the scanners. A hard hit or two
   scanner categories marks a sample `suspect_ai`, ranked last and never auto-approved. Nothing
   reaches a profile without your approval.
2. **Profile and card.** `voice_profile.py` computes the stylometric fingerprint (character
   3-grams, function-word deltas, sentence-length distribution, punctuation, contractions,
   MTLD, impostor z-scores, GI rank). `voice_card.py` writes the layered card the generator
   reads. The card never fabricates, so a dimension with no sample evidence gets no sheet, and
   it's named under "Uncovered" instead. A profile that doesn't describe the supplied samples
   gets rejected (exit 2), so a stale profile can never drive a card.
3. **Calibrate.** When samples run thin, an A/B preference game gathers voice signal at
   tap-level effort. The pairs are dimension-controlled minimal edits of your own passages,
   mostly from deterministic transforms, so each pair keeps the passage's facts. Preferences
   aggregate per dimension with confidence bounds, and the game targets the least-known
   dimension next, while a stated preference that contradicts a sample-measured value surfaces
   to you as a named conflict, never resolved silently. Voice beats the default register guard,
   but only in the open.
4. **Scored demo.** teach closes by mimicking one paragraph, scoring it, and running the
   scanners in front of you. A voiced demo that trips a slop gate fails the loop.

### mimic

`mimic` drafts or rewrites in the taught voice, then clears the full gate battery. The rule is
absolute, so a mimic that scores well on voice but trips a removal gate gets rejected. Voice never
buys an exemption from the constitution, and meaning preservation against the original draft
is its own separate hard gate.

- **Voice check** answers "does this sound like me?" with a score and no rewrite. It reports
  the composite (lower is more you), the General Impostors rank, and the two or three metric
  deltas that explain the score in plain words. It's the cheapest voice interaction and the
  usual one after teach. Check drafts often, commission rewrites rarely.
- **Refine** hill-climbs when a single pass keeps landing short. It splits samples into a
  retrieval pool and a held-out acceptance split, generates candidates, and discards any that
  trip a hard gate (banned-phrase, structure, draft-to-candidate preservation, a copy-gate
  against the pool, and a word floor). Survivors get scored on the held-out split with a
  gaming-resistant composite: `0.5·(1−GI) + 0.5·` a clipped impostor-z distance against a
  same-genre impostor pool. A marker-stuffed candidate can drive a raw distance down and still
  lose under the General Impostors rank, and that's what stops it from beating honest prose. A
  **divergence guard** halts the loop and raises `reward_hacking_warning` when the pool score
  improves while the held-out score worsens for two iterations. Claim a win only when
  `mimic_stats.py` shows the confidence-interval lower bound above zero and p below 0.05.

## Co-writer: cleanup

`cleanup` is the co-writer mode. On detection it surfaces findings as structured suggestions,
never a silent rewrite. Each suggestion carries a span, severity, category, rationale, and
proposed replacement. Detection is cheap and deterministic, and replacement generation is
delegated to a stronger model, which fills in the null replacements the scanner leaves.

Hard findings become direct replacements. Soft findings are register-dependent, so their
rationale is phrased as a question rather than an edit. Four contract gates in
`check_suggestions.py` make "accept all" safe by construction:

- **span-minimality**: an edit changes only its own span, and a whole-sentence rewrite fails.
- **replacement-scanner**: each replacement passes both scanners in isolation and adds no new
  violation in context.
- **accept-all**: applying every suggestion yields a document that passes both scanners and
  preserves every constraint against the original.
- **span-overlap**: spans may not overlap.

A report-only variant ("flag it, change nothing") runs the scanners and reports each issue by
span, category, and severity, separating clear problems from judgment calls.

## Contribute: the growth flywheel

Detection catalogs decay as generators evolve. Growth comes from adversarial refresh, where a
wild specimen becomes an eval row becomes a structured PR. `/unslop contribute` runs the
pipeline offline until you approve publication.

1. **Precheck** tells you whether the tell is already covered.
2. **Confirmation gate one** shows you the exact snippet and asks whether it may go public,
   with redaction hints that keep the tell byte-for-byte intact.
3. **Scaffold and implement eval-first.** The false-negative row lands red before the scanner
   changes, and a literal-use false-positive row lands beside it. The scanner and catalog then
   change until the row goes green while the protection row holds.
4. **Verify** captures the red-to-green transition and refuses TODO markers.
5. **Full gate battery**, then **confirmation gate two** on the final PR body. Only then does
   the host agent branch, commit, and open the PR. The scripts never touch the network.

Yesterday's miss becomes tomorrow's regression test, and nothing rides on good habits.

Caught a specimen but working outside an agent? [CONTRIBUTING.md](CONTRIBUTING.md) links the
fast path and the manual path.

## The Eval Suite Is the Product

Every behavior worth having is pinned by a row that fails without it. The suite is
constitutional, and it's built to resist gaming.

- **440 deterministic script cases (439 pass, 1 documented xfail)** in `evals/adversarial-evals.json`, run by
  `python3 evals/run_adversarial.py`. Each detection carries a false-negative row (the tell
  gets caught), a false-positive row (the literal sense survives), and a recall row (gating
  didn't gut detection).
- **24 machine-readable gates** via `python3 evals/run_adversarial.py --list-gates`, mirrored
  in `evals/CHECKS.md`. They cover the scanners, the harvest/contribute/calibrate suites, the
  voice scorer, pack structure, silhouette separation, and the docs themselves.
- **Mutation-proof by construction.** Deleting a scanner pattern fails the coverage gate.
  Marking a passing case `xfail` fails the build. The one documented XFAIL is pinned to exactly
  one case: `FP-06`, where the literal `"delve into the mountain"` collides with the strong
  `"delve into the topic"` tell, an accepted residual a pattern regex can't disambiguate. Even
  the docs get gate-checked, so SKILL.md's own examples must pass its scanners, the scanner and
  catalog are held in two-way parity, and a kata proves the add-a-pattern loop still works.
- **Behavioral layer.** `evals/shared-benchmark.json` is generated (never hand-edited) from the
  `skill` rows, with `with_skill` and `without_skill` variants graded by an LLM judge plus
  deterministic backstops: facts that must survive, banned strings that must not appear,
  similarity floors for do-no-harm. Its 33 cases split `tune` (17) for shaping, `holdout` (12)
  for reporting, and `holdback` (4) sealed until final confirmation.
- **Interpreting the lift.** The base model already de-slops well, so judge-blended lift runs
  near zero and per-case deltas carry the signal. On the recorded 2026-07-06 holdout run, the
  deterministic backstops show +4.2 points objective lift (0.917 vs 0.875 across 12 held-out
  cases, see `evals/TUNE-RESULTS.md`), while the judge can't tell the prose apart, so the
  measurable value lives in preserved facts, register, and structure. The recorded tune run also
  preserved a legal hedge the baseline dropped, and it exposed a do-no-harm regression the
  guards were then hardened against.

```bash
python3 evals/run_adversarial.py            # the deterministic suite (439 pass, 1 xfail)
python3 evals/run_adversarial.py --only FP  # one category slice, parallelizes well
evals/run_behavioral.sh tune                # the behavioral layer (needs claude -p)
```

## Model Tiering Is Measured

Where the pipeline depends on a model, `evals/run_model_parity.py` measures whether a cheap
tier is safe rather than assuming it. The live matrix was recorded **2026-07-06** across both
the Anthropic and GPT spectrums.

**Span replacement clears on the cheapest tier.** On the mechanical span-minimal contract,
`claude-haiku`, `claude-sonnet`, `gpt-5.4-mini`, and `gpt-5.5` all scored 8/8, and `claude-opus`
scored 7/8, its one miss a dropped `8:30` caught by the preservation gate rather than by model
choice. The gates carry safety, the tier doesn't.

**Full rewrites of register-sensitive text belong to frontier models.** On eight
register/structure cases the ladder was 7/8 (opus, gpt-5.4-mini), 6/8 (sonnet, gpt-5.5), and
5/8 (haiku, gpt-5.4-nano), and the cheap-tier misses softened absolutes, dropped hedges, and
eroded a legal negation.

**Macro structure defeated every model tested.** The `MACRO-01` case failed for all six,
opus included, and each one kept a conclusion coda the prose instruction told it to drop. No
model self-checks document shape from prose, so structure is always machine-detected and
machine-gated. `references/pipeline.md` records the full tables.

## Standalone Scripts

The scripts run independently, standard library only. A quick tour:

```bash
# Phrase, structure, and silhouette scans
python3 scripts/banned_phrase_scan.py < input.txt
python3 scripts/banned_phrase_scan.py --include-quoted < input.txt   # audit quoted examples too
python3 scripts/structure_scan.py < input.txt
python3 scripts/structure_scan.py --genre docs < README.md           # reference-doc carve-outs
python3 scripts/silhouette_scan.py < input.txt                       # idea-arrangement tells

# Facts and preservation
python3 scripts/extract_constraints.py < input.txt
python3 scripts/validate_preservation.py original.txt transformed.txt
python3 scripts/validate_preservation.py --strict original.txt transformed.txt  # regulated text
python3 scripts/diff_check.py original.txt transformed.txt
python3 scripts/readability_metrics.py < input.txt

# Co-writer suggestions
python3 scripts/suggest.py document.md
python3 scripts/check_suggestions.py suggestions.json                # the four contract gates

# Voice
python3 scripts/harvest_samples.py SOURCE -o candidates.json         # bootstrap from transcripts
python3 scripts/voice_profile.py samples/ -o profile.json            # stylometric fingerprint
python3 scripts/voice_card.py --profile profile.json --samples samples/ --out . --name me
python3 scripts/voice_score.py --profile profile.json candidate.md   # "does this sound like me?"
python3 scripts/calibrate_pairs.py generate --base passage.txt --dimension em_dash --seed 1
python3 scripts/wiki_sync.py check                                   # sync the phrase catalog
```

## Project Structure

```
unslop/
├── SKILL.md                       # Four-verb router and shared doctrine
├── README.md                      # This file
├── references/
│   ├── commands/                  # The routed flows: teach, cleanup, rewrite, mimic, contribute
│   ├── taboo-phrases.md           # Authoritative pattern catalog (all families)
│   ├── mimic.md                   # Teach/mimic internals: card anatomy, scoring, refine
│   ├── harvest.md                 # Adapter internals and the contamination tripwire
│   ├── calibrate.md               # The A/B preference game
│   ├── pipeline.md                # Tiered execution and the measured model-parity tables
│   ├── fact-preservation.md       # Constraint preservation rules
│   ├── rubric.md                  # Strict scoring criteria
│   ├── edit-library.md            # Transformation examples
│   ├── personality-guide.md       # Adding voice without fake personality
│   ├── maintenance.md             # Add/list/wiki-sync procedures (eval-first)
│   └── packs/                     # Small detector rule-packs plus manifest
├── presets/                       # crisp / warm / expert / story voice deltas
├── scripts/                       # Scanners, voice tools, preservation, suggest, harvest
├── evals/
│   ├── adversarial-evals.json     # Source of truth: 440 script cases
│   ├── run_adversarial.py         # Deterministic runner (--only, --case, --list-gates)
│   ├── shared-benchmark.json      # Generated behavioral manifest (never hand-edit)
│   ├── build_shared_benchmark.py  # Regenerates the behavioral manifest
│   ├── run_model_parity.py        # Re-measures the tiering matrix
│   ├── CHECKS.md                  # Machine-readable gate matrix and parallel protocol
│   └── check_*.py                 # Parity, doc, pack, voice, and silhouette gates
├── docs/
│   └── PRODUCT.md                 # Product doctrine (the why behind the repo)
└── assets/
    └── examples/                  # Before/after sets: article, LinkedIn, sales
```

## Voice Presets

Read one preset from `presets/` before a rewrite.

| Preset | Style | Best for |
|--------|-------|----------|
| `crisp` | Short, direct, no filler | Technical writing, documentation |
| `warm` | Friendly, conversational | Emails, blog posts |
| `expert` | Authoritative, confident | Thought leadership, articles |
| `story` | Narrative flow, show rather than tell | Case studies, personal posts |

## Scoring Rubric

Eight criteria, one to five points each (40 maximum): directness, natural rhythm, concrete
verbs, reader trust, human authenticity, content density, fact preservation, and template
avoidance. Strict mode fails a rewrite scoring below 32/40. Criteria live in
`references/rubric.md`.

## Supported Agents

This skill follows the [Agent Skills specification](https://agentskills.io) and works with:

- Claude Code
- Cursor
- Codex
- OpenCode
- Cline
- Roo Code
- And [35+ other agents](https://github.com/vercel-labs/skills#supported-agents)

## Wikipedia Sync

Part of the phrase catalog derives from Wikipedia's
[Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) guide. The
skill can sync itself with that page to pick up new patterns as editors add them:

```bash
python3 scripts/wiki_sync.py check
```

The sync diffs against the last run and proposes updates to `taboo-phrases.md` and the phrase
scanner, always eval-row-first per `references/maintenance.md`. Wikipedia-only patterns (broken
wikitext, DOI issues) get skipped, and state lives in `scripts/.wiki_sync_state.json`
(gitignored).

## Maintenance

All maintenance is eval-first, and the row lands red in `evals/adversarial-evals.json` before
any scanner or catalog edit turns it green. `references/maintenance.md` holds the procedures for
adding a banned phrase (with its required literal-use protection row), adding a structural
pattern, listing current patterns, and running the Wikipedia sync. `CLAUDE.md` and `AGENTS.md`
hold the contribution rules, and `docs/PRODUCT.md` holds the reasoning behind them.

## Philosophy

AI text follows predictable patterns that readers learn to spot. unslop doesn't just swap
words, it restructures content to read as human, and it refuses to fix writing that was never
broken. The guiding principles:

- **Cut what carries no meaning.** If removal doesn't change the meaning, remove it.
- **Trust the reader.** They don't need `"let that sink in"`.
- **Facts are sacred.** Numbers, names, dates, negations, and scope survive unchanged.
- **Do no harm.** Register hedges, literal vocabulary, and already-human prose stay intact.
- **Voice runs under the constitution.** A mimic that reintroduces slop is a failure.
- **The eval suite defines the product.** If a behavior matters, a row fails without it.

## Requirements and License

Python 3.8+ and any supported coding agent. Licensed MIT.
</content>
</invoke>
