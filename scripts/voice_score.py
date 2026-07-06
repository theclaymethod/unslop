#!/usr/bin/env python3
"""Score a candidate against a voice profile.

Lower composite means more user-like. The composite is half GI-rank penalty and
half clipped, weighted impostor z-distance using the WP10a research weights.
"""

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path

import voice_profile

WEIGHTS = {
    "char3": 0.30,
    "delta": 0.25,
    "sentence_emd": 0.10,
    "punctuation": 0.08,
    "contraction": 0.07,
    "mtld": 0.10,
    "word_length": 0.10,
}


def cosine_distance(a, b, keys=None):
    keys = list(keys) if keys is not None else sorted(set(a) | set(b))
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    na = math.sqrt(sum(a.get(k, 0.0) ** 2 for k in keys))
    nb = math.sqrt(sum(b.get(k, 0.0) ** 2 for k in keys))
    if not na or not nb:
        return 1.0
    return 1 - (dot / (na * nb))


def z_function_vector(freqs, bg, top):
    keys = sorted(bg, key=lambda k: bg[k].get("mean", 0), reverse=True)[:top]
    return {k: (freqs.get(k, 0.0) - bg[k]["mean"]) / (bg[k]["std"] or 0.0001) for k in keys}


def emd(a, b):
    if not a or not b:
        return 0.0
    max_len = max(max(a), max(b))
    ca = cb = dist = 0.0
    for i in range(1, max_len + 1):
        ca += sum(1 for x in a if x == i) / len(a)
        cb += sum(1 for x in b if x == i) / len(b)
        dist += abs(ca - cb)
    return dist


def l1(a, b, keys):
    return sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys)


def distances(profile, feats, subset=None):
    subset = set(subset or WEIGHTS)
    out = {}
    if "char3" in subset:
        keys = set(profile["char3"]) | set(feats["char3"])
        out["char3"] = cosine_distance(profile["char3"], feats["char3"], keys)
    if "delta" in subset:
        top = 50 if feats["total_words"] < 300 else 200
        bg = profile["function_word_background"]
        pv = z_function_vector(profile["function_words"], bg, top)
        cv = z_function_vector(feats["function_words"], bg, top)
        out["delta"] = cosine_distance(pv, cv, pv.keys())
    if "sentence_emd" in subset:
        med = profile["sentence_lengths"].get("median") or 1.0
        out["sentence_emd"] = emd(profile["sentence_lengths"]["lengths"], feats["sentence_lengths"]["lengths"]) / med
    if "punctuation" in subset:
        out["punctuation"] = l1(profile["punctuation"], feats["punctuation"], voice_profile.PUNCT)
    if "contraction" in subset:
        out["contraction"] = abs(profile["contraction_rate"] - feats["contraction_rate"])
    if "mtld" in subset:
        out["mtld"] = abs(profile["mtld"] - feats["mtld"]) / (profile["mtld"] or 1.0)
    if "word_length" in subset:
        keys = [str(i) for i in range(1, 16)]
        out["word_length"] = l1(profile["word_length_histogram"], feats["word_length_histogram"], keys)
    return out


def weighted_sum(dists):
    return sum(WEIGHTS[k] * dists.get(k, 0.0) for k in WEIGHTS)


def impostor_features(root):
    feats = []
    for path in voice_profile.iter_docs(root):
        feats.append((str(path), voice_profile.feature_bundle(path.read_text(errors="replace"))))
    return feats


def zscores(candidate, impostor_rows):
    out = {}
    for key in WEIGHTS:
        vals = [row[key] for row in impostor_rows if key in row]
        if key not in candidate or not vals:
            out[key] = None
            continue
        mean = statistics.mean(vals)
        std = statistics.pstdev(vals) or 0.0001
        out[key] = (candidate[key] - mean) / std
    return out


def gi_score(profile, cand_feats, impostors, seed):
    rng = random.Random(seed)
    keys = list(WEIGHTS)
    wins = 0
    trials = 64
    for _ in range(trials):
        subset = [k for k in keys if rng.random() < 0.5] or [rng.choice(keys)]
        cand = weighted_sum(distances(profile, cand_feats, subset))
        sampled = rng.sample(impostors, k=min(len(impostors), max(1, len(impostors) // 2)))
        if all(cand < weighted_sum(distances(profile, imp, subset)) for _, imp in sampled):
            wins += 1
    return wins / trials


def ngrams(tokens, n=4):
    return set(tuple(tokens[i:i + n]) for i in range(max(0, len(tokens) - n + 1)))


def lcs_len(a, b):
    prev = [0] * (len(b) + 1)
    best = 0
    for ca in a:
        cur = [0]
        for j, cb in enumerate(b, 1):
            val = prev[j - 1] + 1 if ca == cb else 0
            best = max(best, val)
            cur.append(val)
        prev = cur
    return best


def copy_gate(candidate_text, samples_dir):
    cand_grams = ngrams(voice_profile.words(candidate_text))
    max_overlap = 0.0
    max_lcs = 0
    for path in voice_profile.iter_docs(samples_dir):
        text = path.read_text(errors="replace")
        sample_grams = ngrams(voice_profile.words(text))
        if cand_grams:
            max_overlap = max(max_overlap, len(cand_grams & sample_grams) / len(cand_grams))
        max_lcs = max(max_lcs, lcs_len(candidate_text, text))
    return {
        "max_overlap": max_overlap,
        "longest_common_substring": max_lcs,
        "violation": max_overlap > 0.35 or max_lcs > 120,
    }


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--impostors", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--samples")
    parser.add_argument("candidate_file")
    return parser.parse_args(argv)


def read_candidate(path):
    if path == "-":
        return sys.stdin.read()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    return p.read_text(errors="replace")


def main(argv):
    args = parse_args(argv)
    if not Path(args.profile).exists() or not Path(args.impostors).is_dir():
        print("missing profile or impostors", file=sys.stderr)
        return 2
    try:
        text = read_candidate(args.candidate_file)
    except FileNotFoundError as e:
        print(f"missing candidate: {e}", file=sys.stderr)
        return 2
    profile = json.loads(Path(args.profile).read_text())
    feats = voice_profile.feature_bundle(text)
    low = feats["total_words"] < 150
    impostors = impostor_features(args.impostors)
    dist = distances(profile, feats)
    imp_dist = [distances(profile, f) for _, f in impostors]
    zs = zscores(dist, imp_dist)
    zsum = sum(WEIGHTS[k] * max(-3.0, min(3.0, zs[k] if zs[k] is not None else 0.0)) for k in WEIGHTS)
    gi = gi_score(profile, feats, impostors, args.seed) if impostors else 0.0
    result = {
        "candidate_words": feats["total_words"],
        "low_confidence": low,
        "distances": {k: (None if low and k in {"sentence_emd", "mtld"} else v) for k, v in dist.items()},
        "z_scores": {k: (None if low and k in {"sentence_emd", "mtld"} else v) for k, v in zs.items()},
        "gi": gi,
        "composite": 0.5 * (1 - gi) + 0.5 * zsum,
    }
    if args.samples:
        result["copy_gate"] = copy_gate(text, args.samples)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
