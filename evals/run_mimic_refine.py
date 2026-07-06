#!/usr/bin/env python3
"""Iterative ``--refine`` loop for the mimic feature (formerly the onslaught
design). Given author samples and a draft, it hill-climbs candidates toward the
author's stylometric profile under hard removal gates, accepting only DEV-split
improvements and halting on patience or on the reward-hacking divergence
signature.

Two candidate sources, both driving the identical gate/score/accept path:

* LIVE (default): each iteration assembles B prompts (draft + the A-split voice
  card + the k nearest-A samples + the current directives) and invokes
  ``--generate-cmd`` once per prompt, feeding the prompt on stdin and reading the
  candidate on stdout. ``--baseline zero|few|retrieval`` selects which samples
  ride in the prompt (none / first-k / k nearest-A). Deterministic when the
  generator is deterministic.
* DRY-RUN: pass ``--candidates-dir DIR`` and the loop reads ``DIR/iter<i>/*.md``
  as that iteration's batch instead of generating them. The MIMIC-* eval rows
  exercise both paths (the live path via a mock generator).

Acceptance and the divergence guard both use the FULL ``voice_score`` composite
(``0.5*(1-GI) + 0.5*`` clipped weighted impostor z-distance) against a same-genre
impostor pool, not a raw weighted distance — a marker-stuffed candidate that
clears every hard gate must still lose to honest prose. The generator never
scores itself. Climb on A, accept on DEV, watch for divergence between the two.
"""

import argparse
import json
import os
import random
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import voice_profile  # noqa: E402
import voice_score  # noqa: E402
import voice_card  # noqa: E402
import banned_phrase_scan  # noqa: E402
import structure_scan  # noqa: E402
import validate_preservation  # noqa: E402

LENGTH_FLOOR = 150
PRECISION = 12
DEFAULT_IMPOSTORS = ROOT / "evals" / "fixtures" / "voice" / "impostors"
NEAREST_K = 2

DIRECTIVE_TEXT = {
    "char3": ("Shift vocabulary and letter texture toward the samples; you are "
              "leaning on different words than the author.",
              "Lexicon: prefer the author's concrete nouns over your own."),
    "delta": ("Rebalance function words (articles, pronouns, prepositions) "
              "toward the author's mix.",
              "Openers & connectives: match the author's function-word rhythm."),
    "sentence_emd": ("Move sentence lengths toward the author's distribution "
                     "(median {med} words).",
                     "Rhythm: target a median sentence around {med} words."),
    "punctuation": ("Match the author's punctuation habits instead of your own.",
                    "Punctuation: mirror the author's mark rates."),
    "contraction": ("Match the author's contraction rate ({rate}).",
                    "Contractions: target rate {rate}."),
    "mtld": ("Match the author's lexical variety; you are repeating or varying "
             "words more than they do.",
             "Lexicon: match the author's repetition and variety."),
    "word_length": ("Match the author's word-length habit (shorter or longer "
                    "words).",
                    "Lexicon: match the author's average word length."),
}


def round12(x):
    return round(float(x), PRECISION)


def split_docs(paths, seed, dev_frac=0.4):
    """Deterministic by-document split into (A, DEV) file lists."""
    ordered = sorted(str(p) for p in paths)
    shuffled = ordered[:]
    random.Random(seed).shuffle(shuffled)
    n = len(shuffled)
    n_dev = max(2, round(n * dev_frac))
    dev = sorted(shuffled[:n_dev])
    a = sorted(shuffled[n_dev:])
    return [Path(p) for p in a], [Path(p) for p in dev]


def profile_from_paths(paths, background=None):
    text = "\n\n".join(p.read_text(errors="replace") for p in paths)
    profile = voice_profile.feature_bundle(text)
    profile["function_word_background"] = voice_profile.background_stats(background)
    profile["metadata"] = {
        "doc_count": len(paths),
        "total_words": profile["total_words"],
        "low_confidence": profile["total_words"] < 2000,
        "genre_warning": "",
    }
    return profile


def make_scorer(profile, impostor_rows, seed):
    """Full voice_score composite (GI + clipped weighted z-distance) closure.

    Lower is more author-like. Impostor z-distances are precomputed per profile;
    GI is reseeded per call so the whole loop is reproducible.
    """
    imp_dist = [voice_score.distances(profile, f) for _, f in impostor_rows]

    def score(feats):
        dist = voice_score.distances(profile, feats)
        zs = voice_score.zscores(dist, imp_dist)
        zsum = sum(
            voice_score.WEIGHTS[k]
            * max(-3.0, min(3.0, zs[k] if zs[k] is not None else 0.0))
            for k in voice_score.WEIGHTS
        )
        gi = (voice_score.gi_score(profile, feats, impostor_rows, seed)
              if impostor_rows else 0.0)
        return round12(0.5 * (1 - gi) + 0.5 * zsum)

    return score


def copy_gate_vs_paths(cand_text, a_paths):
    """Anti-verbatim-copy gate against the A split only (not the DEV holdout)."""
    cand_grams = voice_score.ngrams(voice_profile.words(cand_text))
    max_overlap = 0.0
    lcs_violation = False
    for path in a_paths:
        text = path.read_text(errors="replace")
        sample_grams = voice_score.ngrams(voice_profile.words(text))
        if cand_grams:
            max_overlap = max(max_overlap, len(cand_grams & sample_grams) / len(cand_grams))
        if voice_score.has_common_substring_over(cand_text, text, voice_score.LCS_THRESHOLD + 1):
            lcs_violation = True
    return max_overlap > 0.35 or lcs_violation


def run_gates(cand_text, draft_text, a_paths, genre):
    """Return (passed, reason_or_None, gate_detail)."""
    gates = {}
    banned = banned_phrase_scan.scan_for_violations(cand_text)
    gates["banned_phrase"] = not banned
    struct = structure_scan.scan(cand_text, genre)
    gates["structure"] = not struct["flags"]
    pres = validate_preservation.validate_preservation(draft_text, cand_text)
    gates["preservation"] = pres["passed"]
    gates["copy_gate"] = not copy_gate_vs_paths(cand_text, a_paths)
    words = len(voice_profile.words(cand_text))
    gates["length_floor"] = words >= LENGTH_FLOOR
    order = ["length_floor", "preservation", "banned_phrase", "structure", "copy_gate"]
    reason = next((g for g in order if not gates[g]), None)
    return reason is None, reason, gates


def load_iteration_candidates(candidates_dir, index):
    d = Path(candidates_dir) / f"iter{index}"
    if not d.is_dir():
        return None
    out = []
    for path in sorted(d.glob("*.md")):
        out.append((path.name, path.read_text(errors="replace")))
    return out


# --------------------------- live generation ---------------------------

def char3_cosine(a_text, b_text):
    ga = voice_profile.char3_counts(a_text)
    gb = voice_profile.char3_counts(b_text)
    return voice_score.cosine_distance(ga, gb)


def nearest_samples(draft_text, a_paths, k=NEAREST_K):
    scored = []
    for p in a_paths:
        text = p.read_text(errors="replace")
        scored.append((char3_cosine(draft_text, text), p.name, text))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [(name, text) for _, name, text in scored[:k]]


def select_samples(baseline, draft_text, a_paths, k=NEAREST_K):
    """Which A samples ride in the prompt, per baseline mode."""
    if baseline == "zero":
        return []
    if baseline == "few":
        ordered = sorted(a_paths, key=lambda p: p.name)[:k]
        return [(p.name, p.read_text(errors="replace")) for p in ordered]
    return nearest_samples(draft_text, a_paths, k)  # retrieval (default)


def build_prompt(draft_text, card_text, samples, directives, beam_index):
    parts = ["# Voice card\n" + card_text.strip()]
    for name, text in samples:
        parts.append(f"# Sample: {name}\n{text.strip()}")
    if directives:
        parts.append("# Directives\n" + "\n".join(
            f"- {d['directive']}" for d in directives))
    parts.append("# Draft to rewrite in this voice\n" + draft_text.strip())
    parts.append(f"# Variant {beam_index}")
    return "\n\n".join(parts) + "\n"


def generate_candidate(generate_cmd, prompt, iter_index):
    env = dict(os.environ, MOCK_ITER=str(iter_index))
    proc = subprocess.run(
        shlex.split(generate_cmd), input=prompt, text=True,
        capture_output=True, env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"generate-cmd failed ({proc.returncode}): {proc.stderr}")
    return proc.stdout


def make_live_source(args, a_paths, profile_a, docs_a, matrix_a, draft_text):
    """Build the card once, then generate a beam per iteration through the CLI."""
    card_text = voice_card.build_card(profile_a, docs_a, matrix_a, args.name)
    samples = select_samples(args.baseline, draft_text, a_paths)

    def get_batch(index, directives):
        batch = []
        for b in range(args.beam):
            prompt = build_prompt(draft_text, card_text, samples, directives, b)
            text = generate_candidate(args.generate_cmd, prompt, index)
            batch.append((f"cand{b + 1:02d}.md", text))
        return batch

    return get_batch


def make_dry_run_source(candidates_dir):
    def get_batch(index, directives):
        return load_iteration_candidates(candidates_dir, index)
    return get_batch


def derive_directives(profile_dev, best_feats):
    dists = voice_score.distances(profile_dev, best_feats)
    weighted = sorted(
        ((k, voice_score.WEIGHTS[k] * dists.get(k, 0.0)) for k in voice_score.WEIGHTS),
        key=lambda kv: (-kv[1], kv[0]),
    )
    med = int(profile_dev["sentence_lengths"]["median"])
    rate = f"{profile_dev['contraction_rate']:.3f}"
    out = []
    for metric, wdist in weighted[:4]:
        text, amend = DIRECTIVE_TEXT[metric]
        out.append({
            "metric": metric,
            "weighted_distance": round12(wdist),
            "directive": text.format(med=med, rate=rate),
            "card_amendment": amend.format(med=med, rate=rate),
        })
    return out


def build_report(args, a_paths, dev_paths, profile_a, profile_dev,
                 score_a, score_dev, get_batch):
    genre = args.genre
    draft_text = Path(args.draft).read_text(errors="replace")

    iterations = []
    best_name = None
    best_score = None
    best_feats = None
    best_text = None
    stop_reason = None
    reward_hacking = False
    since_accept = 0
    divergence_run = 0
    prev_best_a = None
    prev_best_dev = None
    directives = []

    for i in range(args.iterations):
        batch = get_batch(i, directives)
        if batch is None:
            stop_reason = "candidates_exhausted"
            break
        cand_records = []
        rejections = []
        survivors = []  # (name, dev_score, a_score, feats, text)
        for name, text in batch:
            passed, reason, gates = run_gates(text, draft_text, a_paths, genre)
            feats = voice_profile.feature_bundle(text)
            dev_score = score_dev(feats)
            a_score = score_a(feats)
            cand_records.append({
                "name": name,
                "words": feats["total_words"],
                "gates": gates,
                "passed": passed,
                "dev_score": dev_score if passed else None,
                "a_score": a_score if passed else None,
            })
            if passed:
                survivors.append((name, dev_score, a_score, feats, text))
            else:
                rejections.append({"name": name, "reason": reason})

        accepted = False
        iter_best = None
        iter_best_dev = None
        iter_best_a = None
        if survivors:
            survivors.sort(key=lambda s: (s[1], s[0]))
            iter_best = survivors[0][0]
            iter_best_dev = survivors[0][1]
            iter_best_a = survivors[0][2]
            iter_feats = survivors[0][3]
            if best_score is None or iter_best_dev <= best_score - args.min_delta:
                accepted = True
                best_score = iter_best_dev
                best_name = iter_best
                best_feats = iter_feats
                best_text = survivors[0][4]

        # Divergence: best-survivor A improves while DEV worsens, 2 rounds running.
        if (iter_best_dev is not None and prev_best_dev is not None
                and iter_best_a < prev_best_a and iter_best_dev > prev_best_dev):
            divergence_run += 1
        else:
            divergence_run = 0
        if iter_best_dev is not None:
            prev_best_a = iter_best_a
            prev_best_dev = iter_best_dev

        directives = (derive_directives(profile_dev, survivors[0][3])
                      if survivors else [])

        iterations.append({
            "index": i,
            "candidates": cand_records,
            "gate_rejections": rejections,
            "best_survivor": iter_best,
            "best_dev_score": iter_best_dev,
            "best_a_score": iter_best_a,
            "accepted": accepted,
            "directives": directives,
        })

        since_accept = 0 if accepted else since_accept + 1

        if divergence_run >= 2:
            stop_reason = "divergence"
            reward_hacking = True
            break
        if since_accept >= args.patience:
            stop_reason = "patience"
            break

    if stop_reason is None:
        stop_reason = "max_iterations"

    final_directives = derive_directives(profile_dev, best_feats) if best_feats else []

    report = {
        "seed": args.seed,
        "baseline": args.baseline,
        "genre": genre,
        "impostors": str(args.impostors),
        "split": {
            "A": [p.name for p in a_paths],
            "DEV": [p.name for p in dev_paths],
        },
        "iterations": iterations,
        "best_candidate": best_name,
        "best_score": best_score,
        "stop_reason": stop_reason,
        "reward_hacking_warning": reward_hacking,
        "directives": final_directives,
        "card_path": str(Path(args.out) / "voice-card.refined.md"),
    }
    return report, best_text


def write_outputs(args, report, a_paths, profile_a, docs_a, matrix_a, best_text):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    # Refined card: base card from the A split plus the directive amendments.
    base = voice_card.build_card(profile_a, docs_a, matrix_a, args.name)
    amend_lines = ["", "## Refinement amendments", ""]
    for d in report["directives"]:
        amend_lines.append(f"- {d['card_amendment']}")
    (out / "voice-card.refined.md").write_text(base + "\n".join(amend_lines) + "\n")
    # Best candidate text (captured from whichever source produced it).
    if best_text is not None:
        (out / "final.md").write_text(best_text)


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--samples", required=True)
    p.add_argument("--draft", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--seed", required=True, type=int)
    p.add_argument("--iterations", type=int, default=6)
    p.add_argument("--beam", type=int, default=4)
    p.add_argument("--patience", type=int, default=2)
    p.add_argument("--min-delta", type=float, default=0.01)
    p.add_argument("--generate-cmd", default="claude -p")
    p.add_argument("--candidates-dir")
    p.add_argument("--impostors", default=str(DEFAULT_IMPOSTORS))
    p.add_argument("--baseline", choices=["zero", "few", "retrieval"], default="retrieval")
    p.add_argument("--genre", choices=["prose", "docs", "social"], default="prose")
    p.add_argument("--name", default="voice")
    return p.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    samples = Path(args.samples)
    if not samples.is_dir() or not Path(args.draft).exists():
        print("missing samples dir or draft", file=sys.stderr)
        return 2
    if not Path(args.impostors).is_dir():
        print(f"missing impostor pool: {args.impostors}", file=sys.stderr)
        return 2
    paths = list(voice_profile.iter_docs(samples))
    if len(paths) < 5:
        print(f"need at least 5 sample documents to split; found {len(paths)}",
              file=sys.stderr)
        return 2

    a_paths, dev_paths = split_docs(paths, args.seed)
    if len(dev_paths) < 2:
        print("DEV split needs at least 2 documents", file=sys.stderr)
        return 2
    profile_a = profile_from_paths(a_paths)
    profile_dev = profile_from_paths(dev_paths)

    docs_a = []
    for p in a_paths:
        sents = voice_card.split_sentences_text(p.read_text(errors="replace"))
        if sents:
            docs_a.append(sents)
    matrix_a, _ = voice_card.coverage_matrix(docs_a)

    impostor_rows = voice_score.impostor_features(args.impostors)
    score_a = make_scorer(profile_a, impostor_rows, args.seed)
    score_dev = make_scorer(profile_dev, impostor_rows, args.seed)

    if args.candidates_dir is not None:
        get_batch = make_dry_run_source(args.candidates_dir)
    else:
        get_batch = make_live_source(args, a_paths, profile_a, docs_a, matrix_a,
                                     Path(args.draft).read_text(errors="replace"))

    report, best_text = build_report(args, a_paths, dev_paths, profile_a,
                                     profile_dev, score_a, score_dev, get_batch)
    write_outputs(args, report, a_paths, profile_a, docs_a, matrix_a, best_text)
    print(json.dumps({
        "best_candidate": report["best_candidate"],
        "best_score": report["best_score"],
        "stop_reason": report["stop_reason"],
        "reward_hacking_warning": report["reward_hacking_warning"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
