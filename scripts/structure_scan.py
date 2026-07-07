#!/usr/bin/env python3
"""Scan prose for macro-structure AI-writing patterns."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _lang import (  # noqa: E402
    ENGLISH_FUNCTION_WORDS,
    english_function_share,
    is_probably_english,
)
from readability_metrics import split_sentences  # noqa: E402


STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "with", "by", "from", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "can", "it", "its", "this", "that",
    "these", "those", "we", "you", "they", "i", "he", "she", "as", "than",
    "if", "then", "so", "not", "no", "yes", "into", "over", "under",
}


CONNECTIVE_OPENERS = re.compile(
    r"^(however|moreover|furthermore|additionally|in addition|overall|"
    r"consequently|nevertheless)\b",
    re.I,
)
SIGNPOST_RE = re.compile(
    r"\b(first,|next,|having (?:covered|established)|in (?:this|the following|"
    r"the next) section|as (?:mentioned|noted) (?:above|earlier)|let us turn|"
    r"let's turn)\b",
    re.I,
)
CLOSER_RE = re.compile(
    r",\s+(ensuring|highlighting|reflecting|allowing|enabling|underscoring|"
    r"showcasing|emphasizing|fostering|driving|paving|reinforcing|solidifying|"
    r"demonstrating|contributing to)\b[^.!?]*[.!?\"]?$",
    re.I,
)
CODA_START_RE = re.compile(
    r"^(ultimately,|in the end,|in conclusion|as we've seen|only time will tell|"
    r"remember,|the future\b)",
    re.I,
)
BOLD_COLON_RE = re.compile(r"^\s*[-*+]?\s*\*\*[^*]{1,40}\*\*\s*:", re.M)


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text.lower())


def strip_markdown_for_prose(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "\n\n", text)
    kept = []
    for line in text.splitlines():
        if re.match(r"\s*>", line) or re.match(r"\s{0,3}#{1,6}\s+", line):
            kept.append("")
            continue
        line = re.sub(r"^\s*[-*+]\s+", "", line)
        line = re.sub(r"^\s*\d+[.)]\s+", "", line)
        kept.append(line)
    return "\n".join(kept)


def prose_paragraphs(text: str) -> list[str]:
    stripped = strip_markdown_for_prose(text)
    return [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", stripped) if p.strip()]


def cv(values: list[int]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)) / mean


def content_bigrams(text: str) -> set[tuple[str, str]]:
    toks = [w for w in words(text) if len(w) > 3 and w not in STOPWORDS]
    return set(zip(toks, toks[1:]))


def triad_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z-]+,\s+[A-Za-z][A-Za-z-]+,\s+and\s+[A-Za-z][A-Za-z-]+\b", text))


def flag(metric: str, value: float | int, threshold: str, detail: str, suggestion: str) -> dict:
    return {
        "metric": metric,
        "value": value,
        "threshold": threshold,
        "severity": "soft",
        "detail": detail,
        "suggestion": suggestion,
    }


# Metrics a given --genre suppresses outright (the genre's normal shape trips
# the metric without being AI-slop). Table form so each suppression is a single
# lookup instead of an inline `genre != "..."` conditional per metric.
GENRE_SUPPRESSIONS = {
    "docs": {"bold_colon_listicle"},
    "social": {"one_line_staccato"},
}


def scan(text: str, genre: str = "prose") -> dict:
    paragraphs = prose_paragraphs(text)
    prose_text = "\n\n".join(paragraphs)
    sentences = split_sentences(prose_text)
    sentence_lengths = [len(words(s)) for s in sentences]
    prose_words = words(prose_text)
    para_lengths = [len(words(p)) for p in paragraphs]
    metrics = {
        "sentence_burstiness": round(cv(sentence_lengths), 3),
        "summary_sandwich": 0.0,
        "paragraph_cv": round(cv(para_lengths), 3),
        "sentence_mean_len": round(sum(sentence_lengths) / len(sentence_lengths), 1) if sentence_lengths else 0,
        "triad_density": round((triad_count(prose_text) / len(prose_words) * 1000), 3) if prose_words else 0,
        "em_dash_per_1k": round((text.count("—") / len(prose_words) * 1000), 3) if prose_words else 0,
        "bold_colon_listicle_count": len(BOLD_COLON_RE.findall(text)),
        "one_line_staccato_share": 0.0,
        "connective_paragraph_openers": 0,
        "signpost_density": 0.0,
        "opener_unique_ratio": 0.0,
        "top_opener_share": 0.0,
        "max_consecutive_opener": 0,
        "participial_closer_share": 0.0,
        "conclusion_coda": False,
    }
    flags = []

    if len(paragraphs) >= 2:
        first = content_bigrams(paragraphs[0])
        last = content_bigrams(paragraphs[-1])
        union = first | last
        metrics["summary_sandwich"] = round(len(first & last) / len(union), 3) if union else 0.0

    if len(sentences) >= 8 and metrics["sentence_burstiness"] < 0.55:
        flags.append(flag(
            "sentence_burstiness",
            metrics["sentence_burstiness"],
            "< 0.55 over at least 8 prose sentences",
            "Sentence lengths are unusually uniform for running prose.",
            "Vary sentence length and cadence; if this is formal reference prose, review before treating it as blocking.",
        ))

    if len(paragraphs) >= 3:
        coda = bool(CODA_START_RE.search(paragraphs[-1]))
        if not coda:
            coda = len(content_bigrams(paragraphs[0]) & content_bigrams(paragraphs[-1])) >= 2
        metrics["conclusion_coda"] = coda
        if coda:
            flags.append(flag(
                "conclusion_coda",
                1,
                "last paragraph starts with a stock coda or repeats 2+ first-paragraph content bigrams",
                "The ending reads like a recap/moral coda instead of a concrete final point.",
                "Cut the wrap-up or end on a specific fact; if this is an abstract or executive summary, judge the genre before changing it.",
            ))

    if (metrics["bold_colon_listicle_count"] >= 3
            and "bold_colon_listicle" not in GENRE_SUPPRESSIONS.get(genre, set())):
        flags.append(flag(
            "bold_colon_listicle",
            metrics["bold_colon_listicle_count"],
            ">= 3 bold-label colon lines",
            "The raw Markdown has repeated bold-label listicle formatting.",
            "Convert to prose or plain bullets; if this is a reference doc, rerun with --genre docs.",
        ))

    if paragraphs:
        one_line = 0
        for p in paragraphs:
            ps = split_sentences(p)
            if len(ps) == 1 and len(words(ps[0])) < 12:
                one_line += 1
        metrics["one_line_staccato_share"] = round(one_line / len(paragraphs), 3)
        if (len(paragraphs) >= 6 and metrics["one_line_staccato_share"] > 0.6
                and "one_line_staccato" not in GENRE_SUPPRESSIONS.get(genre, set())):
            flags.append(flag(
                "one_line_staccato",
                metrics["one_line_staccato_share"],
                "> 0.60 over at least 6 paragraphs",
                "Most paragraphs are short single-sentence beats.",
                "Merge related beats and vary paragraph length; if this is social copy, rerun with --genre social.",
            ))

    connective = sum(1 for p in paragraphs if CONNECTIVE_OPENERS.search(p))
    metrics["connective_paragraph_openers"] = connective
    if connective >= 3 or (len(paragraphs) >= 8 and connective / len(paragraphs) > 0.4):
        flags.append(flag(
            "connective_paragraph_openers",
            connective,
            ">= 3 paragraphs or > 40% of 8+ paragraphs",
            "Paragraphs repeatedly open with formal transition words.",
            "Replace scaffold openers with specific topic sentences; academic prose may justify some connectors.",
        ))

    if prose_words:
        signposts = len(SIGNPOST_RE.findall(prose_text))
        metrics["signpost_density"] = round(signposts / len(prose_words) * 100, 3)
        if len(prose_words) >= 150 and metrics["signpost_density"] > 0.6:
            flags.append(flag(
                "signpost_density",
                metrics["signpost_density"],
                "> 0.6 per 100 prose words, minimum 150 words",
                "The text over-explains its own structure.",
                "Remove roadmap language unless the genre is a textbook, legal brief, or long guide.",
            ))

    if len(sentences) >= 5:
        openers = []
        for s in sentences:
            ws = words(s)
            if not ws:
                continue
            openers.append(ws[0])
        enumeration = {"the", "a", "an", "section", "chapter", "figure", "table",
                       "step", "part", "appendix"}
        counted = [o for o in openers if o not in enumeration]
        top_count = 0
        if counted:
            counts = Counter(counted)
            top_count = max(counts.values())
            metrics["opener_unique_ratio"] = round(len(counts) / len(counted), 3)
            metrics["top_opener_share"] = round(top_count / len(counted), 3)
        run = max_run = 0
        prev = None
        for opener in counted:
            run = run + 1 if opener == prev else 1
            prev = opener
            max_run = max(max_run, run)
        metrics["max_consecutive_opener"] = max_run
        top_repeat = metrics["top_opener_share"] > 0.25 and top_count >= 4
        if metrics["opener_unique_ratio"] < 0.55 or top_repeat or max_run >= 4:
            flags.append(flag(
                "opener_repetition",
                metrics["opener_unique_ratio"],
                "unique ratio < 0.55, one opener > 25% with 4+ uses, or 4 consecutive identical openers",
                "Sentence openings repeat in a template-like rhythm.",
                "Rewrite repeated starts; step-by-step docs may need repeated imperative openers.",
            ))

    if sentences:
        closer_count = sum(1 for s in sentences if CLOSER_RE.search(s))
        metrics["participial_closer_share"] = round(closer_count / len(sentences), 3)
        if len(sentences) >= 8 and metrics["participial_closer_share"] >= 0.15:
            flags.append(flag(
                "participial_closer_share",
                metrics["participial_closer_share"],
                ">= 0.15 over at least 8 prose sentences",
                "Many sentences end with editorial -ing consequence tails.",
                "Make the consequence concrete or cut the tail; analytical prose may allow an occasional closer.",
            ))

    return {
        "flags": flags,
        "flagged": {f["metric"]: True for f in flags},
        "metrics": metrics,
        "genre": genre,
        "prose_sentences": len(sentences),
        "prose_paragraphs": len(paragraphs),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?")
    parser.add_argument("--genre", choices=["prose", "docs", "social"], default="prose")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.path:
        path = Path(args.path)
        if not path.exists():
            print(f"Missing file: {path}", file=sys.stderr)
            return 2
        text = path.read_text(errors="replace")
    else:
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")

    # English-only graceful decline, matching banned_phrase_scan.py.
    result = scan(text, args.genre)

    # Function-word absence alone is not evidence of a foreign language
    # (imperative stacks and buzzword lists are English slop with few function
    # words). Decline only when the heuristic fails AND nothing flagged.
    if not result.get("flags") and not is_probably_english(text):
        print(json.dumps({"non_english": True, "violations": [], "flags": []}, indent=2))
        print("note: input appears non-English; scanner declined (English-only).", file=sys.stderr)
        return 0

    print(json.dumps(result, indent=2))
    return 1 if result["flags"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
