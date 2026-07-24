# Pack: Voice

Use this pack for manufactured voice and the skill's own replacement tells. Do not report core phrase boilerplate or factual/register constraints.

## Look For

- Anti-slop register: bare fragment contrasts such as "Not the tool. The team."; forced punch endings; repeated two- or three-word sentences.
- Elegant variation and synonym cycling that calls attention to itself instead of clarifying.
- Dramatic fragments, binary contrasts, negative parallelism, colon reveals, and rhetorical setups.
- Contrastive-definition tails ("X is a build step, not an output."), two-beat imperative slogans ("Emit tokens. Ship bytes."), repeated "<plural noun> that <verb>." fragments, "One X, N Y." numeric parallelism, and abstractions that "ship inside" things.
- Standalone slogan/spec fragment lines and headers: "N X, one Y." slogan cadence ("Four presets, one input.") and "N noun-phrase, past-participle ..." spec-sheet fragments ("Eight criteria, scored 1 to 5."). Flagged only when the whole line is the fragment; the same shape embedded in a sentence is a literal count and stays clean. Soft.
- Headline slogan cadence: the "Short statement. Short statement." two-beat rhythm repeated across a document's headlines ("One command. A real URL." / "Reviewers click. The agent fixes."). One is voice; three or more is template grammar. Frequency-gated, soft.
- Headline container agency: a calendar or program container delivers an artifact or outcome ("Week 1 ends with a calibrated eval"; "Demo day closes the cohort"). Name the completion criterion, mechanism, result, or decision instead. Literal boundaries such as "Week 1 ends on Friday" stay clean. Soft.
- Tool anthropomorphism: an inanimate tool-noun given human agency. Reflexive self-agency fires anywhere ("The suite defends itself." / "The rules update themselves." / "It graded its own reflection."); strongly-volitional verbs (decides, hunts, wants, knows, believes, cares, refuses, judges, thinks) fire only on a standalone headline line ("The bench decides which model does which job." / "It hunts instances, not word lists."). Ordinary technical register stays clean ("the parser reads the file", "the model learns the distribution", "the test cleans up after itself"). Soft.
- Punctuation performance: em-dash clusters, exclamation overuse, decorative bolding, title case inside body prose.
- Warmth stripped into telegraphese: an email or narrative that loses natural softeners and sounds colder than the source.

## Emit

Return JSON findings only:

```json
{"span":"Not the tooling. The conversations.","rule":"anti_slop_register","pack":"pack-voice","severity":"hard","note":"Bare fragment contrast is the skill's own tell; rewrite as varied prose."}
```

Mark `hard` when the cadence is itself a recognizable formula. Mark `soft` when it may be genre-appropriate but needs review.

## Examples

- "Not the strategy. The execution." -> report `anti_slop_register`.
- "We tested the API, fixed the retry path, and shipped." -> no finding.
- "The result: alignment. The cost: trust." -> report colon reveal / fragment cadence.
- "Thanks for sending this over. Could you send the figures by Friday?" -> no finding; natural warmth.
