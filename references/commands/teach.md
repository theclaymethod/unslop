# /unslop teach

Build a reusable voice from a writer's samples. **Agent-driven end to end**: the
user supplies only approvals and answers, never a directory or a command. Route
here on "teach my voice", "learn how I write", or when the user offers samples to
learn from. Any samples the user provides are fair game; there are no rights or
attestation checks.

Read `references/mimic.md` for card anatomy, sample requirements, and scoring
before you finish; this file is the flow.

## 1. Gather samples (harvest)

If the user offers none, default to bootstrapping. Harvest their transcripts and
writing folders per `references/harvest.md`:

```bash
python3 scripts/harvest_samples.py SOURCE [SOURCE...] -o candidates.json
python3 scripts/harvest_classify.py --candidates candidates.json --mode heuristic
```

Present the ranked candidates with their sources and flags; the user approves or
rejects each. Treat `suspect_ai` candidates skeptically — that human review is
the contamination defense, so never auto-approve a flagged paste. Copy only
approved samples into `.unslop/voice/<name>/samples/`. The adapter internals,
contamination tripwire, and privacy rules live in `references/harvest.md`.

## 2. Build the profile and card

Create `.unslop/voice/<name>/` yourself (it is gitignored) and run:

```bash
python3 scripts/voice_profile.py samples/ -o profile.json
python3 scripts/voice_card.py --profile profile.json --samples samples/ --out . --name <name> --provenance
```

`voice_profile.py` is the machine fingerprint the scorer refers to.
`voice_card.py` writes the layered card the generating model follows (`card.md`
plus `card/<situation>.md` sheets) and, with `--provenance`, a `provenance.json`
audit trail. Both scripts read only `.txt` and `.md` files; convert samples
first. `voice_card.py` refuses (exit 2) when the profile does not describe the
supplied samples, so a stale profile can never drive a card.

## 3. Surface confidence and gaps

Show the user `card.md`. If the profile is `low_confidence` (thin or cross-genre
samples), say the voice is provisional and ask for more same-genre samples before
trusting a mimic. For an **Uncovered** dimension the target writing will need,
ask for one short sample that exercises it — and only those the task requires, not
all ten. Prompt templates:

| Dimension | Prompt |
|-----------|--------|
| explaining-technical | "Share something you wrote explaining how a thing works." |
| anecdote | "Share a few sentences telling a small story that happened to you." |
| argument | "Share something where you defended a claim." |
| disagreement | "Share something where you pushed back on an idea." |
| praise | "Share something where you recommended something you liked." |
| hedging-uncertainty | "Share something where you were unsure and said so." |
| numbers-data | "Share something you wrote that works with quantities." |
| addressing-reader | "Share a note or instructions written to a reader." |

`openings` and `closings` are structural and covered as soon as one document
exists, so they need no prompt. The full canonical table lives in
`references/mimic.md`.

When coverage or confidence stays thin and the user cannot supply more samples,
offer the A/B calibration game (`references/calibrate.md`): it elicits voice
preferences through reversible pair choices and feeds them to the card as
`stated-preference` provenance, distinct from `measured-from-samples`.

## 4. Close with a scored demo

Prove the loop before the user trusts it: mimic one paragraph per
`references/commands/mimic.md`, run `scripts/voice_score.py` and the scanners,
and show the results. A voiced demo that trips a slop gate fails the loop; do not
ship it with an excuse.
