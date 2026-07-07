# /unslop mimic

Single-pass voiced writing. Draft or rewrite in a taught voice, then clear the
full gate battery. Route here on "write this like me", "match my voice", or
"mimic this author" once a voice card exists. Read `references/mimic.md` for card
anatomy, scoring, and failure modes.

## Flow

1. Load the situation sheet the task needs. Read `card.md` for the always-on core
   (rhythm, contraction habits, punctuation, openers, the Never list) and the
   one `card/<situation>.md` sheet that matches what you are writing. Load only
   what the task needs; the card is layered so generation stays cheap.
2. Draft or rewrite in that voice. Follow the card's measured markers and
   verbatim snippets; do not invent a habit the samples cannot support.
3. Run the output through **every** removal gate:
   ```bash
   python3 scripts/banned_phrase_scan.py <<< "$OUTPUT"
   python3 scripts/structure_scan.py <<< "$OUTPUT"
   python3 scripts/readability_metrics.py <<< "$OUTPUT"
   python3 scripts/validate_preservation.py original.txt "$OUTPUT_FILE"
   python3 scripts/diff_check.py original.txt "$OUTPUT_FILE"
   ```
4. Score the voice:
   ```bash
   python3 scripts/voice_score.py --profile profile.json "$OUTPUT_FILE"
   ```

## The rule

A mimic that scores well on voice but trips a slop gate is **rejected**. Voice
never buys an exemption from the constitution — the removal gates are hard, the
voice score is a guide. Meaning preservation versus the original draft is its own
hard gate, never blended into the voice score.

## Refine — when one pass is not enough

Most users teach once and mimic cheaply thereafter. When a single pass keeps
scoring short of the target voice, hill-climb with the refine loop — worth the
cost only then:

```bash
python3 evals/run_mimic_refine.py --samples samples/ --draft draft.md --out OUT
```

LIVE (default) calls `--generate-cmd` (default `claude -p`) once per beam per
iteration; `--candidates-dir DIR` runs the loop logic with no model calls. Hard
gates (banned-phrase, structure, draft→candidate preservation, copy-gate, 150-
word floor) discard a candidate regardless of score; survivors are scored against
a held-out DEV split with the full `voice_score` composite, and the best-so-far
never regresses. The **divergence guard** halts and sets
`reward_hacking_warning` when the A composite improves while DEV worsens for two
iterations — the reward-hacking signature. Confirm a win only when
`mimic_stats.py` shows the CI lower bound > 0 and p < 0.05. Internals, baselines,
and the failure table are in `references/mimic.md`.

## Voice check

"Does this sound like me?" — score only, change nothing. Run
`python3 scripts/voice_score.py --profile .unslop/voice/<name>/profile.json
--impostors evals/fixtures/voice/impostors --seed 7 <draft>` and report the
composite (lower is more them), the GI rank, and the two or three metric
deltas that explain the score, in plain words ("your sentences run longer than
usual; contractions match"). No rewrite unless asked. This is the cheapest
voice interaction and the usual one after teach: check drafts often, commission
rewrites rarely.
