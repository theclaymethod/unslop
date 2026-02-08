#!/usr/bin/env python3
"""
Calculate readability metrics for transformed text.

Outputs:
- Flesch-Kincaid grade level
- Sentence length variance
- Word repetition score
- Paragraph length stats

Usage:
    python readability_metrics.py < input.txt
    python readability_metrics.py input.txt
"""

import sys
import re
import json
from collections import Counter
from typing import TypedDict


class ReadabilityMetrics(TypedDict):
    flesch_kincaid_grade: float
    flesch_reading_ease: float
    sentence_count: int
    word_count: int
    avg_sentence_length: float
    sentence_length_variance: float
    min_sentence_length: int
    max_sentence_length: int
    consecutive_similar_length: int
    word_repetition_score: float
    top_repeated_words: list[tuple[str, int]]
    paragraph_count: int
    avg_paragraph_length: float
    flags: list[str]


def count_syllables(word: str) -> int:
    """Count syllables in a word (approximation)."""
    word = word.lower().strip()
    if not word:
        return 0

    # Handle special cases
    if len(word) <= 3:
        return 1

    # Count vowel groups
    vowels = "aeiouy"
    count = 0
    prev_is_vowel = False

    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_is_vowel:
            count += 1
        prev_is_vowel = is_vowel

    # Adjust for silent e
    if word.endswith('e') and count > 1:
        count -= 1

    # Adjust for -le endings
    if word.endswith('le') and len(word) > 2 and word[-3] not in vowels:
        count += 1

    return max(1, count)


def split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    # Simple sentence splitting (handles common cases)
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    # Filter empty and clean up
    return [s.strip() for s in sentences if s.strip()]


def split_words(text: str) -> list[str]:
    """Split text into words."""
    # Remove punctuation except hyphens in words
    text = re.sub(r'[^\w\s-]', ' ', text)
    words = text.lower().split()
    return [w for w in words if w and not w.isdigit()]


def calculate_metrics(text: str) -> ReadabilityMetrics:
    """Calculate all readability metrics."""
    sentences = split_sentences(text)
    words = split_words(text)
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    if not sentences or not words:
        return {
            "flesch_kincaid_grade": 0,
            "flesch_reading_ease": 0,
            "sentence_count": 0,
            "word_count": 0,
            "avg_sentence_length": 0,
            "sentence_length_variance": 0,
            "min_sentence_length": 0,
            "max_sentence_length": 0,
            "consecutive_similar_length": 0,
            "word_repetition_score": 0,
            "top_repeated_words": [],
            "paragraph_count": len(paragraphs),
            "avg_paragraph_length": 0,
            "flags": ["Empty or invalid text"]
        }

    # Basic counts
    sentence_count = len(sentences)
    word_count = len(words)
    syllable_count = sum(count_syllables(w) for w in words)

    # Sentence lengths
    sentence_lengths = [len(split_words(s)) for s in sentences]
    avg_sentence_length = word_count / sentence_count if sentence_count else 0

    # Variance calculation
    if len(sentence_lengths) > 1:
        mean = sum(sentence_lengths) / len(sentence_lengths)
        variance = sum((x - mean) ** 2 for x in sentence_lengths) / len(sentence_lengths)
    else:
        variance = 0

    # Consecutive similar length sentences
    consecutive_similar = 0
    max_consecutive = 0
    for i in range(1, len(sentence_lengths)):
        # "Similar" = within 3 words of each other
        if abs(sentence_lengths[i] - sentence_lengths[i-1]) <= 3:
            consecutive_similar += 1
            max_consecutive = max(max_consecutive, consecutive_similar)
        else:
            consecutive_similar = 0

    # Flesch-Kincaid calculations
    avg_syllables_per_word = syllable_count / word_count if word_count else 0

    flesch_reading_ease = (
        206.835
        - (1.015 * avg_sentence_length)
        - (84.6 * avg_syllables_per_word)
    )

    flesch_kincaid_grade = (
        (0.39 * avg_sentence_length)
        + (11.8 * avg_syllables_per_word)
        - 15.59
    )

    # Word repetition (excluding common words)
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
        'it', 'its', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she',
        'we', 'they', 'what', 'which', 'who', 'when', 'where', 'why', 'how',
        'not', 'no', 'yes', 'if', 'then', 'else', 'so', 'as', 'than', 'just'
    }

    content_words = [w for w in words if w not in stop_words and len(w) > 2]
    word_freq = Counter(content_words)

    # Repetition score: percentage of content words appearing 3+ times
    repeated_words = {w: c for w, c in word_freq.items() if c >= 3}
    repetition_score = (
        sum(repeated_words.values()) / len(content_words) * 100
        if content_words else 0
    )

    top_repeated = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]

    # Paragraph stats
    para_lengths = [len(split_words(p)) for p in paragraphs]
    avg_para_length = sum(para_lengths) / len(para_lengths) if para_lengths else 0

    # Generate flags
    flags: list[str] = []

    if flesch_kincaid_grade > 12:
        flags.append(f"High reading level ({flesch_kincaid_grade:.1f} grade)")

    if variance < 10 and sentence_count > 3:
        flags.append("Low sentence length variance (monotonous rhythm)")

    if max_consecutive >= 3:
        flags.append(f"{max_consecutive}+ consecutive similar-length sentences")

    if repetition_score > 15:
        flags.append(f"High word repetition ({repetition_score:.1f}%)")

    if avg_sentence_length > 25:
        flags.append(f"Long average sentence length ({avg_sentence_length:.1f} words)")

    if avg_sentence_length < 8 and sentence_count > 3:
        flags.append("Very short sentences (may feel choppy)")

    if max(sentence_lengths) - min(sentence_lengths) < 5 and sentence_count > 5:
        flags.append("Sentences all similar length (AI tell)")

    return {
        "flesch_kincaid_grade": round(flesch_kincaid_grade, 1),
        "flesch_reading_ease": round(flesch_reading_ease, 1),
        "sentence_count": sentence_count,
        "word_count": word_count,
        "avg_sentence_length": round(avg_sentence_length, 1),
        "sentence_length_variance": round(variance, 1),
        "min_sentence_length": min(sentence_lengths) if sentence_lengths else 0,
        "max_sentence_length": max(sentence_lengths) if sentence_lengths else 0,
        "consecutive_similar_length": max_consecutive,
        "word_repetition_score": round(repetition_score, 1),
        "top_repeated_words": top_repeated,
        "paragraph_count": len(paragraphs),
        "avg_paragraph_length": round(avg_para_length, 1),
        "flags": flags
    }


def main() -> None:
    # Read input
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    if not text.strip():
        print(json.dumps({"error": "No input provided"}))
        sys.exit(1)

    metrics = calculate_metrics(text)
    print(json.dumps(metrics, indent=2))

    # Exit with 1 if any flags (warnings)
    sys.exit(1 if metrics["flags"] else 0)


if __name__ == "__main__":
    main()
