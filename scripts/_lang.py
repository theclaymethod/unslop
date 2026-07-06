#!/usr/bin/env python3
"""Shared cheap English-detection helpers for banned_phrase_scan.py and
structure_scan.py. Both scanners must decline the same non-English inputs, so
this table and its two functions live in exactly one place."""

import re


# A small set of high-frequency English function words used only for a cheap
# language check. The words are chosen to be distinctively English: Spanish,
# French, German, etc. rarely use them, so their share of tokens is a robust
# signal without a language-model dependency.
ENGLISH_FUNCTION_WORDS = frozenset({
    "the", "and", "is", "are", "was", "were", "of", "to", "in", "that", "it",
    "for", "with", "on", "this", "but", "not", "you", "have", "be", "as", "at",
    "or", "we", "they", "will", "would", "there", "their", "what", "which",
    "when", "from", "been", "has", "had", "its", "an", "by", "our", "your",
    "if", "than", "then", "them", "these", "those", "about", "into", "over",
    "after", "before", "how", "why", "where", "who", "can", "could", "should",
    "do", "does", "did", "so", "out", "just", "more", "most", "some", "such",
    "only", "also", "because", "while", "between", "through", "during", "being",
})


def english_function_share(text: str) -> float:
    """Share of word tokens that are common English function words."""
    tokens = re.findall(r"[a-z']+", text.lower())
    if not tokens:
        return 1.0
    hits = sum(1 for t in tokens if t in ENGLISH_FUNCTION_WORDS)
    return hits / len(tokens)


def is_probably_english(text: str, threshold: float = 0.10, min_tokens: int = 15) -> bool:
    """Cheap English detector backing a graceful non-English decline.

    Conservative on purpose: inputs below ``min_tokens`` are always treated as
    English (too little signal to decline), and ``threshold`` is low enough that
    even terse or ESL-flavored English clears it. Only prose with almost no
    English function words (i.e. another language) is declined.
    """
    tokens = re.findall(r"[a-z']+", text.lower())
    if len(tokens) < min_tokens:
        return True
    return english_function_share(text) >= threshold
