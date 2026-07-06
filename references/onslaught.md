# Onslaught Scorer Stub

`scripts/voice_profile.py` builds a deterministic stylometric profile from author samples. `scripts/voice_score.py` measures a candidate against that profile with character 3-grams, function-word cosine delta, sentence-length EMD, punctuation, contractions, MTLD, word-length habits, impostor z-scores, and General Impostors rank scoring.

Use at least 2,000-3,000 words of same-genre samples for real work. Shorter profiles still run, but the profile marks `low_confidence` and the score should be treated as noisy.

The `composite` is a guide, not an oracle; authorship verification has an approximate 93-94% ceiling even in stronger research systems. Lower composite means more profile-like.

When `--samples` is supplied, the scorer reports `copy_gate`. A violation means the candidate overlaps too heavily with source samples by normalized 4-gram overlap or longest common substring. The scorer reports the condition; callers decide whether to reject the candidate.
