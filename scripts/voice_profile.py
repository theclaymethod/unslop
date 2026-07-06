#!/usr/bin/env python3
"""Build deterministic stylometric voice profiles.

The built-in background table is a compact Writeprints-style English baseline:
common function words seeded from public-domain frequency lists used by classic
authorship-attribution examples, with broad fallback means/stddevs for words not
observed in a caller-supplied background corpus. It is meant only as a stable
normalizer; pass --background with same-genre documents for calibrated work.
"""

import argparse
import collections
import json
import math
import re
import statistics
import sys
from pathlib import Path

FUNCTION_WORDS = """
the of and to in a is that it for as with was on be by he i this are or his from at
which but have an had they you were their one all we can her has there been if more
when will would who so no she about out up into do any your what than them some could
these other then its our two may first my now such like over only also after most did
many before must through back where much should well people down own just because good
each those how under see made very being make between both even another while last
might still same never every against since off though yet without within upon among
until during per either neither nor whether whose whom why again once here there
therefore however although nevertheless moreover instead indeed perhaps rather thus
else already almost around across behind beyond near toward towards above below beside
inside outside along plus minus except despite via versus including regarding concerning
am were does done doing having let lets cannot dont didn't doesn't isn't aren't wasn't
weren't haven't hasn't hadn't won't wouldn't shouldn't couldn't mightn't mustn't i'm
you're he's she's it's we're they're i've you've we've they've i'd you'd he'd she'd we'd
they'd i'll you'll he'll she'll we'll they'll me him us mine yours ours theirs myself
yourself himself herself itself ourselves yourselves themselves
""".split()

PUNCT = [",", ".", ";", ":", "?", "!", "-", "(", ")", '"', "'"]
WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+")
SENT_RE = re.compile(r"[^.!?]+[.!?]?")


def iter_docs(root):
    for path in sorted(Path(root).rglob("*")):
        if path.suffix.lower() in {".txt", ".md"} and path.is_file():
            yield path


def normalize(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


def words(text):
    return WORD_RE.findall(text.lower())


def sentences(text):
    out = []
    for part in SENT_RE.findall(text):
        toks = words(part)
        if toks:
            out.append(toks)
    return out


def char3_counts(text, limit=None):
    norm = normalize(text)
    grams = collections.Counter(norm[i:i + 3] for i in range(max(0, len(norm) - 2)))
    items = sorted(grams.items(), key=lambda kv: (-kv[1], kv[0]))
    if limit:
        items = items[:limit]
    return dict(items)


def function_freq(tokens):
    total = max(1, len(tokens))
    counts = collections.Counter(tokens)
    return {w: counts[w] / total for w in FUNCTION_WORDS}


def sentence_stats(text):
    lengths = [len(s) for s in sentences(text)]
    if not lengths:
        return {"lengths": [], "median": 0.0, "iqr": 0.0}
    ordered = sorted(lengths)
    mid = statistics.median(ordered)
    q1 = statistics.median(ordered[:len(ordered) // 2] or ordered)
    q3 = statistics.median(ordered[(len(ordered) + 1) // 2:] or ordered)
    return {"lengths": lengths, "median": mid, "iqr": q3 - q1}


def mtld(tokens, threshold=0.72):
    if len(tokens) < 20:
        return 0.0
    factors = 0.0
    types = set()
    count = 0
    for tok in tokens:
        count += 1
        types.add(tok)
        if len(types) / count <= threshold:
            factors += 1
            types.clear()
            count = 0
    if count:
        ttr = len(types) / count
        factors += (1 - ttr) / (1 - threshold) if threshold < 1 else 0
    return len(tokens) / factors if factors else float(len(tokens))


def feature_bundle(text):
    toks = words(text)
    total = max(1, len(toks))
    punct_counts = collections.Counter(ch for ch in text if ch in PUNCT)
    contractions = sum(1 for t in toks if "'" in t)
    hist = collections.Counter(min(len(t), 15) for t in toks)
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return {
        "char3": char3_counts(text, 2000),
        "function_words": function_freq(toks),
        "sentence_lengths": sentence_stats(text),
        "punctuation": {p: punct_counts[p] / total for p in PUNCT},
        "contraction_rate": contractions / total,
        "mtld": mtld(toks),
        "word_length_histogram": {str(i): hist[i] / total for i in range(1, 16)},
        "paragraph_stats": {
            "count": len(paragraphs),
            "mean_words": (sum(len(words(p)) for p in paragraphs) / len(paragraphs)) if paragraphs else 0.0,
        },
        "total_words": len(toks),
    }


def background_stats(root=None):
    docs = []
    if root:
        docs = [p.read_text(errors="replace") for p in iter_docs(root)]
    if not docs:
        return {w: {"mean": 0.0025 if w not in {"the", "of", "and", "to", "in", "a"} else 0.025,
                    "std": 0.006} for w in FUNCTION_WORDS}
    rows = [function_freq(words(text)) for text in docs]
    stats = {}
    for w in FUNCTION_WORDS:
        vals = [r[w] for r in rows]
        stats[w] = {
            "mean": statistics.mean(vals),
            "std": statistics.pstdev(vals) or 0.0001,
        }
    return stats


def build_profile(samples_dir, background=None):
    paths = list(iter_docs(samples_dir))
    text = "\n\n".join(p.read_text(errors="replace") for p in paths)
    profile = feature_bundle(text)
    profile["function_word_background"] = background_stats(background)
    profile["metadata"] = {
        "doc_count": len(paths),
        "total_words": profile["total_words"],
        "low_confidence": profile["total_words"] < 2000,
        "genre_warning": "profile has fewer than 2000 words" if profile["total_words"] < 2000 else "",
    }
    return profile


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("samples_dir")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--background")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    root = Path(args.samples_dir)
    if not root.is_dir():
        print(f"missing samples dir: {root}", file=sys.stderr)
        return 2
    profile = build_profile(root, args.background)
    if profile["metadata"]["low_confidence"]:
        print(profile["metadata"]["genre_warning"], file=sys.stderr)
    Path(args.output).write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
