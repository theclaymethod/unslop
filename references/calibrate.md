# Teach Calibration Game (A/B Preference Elicitation)

An agent-hosted micro-game that calibrates voice preferences the user can state but
never bothered to write samples for. Far lower effort than `teach`: harvest bootstraps
samples, the A/B game calibrates dimension preferences, and both feed the voice card.
`teach` offers this game (`references/commands/teach.md`, step 3) when sample coverage
or confidence stays thin; this file is the canonical flow and rationale.

## Deterministic set

Five dimensions are reachable by reversible, seed-deterministic transforms of a base
passage (`scripts/calibrate_pairs.py`): `contractions`, `em_dash`, `sentence_length`,
`connectives`, `staccato`. Every transform preserves the base passage's must-preserve
constraints (`scripts/extract_constraints.py`) or the command exits 3 rather than
silently dropping a fact.

Register and warmth are NOT in this set — they need LLM generation, not a mechanical
transform, and are out of scope for `calibrate_pairs.py`. If the game wants to cover
those dimensions, generate the pair with a model and skip the determinism/constraint
guarantees this script gives for free.

## Game flow

1. Pick base passages from the user's own harvested samples (`references/harvest.md`)
   when available; otherwise fall back to neutral seed texts. Paragraph-sized (60-150
   words) so a round takes seconds to read.
2. For the dimension needing the most attention, run:
   ```bash
   python3 scripts/calibrate_pairs.py generate --base passage.txt --dimension DIM --seed N
   ```
   Increment the seed each round for that dimension so repeated rounds against the same
   base passage still vary. If the command exits 3 ("dimension not expressible in this
   passage"), pick a different base passage or move to the next dimension — do not force
   a transform through.

   The output also carries `a_flags`/`b_flags`: the `banned_phrase_scan.py` category names
   each variant trips (empty when clean). A generated variant tripping the scanner is not a
   reason to decline the pair — see "Voice overrides defaults" below.
3. Present `a_text` and `b_text` to the user as "is A or B closer to how you'd write
   this?" without naming the dimension or which side is which pole (avoid anchoring).
   Accept "neither" as a valid answer.

   Randomize which pole is shown as "A" and which as "B" each round — a seeded
   shuffle keyed on the round (e.g. `pair_id`) so it is reproducible, not a fresh
   coin flip you can't reconstruct later. Always displaying `calibrate_pairs.py`'s
   own `a_text` as "A" would let the user learn the game's fixed pole ordering
   after a few rounds, reintroducing the anchoring this step is trying to avoid.
   Record the mapping — which of the script's `a_text`/`b_text` was actually shown
   as "A" this round — alongside the round so the recorded `choice` and
   `a_label`/`b_label` in step 4 resolve to the correct pole regardless of what
   was displayed on screen.
4. Append one line to `.unslop/voice/<name>/preferences.jsonl`:
   ```json
   {"pair_id": "...", "dimension": "...", "choice": "a|b|neither", "ts": "...",
    "a_label": "<A's pole from transform_applied>", "b_label": "<B's pole>"}
   ```
   `a_label`/`b_label` come straight off `calibrate_pairs.py`'s `transform_applied`
   (`"<dimension>:<pole>"` names B's pole; A sits at the dimension's other named pole).
   Recording them is what lets `calibrate_score.py` report a semantic direction instead
   of a bare "a"/"b" tally, and what makes conflict detection possible.
5. After each round, run:
   ```bash
   python3 scripts/calibrate_score.py --preferences preferences.jsonl
   ```
   Stop playing a dimension once its `confidence >= 0.7` OR it has reached `k >= 9`
   observations, whichever comes first. Below `k = 5` observations a dimension is always
   reported `"insufficient"` regardless of how lopsided the tally looks — five is the
   floor before a lean means anything. A dimension can also come back `"tied"` with
   `preferred: null` when its top two tallies are exactly equal at `k >= 5` — that's a
   real "no lean yet" result, not insufficient data, and not a coin flip the aggregator
   should silently resolve one way. Play it a couple more rounds. Replaying the same
   round (same `pair_id`) is safe: the aggregator dedups by `pair_id`, keeping only the
   latest row by `ts`, so a retried write never double-counts or lets a stale choice win.
6. Use `--next` to pick which dimension to play next:
   ```bash
   python3 scripts/calibrate_score.py --preferences preferences.jsonl --next
   ```
   Ordering: fewest observations first, then lowest confidence, tie-broken by the fixed
   dimension order (`contractions, em_dash, sentence_length, connectives, staccato`) so
   the choice is reproducible from the same preferences file.
7. When a sample-derived profile exists (`profile.json`, WP10a), run:
   ```bash
   python3 scripts/calibrate_score.py --preferences preferences.jsonl --profile profile.json
   ```
   Any confident (`>= 0.7`) stated preference that contradicts the profile's measured
   value comes back as a `conflicts[]` record naming both values and their provenance,
   e.g. "stated preference for 'short' (confidence 0.70) contradicts
   avg_sentence_length=22.4 measured from samples." Surface every conflict to the user
   verbatim — do not silently pick a winner. Let the user say which one wins; record
   that choice's provenance on the card.
8. Hand the final per-dimension summary to the teach-card step. Every claim on the card
   sourced from this game carries provenance `"stated-preference"`, distinct from
   `"measured-from-samples"` values pulled from the profile directly.

## Voice overrides defaults

A generated variant can legitimately trip `banned_phrase_scan.py` — a staccato pole reads
as `anti_slop_register` (three short fragments in a row is the scanner's own AI-cadence
tell), a plain connective can occasionally read as `filler_opener`. Do not decline these
pairs or quietly steer the user away from the flagged pole; the scanner encodes a default
register guard, and this game exists specifically to find out when a user's real voice
sits outside that default.

When a user's choices consistently land on a pole that `a_flags`/`b_flags` marks as
flagged (e.g. they keep picking the staccato side even though it trips
`anti_slop_register`), record the preference together with its flags. Surface the tension
to the user once, not on every round — something like: "you prefer staccato; the default
register guard flags it as an AI cadence tell — your voice wins in your profile." Do not
re-litigate it every round once the user has answered.

On the final per-dimension summary (step 8), mark that dimension's provenance
`"user-preference overrides register guard"` instead of a bare `"stated-preference"`, so
the teach-card step (and anyone reading the card later) can see that the scanner's default
was deliberately overridden, not silently ignored. This is the same conflict-surfacing
philosophy as the profile conflicts below: voice beats defaults, but only visibly.

## Provenance discipline

The card must always be able to say, for any voice claim, whether it came from the
user's own samples (measured) or from a choice the user made in this game (stated).
Conflicts are a feature, not a bug to smooth over — surfacing them is the whole point
of running both a profile and a preference game.
