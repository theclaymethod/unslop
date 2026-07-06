#!/usr/bin/env python3
"""
Scan text for AI-isms and banned phrases.

Checks against taboo phrases list and returns violations with line numbers.
Provides suggested replacements where available.

By default, quoted examples and code snippets are ignored so the scanner
doesn't flag illustrative bad writing inside docs or tutorials. Pass
--include-quoted to scan those spans too.

Usage:
    python banned_phrase_scan.py < input.txt
    python banned_phrase_scan.py input.txt
    python banned_phrase_scan.py input.txt --include-quoted
"""

import argparse
import sys
import re
import json
from typing import TypedDict


# A small set of high-frequency English function words used only for a cheap
# language check. The words are chosen to be distinctively English: Spanish,
# French, German, etc. rarely use them, so their share of tokens is a robust
# signal without a language-model dependency. Kept identical to the set in
# structure_scan.py so both scanners decline the same inputs.
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


class Violation(TypedDict):
    phrase: str
    category: str
    severity: str
    line_number: int
    column: int
    context: str
    suggestion: str | None


def _mask_non_newlines(text: str) -> str:
    """Replace visible characters with spaces while preserving line/column layout."""
    return re.sub(r"[^\n]", " ", text)


def mask_ignored_spans(text: str, include_quoted: bool = False) -> str:
    """Mask examples and code so they don't produce false-positive matches."""
    masked = re.sub(r"```[\s\S]*?```", lambda m: _mask_non_newlines(m.group(0)), text)
    masked = re.sub(r"`[^`\n]+`", lambda m: _mask_non_newlines(m.group(0)), masked)

    if include_quoted:
        return masked

    # Markdown blockquotes are almost always cited examples rather than prose to edit.
    masked = re.sub(r"(?m)^>.*$", lambda m: _mask_non_newlines(m.group(0)), masked)

    # Double quotes only, any length, across line breaks. Single quotes are NOT
    # masked: they collide with apostrophes/emphasis and would silently hide real
    # slop inside ordinary single-quoted prose.
    quote_patterns = [
        r'"[^"]*"',
        r"“[^”]*”",
    ]
    for pattern in quote_patterns:
        masked = re.sub(pattern, lambda m: _mask_non_newlines(m.group(0)), masked)

    return masked


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    left = r"(?<![a-z0-9_-])" if phrase[0].isalnum() else ""
    right = r"(?![a-z0-9_-])" if phrase[-1].isalnum() else ""
    return re.compile(left + re.escape(phrase) + right)


# Banned phrases with categories, suggestions, and severity.
# severity: "hard" = always an AI tell; "soft" = context-dependent
BANNED_PHRASES: dict[str, dict[str, str | None]] = {
    # Throat-clearing openers
    "here's the thing:": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "the uncomfortable truth is": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "it turns out": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "let me be clear": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "the truth is": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "i'll say it again": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "i'm going to be honest": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "can we talk about": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "here's what i find interesting": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "here's the problem though": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "let's be real": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "here's the deal": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "here's what nobody tells you": {"category": "throat_clearing", "severity": "hard", "suggestion": None},

    # Emphasis crutches
    # ("Full stop." / "Period." as standalone emphasis are handled as structural
    # patterns so an ordinary sentence ending in the word "period" isn't flagged.)
    "let that sink in": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},
    "this matters because": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},
    "make no mistake": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},
    "here's why that matters": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},
    "read that again": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},
    "this is important": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},
    "this cannot be overstated": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},

    # Conclusion / sequencing scaffolding
    "in conclusion": {"category": "conclusion_scaffold", "severity": "hard", "suggestion": "Cut. State the conclusion directly."},
    "in summary": {"category": "conclusion_scaffold", "severity": "soft", "suggestion": "Cut. State the point directly."},
    "to summarize": {"category": "conclusion_scaffold", "severity": "soft", "suggestion": "Cut."},
    "firstly": {"category": "conclusion_scaffold", "severity": "soft", "suggestion": "first (or just start)"},
    "secondly": {"category": "conclusion_scaffold", "severity": "soft", "suggestion": "second (or just continue)"},
    "thirdly": {"category": "conclusion_scaffold", "severity": "soft", "suggestion": "third"},
    "ultimately,": {"category": "conclusion_scaffold", "severity": "soft", "suggestion": "Cut the filler opener."},

    # Significance inflation / cliche metaphors
    "underscore the importance": {"category": "significance_inflation", "severity": "hard", "suggestion": "show, demonstrate"},
    "underscores the importance": {"category": "significance_inflation", "severity": "hard", "suggestion": "shows, demonstrates"},
    "underscoring the importance": {"category": "significance_inflation", "severity": "hard", "suggestion": "showing"},
    "highlights the importance": {"category": "significance_inflation", "severity": "soft", "suggestion": "shows"},
    "analysts predict": {"category": "vague_attribution", "severity": "hard", "suggestion": "Name the analysts or cite the forecast."},
    "what remains clear is": {"category": "generic_conclusion", "severity": "hard", "suggestion": "State the conclusion directly."},
    "treasure trove": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "collection, source"},
    "ever-evolving": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "changing"},
    "ever-changing": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "changing"},
    "rich mosaic": {"category": "significance_inflation", "severity": "hard", "suggestion": None},
    "mosaic of": {"category": "significance_inflation", "severity": "soft", "suggestion": None},

    # False agency (inanimate subjects doing rhetorical work)
    "speak for themselves": {"category": "false_agency", "severity": "hard", "suggestion": "State the numbers and what they show."},
    "speaks for itself": {"category": "false_agency", "severity": "hard", "suggestion": "State the point directly."},
    "tells a clear story": {"category": "false_agency", "severity": "hard", "suggestion": "Say what the data shows."},
    "paints a clear picture": {"category": "false_agency", "severity": "hard", "suggestion": "Describe it directly."},

    # Significance / legacy puffery (Wikipedia: Signs of AI writing)
    "leaves a lasting impact": {"category": "significance_inflation", "severity": "hard", "suggestion": "State the specific effect."},
    "lasting impact": {"category": "significance_inflation", "severity": "soft", "suggestion": "Name the actual effect."},
    "enduring legacy": {"category": "significance_inflation", "severity": "hard", "suggestion": "State what actually persisted."},
    "lasting legacy": {"category": "significance_inflation", "severity": "hard", "suggestion": "State what actually persisted."},
    "watershed moment": {"category": "significance_inflation", "severity": "soft", "suggestion": "turning point (if sourced)"},
    "in the realm of": {"category": "significance_inflation", "severity": "hard", "suggestion": "in"},

    # Travel-brochure promotional language
    "rich cultural heritage": {"category": "promotional", "severity": "hard", "suggestion": None},
    "stunning natural beauty": {"category": "promotional", "severity": "soft", "suggestion": None},
    "picturesque": {"category": "promotional", "severity": "soft", "suggestion": None},
    "iconic": {"category": "promotional", "severity": "soft", "suggestion": None},

    # Vague attribution / weasel wording
    "has been described as": {"category": "vague_attribution", "severity": "soft", "suggestion": "Name and cite who described it."},
    "is widely regarded as": {"category": "vague_attribution", "severity": "soft", "suggestion": "Attribute to a named source."},
    "some critics argue": {"category": "vague_attribution", "severity": "soft", "suggestion": "Name the critics."},
    "observers have noted": {"category": "vague_attribution", "severity": "soft", "suggestion": "Name the observers."},

    # Editorializing
    "would be complete without": {"category": "editorializing", "severity": "hard", "suggestion": "Drop the editorial framing."},

    # Future-outlook boilerplate
    "future prospects": {"category": "conclusion_scaffold", "severity": "soft", "suggestion": "State a specific, sourced forecast."},
    "future outlook": {"category": "conclusion_scaffold", "severity": "soft", "suggestion": None},

    # Assistant / chatbot artifacts pasted into prose
    "as an ai language model": {"category": "assistant_artifact", "severity": "hard", "suggestion": "Delete — this is chatbot boilerplate."},
    "as an ai assistant": {"category": "assistant_artifact", "severity": "hard", "suggestion": "Delete — this is chatbot boilerplate."},
    "as of my last knowledge update": {"category": "assistant_artifact", "severity": "hard", "suggestion": "Delete the training-cutoff disclaimer."},

    # Academic/scientific excess vocabulary (Berens & Kobak, Science Advances 2024).
    # Mostly soft: each is legitimate but over-represented in LLM prose; flag for
    # judgment, especially when clustered.
    "elucidate": {"category": "academic_excess", "severity": "soft", "suggestion": "explain, clarify"},
    "delineate": {"category": "academic_excess", "severity": "soft", "suggestion": "describe, outline"},
    "underpin": {"category": "academic_excess", "severity": "soft", "suggestion": "support, underlie"},
    "unveil": {"category": "academic_excess", "severity": "soft", "suggestion": "show, present"},
    "seamless": {"category": "academic_excess", "severity": "soft", "suggestion": "smooth"},
    "invaluable": {"category": "academic_excess", "severity": "soft", "suggestion": "useful, important"},
    "noteworthy": {"category": "academic_excess", "severity": "soft", "suggestion": "Cut or be specific."},
    "revolutionize": {"category": "academic_excess", "severity": "soft", "suggestion": "change, improve"},
    "revolutionizing": {"category": "academic_excess", "severity": "soft", "suggestion": "changing"},

    # Formulaic academic phrases
    "it should be noted that": {"category": "throat_clearing", "severity": "hard", "suggestion": "Cut — state it directly."},
    "warrants further": {"category": "conclusion_scaffold", "severity": "hard", "suggestion": "Say what specifically to do next."},
    "holds great promise": {"category": "significance_inflation", "severity": "hard", "suggestion": "State the concrete potential."},
    "holds promise": {"category": "significance_inflation", "severity": "soft", "suggestion": "State the concrete potential."},
    "new avenues": {"category": "significance_inflation", "severity": "soft", "suggestion": "Name the specific next steps."},
    "shed new light": {"category": "significance_inflation", "severity": "soft", "suggestion": "State what was learned."},
    "to the best of our knowledge": {"category": "vague_attribution", "severity": "soft", "suggestion": "Cut unless the novelty claim is load-bearing."},
    "a growing body of": {"category": "vague_attribution", "severity": "soft", "suggestion": "Cite the specific evidence."},
    "in recent years": {"category": "filler_opener", "severity": "soft", "suggestion": "Cut the time-filler opener."},
    "with the advent of": {"category": "filler_opener", "severity": "soft", "suggestion": "when X arrived"},
    "garnered significant attention": {"category": "significance_inflation", "severity": "soft", "suggestion": "State who paid attention and why."},
    "garnered considerable attention": {"category": "significance_inflation", "severity": "soft", "suggestion": "State who paid attention and why."},
    "taken together,": {"category": "conclusion_scaffold", "severity": "soft", "suggestion": "Cut the summarizer opener."},

    # Business jargon
    # ("navigate" and "leverage" alone have legitimate literal/financial senses;
    # they're matched as jargon collocations in STRUCTURAL_PATTERNS instead.)
    "game-changer": {"category": "jargon", "severity": "hard", "suggestion": "significant, important"},
    "game changer": {"category": "jargon", "severity": "hard", "suggestion": "significant, important"},
    "deep dive": {"category": "jargon", "severity": "hard", "suggestion": "analysis, examination"},
    "take a step back": {"category": "jargon", "severity": "hard", "suggestion": "reconsider, pause"},
    "moving forward": {"category": "jargon", "severity": "hard", "suggestion": "next, from now"},
    "circle back": {"category": "jargon", "severity": "hard", "suggestion": "return to, revisit"},
    "on the same page": {"category": "jargon", "severity": "hard", "suggestion": "aligned, agreed"},
    "level up": {"category": "jargon", "severity": "hard", "suggestion": "improve, advance"},
    "bandwidth": {"category": "jargon", "severity": "soft", "suggestion": "capacity, time"},
    "synergy": {"category": "jargon", "severity": "hard", "suggestion": "cooperation, collaboration"},
    "low-hanging fruit": {"category": "jargon", "severity": "hard", "suggestion": "easy wins"},
    "pivot": {"category": "jargon", "severity": "soft", "suggestion": "change, shift"},
    "disrupt": {"category": "jargon", "severity": "soft", "suggestion": "change, challenge"},
    "scalable": {"category": "jargon", "severity": "soft", "suggestion": "expandable, growable"},
    "actionable": {"category": "jargon", "severity": "hard", "suggestion": "practical, usable"},
    "ecosystem": {"category": "jargon", "severity": "soft", "suggestion": "environment, system"},
    "touch base": {"category": "jargon", "severity": "hard", "suggestion": "talk, connect"},
    "value-add": {"category": "jargon", "severity": "hard", "suggestion": "benefit, contribution"},
    "thought leader": {"category": "jargon", "severity": "hard", "suggestion": "expert"},
    "best-in-class": {"category": "jargon", "severity": "hard", "suggestion": "leading, top-tier"},
    "cutting-edge": {"category": "jargon", "severity": "hard", "suggestion": "modern, advanced"},
    "delve into": {"category": "jargon", "severity": "hard", "suggestion": "explore, examine, look at"},
    "delve deeper": {"category": "jargon", "severity": "hard", "suggestion": "explore, examine, look at"},
    "robust": {"category": "jargon", "severity": "soft", "suggestion": "strong, solid, thorough"},
    "comprehensive": {"category": "jargon", "severity": "soft", "suggestion": "full, complete, thorough"},
    "utilize": {"category": "jargon", "severity": "hard", "suggestion": "use"},
    "facilitate": {"category": "jargon", "severity": "hard", "suggestion": "help, enable, run"},
    "spearhead": {"category": "jargon", "severity": "hard", "suggestion": "lead, start, run"},
    "streamline": {"category": "jargon", "severity": "soft", "suggestion": "simplify, speed up"},
    "multifaceted": {"category": "jargon", "severity": "hard", "suggestion": "complex, varied"},
    # ("harness" and "foster" have literal senses (a horse harness, a foster
    # family); their jargon use is matched as a collocation in STRUCTURAL_PATTERNS.)
    "enhance": {"category": "jargon", "severity": "soft", "suggestion": "improve, strengthen"},
    "align with": {"category": "jargon", "severity": "hard", "suggestion": "match, fit, support"},

    # Filler phrases
    "at its core": {"category": "filler", "severity": "hard", "suggestion": None},
    "in today's": {"category": "filler", "severity": "hard", "suggestion": None},
    "interestingly,": {"category": "filler", "severity": "hard", "suggestion": None},
    "importantly,": {"category": "filler", "severity": "hard", "suggestion": None},
    "crucially,": {"category": "filler", "severity": "hard", "suggestion": None},
    "at the end of the day": {"category": "filler", "severity": "hard", "suggestion": None},
    "when it comes to": {"category": "filler", "severity": "hard", "suggestion": "for"},
    "in a world where": {"category": "filler", "severity": "hard", "suggestion": None},
    "the reality is": {"category": "filler", "severity": "hard", "suggestion": None},
    "with that said": {"category": "filler", "severity": "hard", "suggestion": None},
    "that being said": {"category": "filler", "severity": "hard", "suggestion": None},
    "all things considered": {"category": "filler", "severity": "hard", "suggestion": None},
    "by and large": {"category": "filler", "severity": "hard", "suggestion": None},
    "for the most part": {"category": "filler", "severity": "hard", "suggestion": None},
    "to be fair": {"category": "filler", "severity": "hard", "suggestion": None},
    "to be honest": {"category": "filler", "severity": "hard", "suggestion": None},
    "needless to say": {"category": "filler", "severity": "hard", "suggestion": None},
    "it goes without saying": {"category": "filler", "severity": "hard", "suggestion": None},
    "in order to": {"category": "filler", "severity": "hard", "suggestion": "to"},
    "due to the fact that": {"category": "filler", "severity": "hard", "suggestion": "because"},
    "at this point in time": {"category": "filler", "severity": "hard", "suggestion": "now"},
    "in the event that": {"category": "filler", "severity": "hard", "suggestion": "if"},

    # Meta-commentary
    "hint:": {"category": "meta", "severity": "hard", "suggestion": None},
    "plot twist:": {"category": "meta", "severity": "hard", "suggestion": None},
    "spoiler:": {"category": "meta", "severity": "hard", "suggestion": None},
    "you already know this, but": {"category": "meta", "severity": "hard", "suggestion": None},
    "but that's another post": {"category": "meta", "severity": "hard", "suggestion": None},
    "is a feature, not a bug": {"category": "meta", "severity": "hard", "suggestion": None},
    "dressed up as": {"category": "meta", "severity": "hard", "suggestion": None},
    "let me explain": {"category": "meta", "severity": "hard", "suggestion": None},
    "to put it simply": {"category": "meta", "severity": "hard", "suggestion": None},
    "in other words": {"category": "meta", "severity": "hard", "suggestion": None},
    "if you think about it": {"category": "meta", "severity": "hard", "suggestion": None},

    # Performative emphasis
    "creeps in": {"category": "performative", "severity": "hard", "suggestion": "appears, emerges"},
    "i promise": {"category": "performative", "severity": "hard", "suggestion": None},
    "they exist, i promise": {"category": "performative", "severity": "hard", "suggestion": None},
    "this is genuinely": {"category": "performative", "severity": "hard", "suggestion": None},
    "actually looks like": {"category": "performative", "severity": "hard", "suggestion": None},
    "trust me": {"category": "performative", "severity": "hard", "suggestion": None},
    "believe me": {"category": "performative", "severity": "hard", "suggestion": None},

    # Significance / legacy inflation
    "stands as a testament": {"category": "significance_inflation", "severity": "hard", "suggestion": None},
    "testament to": {"category": "significance_inflation", "severity": "hard", "suggestion": "proof of, shows"},
    "pivotal moment": {"category": "significance_inflation", "severity": "hard", "suggestion": None},
    "indelible mark": {"category": "significance_inflation", "severity": "hard", "suggestion": None},
    "rich tapestry": {"category": "significance_inflation", "severity": "hard", "suggestion": None},
    "rich history": {"category": "significance_inflation", "severity": "soft", "suggestion": "long history"},
    "a legacy of": {"category": "significance_inflation", "severity": "hard", "suggestion": None},
    "cornerstone of": {"category": "significance_inflation", "severity": "hard", "suggestion": "key part of, foundation of"},
    "groundbreaking": {"category": "significance_inflation", "severity": "hard", "suggestion": "new, first, original"},
    "transformative": {"category": "significance_inflation", "severity": "hard", "suggestion": "major, significant"},
    "trailblazing": {"category": "significance_inflation", "severity": "hard", "suggestion": "first, pioneering"},
    "seminal": {"category": "significance_inflation", "severity": "soft", "suggestion": "influential, important"},

    # Promotional language
    "nestled": {"category": "promotional", "severity": "hard", "suggestion": "located, situated"},
    # ("boasts" is promotional only with a boastful complement; see STRUCTURAL_PATTERNS.)
    "breathtaking": {"category": "promotional", "severity": "hard", "suggestion": None},
    "must-visit": {"category": "promotional", "severity": "hard", "suggestion": None},
    "in the heart of": {"category": "promotional", "severity": "hard", "suggestion": "in central, in downtown"},
    "world-class": {"category": "promotional", "severity": "hard", "suggestion": None},
    "state-of-the-art": {"category": "promotional", "severity": "hard", "suggestion": "modern, current"},
    "second to none": {"category": "promotional", "severity": "hard", "suggestion": None},
    "a hidden gem": {"category": "promotional", "severity": "hard", "suggestion": None},
    "bustling": {"category": "promotional", "severity": "hard", "suggestion": "busy, active"},
    "renowned for": {"category": "promotional", "severity": "hard", "suggestion": "known for"},
    "a beacon of": {"category": "promotional", "severity": "hard", "suggestion": None},

    # Vague attributions
    "experts argue": {"category": "vague_attribution", "severity": "hard", "suggestion": "name the experts or cut"},
    "industry reports suggest": {"category": "vague_attribution", "severity": "hard", "suggestion": "cite the report or cut"},
    "some critics": {"category": "vague_attribution", "severity": "hard", "suggestion": "name them or cut"},
    "many believe": {"category": "vague_attribution", "severity": "hard", "suggestion": None},
    "it is widely regarded": {"category": "vague_attribution", "severity": "hard", "suggestion": None},
    "according to experts": {"category": "vague_attribution", "severity": "hard", "suggestion": "name the experts"},
    "observers note": {"category": "vague_attribution", "severity": "hard", "suggestion": None},
    "studies show": {"category": "vague_attribution", "severity": "hard", "suggestion": "cite the study"},
    "research suggests": {"category": "vague_attribution", "severity": "hard", "suggestion": "cite the research"},

    # Copula avoidance
    # ("serves as a" / "stands as a" have literal-function senses (a room serves
    # as a kitchen); the inflated significance use is matched in STRUCTURAL_PATTERNS.)
    "represents a": {"category": "copula_avoidance", "severity": "soft", "suggestion": "is a"},
    "constitutes a": {"category": "copula_avoidance", "severity": "hard", "suggestion": "is a"},
    "functions as a": {"category": "copula_avoidance", "severity": "hard", "suggestion": "is a"},
    "operates as a": {"category": "copula_avoidance", "severity": "hard", "suggestion": "is a"},

    # Communication artifacts
    "i hope this helps": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "certainly!": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "great question": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "that's a great point": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "happy to help": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "let me know if you need anything else": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "i'd be happy to": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "i am happy to address": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "i am open to any suggestions": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "i am open to feedback": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "i would appreciate any feedback": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "i am willing to address": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "i assure you": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "demonstrate my commitment": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "with the utmost care": {"category": "communication_artifact", "severity": "hard", "suggestion": None},
    "if you have any concerns or suggestions": {"category": "communication_artifact", "severity": "hard", "suggestion": None},

    # Knowledge-cutoff disclaimers
    "as of my last": {"category": "knowledge_cutoff", "severity": "hard", "suggestion": None},
    "as of my knowledge cutoff": {"category": "knowledge_cutoff", "severity": "hard", "suggestion": None},
    "based on my training data": {"category": "knowledge_cutoff", "severity": "hard", "suggestion": None},
    "based on available information": {"category": "knowledge_cutoff", "severity": "hard", "suggestion": None},

    # Generic positive conclusions
    "the future looks bright": {"category": "generic_conclusion", "severity": "hard", "suggestion": None},
    "exciting times lie ahead": {"category": "generic_conclusion", "severity": "hard", "suggestion": None},
    "only time will tell": {"category": "generic_conclusion", "severity": "hard", "suggestion": None},
    "one thing is certain": {"category": "generic_conclusion", "severity": "hard", "suggestion": None},
    "continues to evolve": {"category": "generic_conclusion", "severity": "hard", "suggestion": None},
    "continues to shape": {"category": "generic_conclusion", "severity": "hard", "suggestion": None},
    "poised for growth": {"category": "generic_conclusion", "severity": "hard", "suggestion": None},
    "remains to be seen": {"category": "generic_conclusion", "severity": "hard", "suggestion": None},

    # AI vocabulary (individual words)
    "interplay": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "interaction, connection"},
    "intricate": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "complex, detailed"},
    "tapestry of": {"category": "ai_vocabulary", "severity": "hard", "suggestion": None},
    "paramount": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "important, critical"},
    "pertaining to": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "about, regarding"},
    "aforementioned": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "this, that, the"},
    "henceforth": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "from now on"},
    "whereby": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "where, by which"},
    "therein": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "in it, there"},
    "burgeoning": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "growing, expanding"},
    "myriad": {"category": "ai_vocabulary", "severity": "soft", "suggestion": "many, numerous"},
    "plethora": {"category": "ai_vocabulary", "severity": "soft", "suggestion": "many, lots of"},
    "encompass": {"category": "ai_vocabulary", "severity": "soft", "suggestion": "include, cover"},
    "moreover": {"category": "ai_vocabulary", "severity": "soft", "suggestion": "also, and"},
    "furthermore": {"category": "ai_vocabulary", "severity": "soft", "suggestion": "also, and"},
    "nevertheless": {"category": "ai_vocabulary", "severity": "soft", "suggestion": "still, but, yet"},
    "ubiquitous": {"category": "ai_vocabulary", "severity": "soft", "suggestion": "everywhere, common"},
    "nuanced": {"category": "ai_vocabulary", "severity": "soft", "suggestion": "subtle, complex"},
    "meticulous": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "careful, thorough"},
    "meticulously": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "carefully, thoroughly"},
    "emphasizing": {"category": "ai_vocabulary", "severity": "soft", "suggestion": "stressing, focusing on"},
    "enduring": {"category": "ai_vocabulary", "severity": "soft", "suggestion": "lasting, long-standing"},
    "vibrant": {"category": "ai_vocabulary", "severity": "soft", "suggestion": "lively, busy, colorful"},

    # Commonly missed AI tells
    "resonates with": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "matters to, connects with"},
    "resonate with": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "matters to, connects with"},
    "at the intersection of": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "where X meets Y, or just state both"},
    "it's no secret that": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "speaks volumes": {"category": "significance_inflation", "severity": "hard", "suggestion": "shows, demonstrates"},
    "the elephant in the room": {"category": "performative", "severity": "hard", "suggestion": "state the problem directly"},
    "it begs the question": {"category": "performative", "severity": "hard", "suggestion": "this raises, or just ask the question"},
    "a deep understanding": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "understanding, knowledge of"},
    "double-edged sword": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "has tradeoffs, cuts both ways"},
    "sends a clear message": {"category": "significance_inflation", "severity": "hard", "suggestion": "shows, signals"},
    "here's why": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "let's dive in": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "let's unpack": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "let's explore": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "let's break this down": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "let's take a look": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "let's examine": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "the bottom line": {"category": "filler", "severity": "hard", "suggestion": None},
    "the key takeaway": {"category": "filler", "severity": "hard", "suggestion": None},
    "it's clear that": {"category": "filler", "severity": "hard", "suggestion": None},
    "what's clear is": {"category": "filler", "severity": "hard", "suggestion": None},
    "it's a no-brainer": {"category": "performative", "severity": "hard", "suggestion": None},
    "at the forefront of": {"category": "promotional", "severity": "hard", "suggestion": "leading, ahead in"},
    "a testament to": {"category": "significance_inflation", "severity": "hard", "suggestion": "shows, proves"},
    "needless to say": {"category": "filler", "severity": "hard", "suggestion": None},
    "navigating the complexities": {"category": "jargon", "severity": "hard", "suggestion": "handling, dealing with"},
    "in an era of": {"category": "filler", "severity": "hard", "suggestion": None},
    "the fabric of": {"category": "significance_inflation", "severity": "hard", "suggestion": "part of, within"},
    "it's worth mentioning": {"category": "filler", "severity": "hard", "suggestion": None},
    "sheds light on": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "explains, reveals, shows"},
    "strikes a balance": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "balances"},
    "paints a picture": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "shows, describes"},
    "raises the bar": {"category": "significance_inflation", "severity": "hard", "suggestion": "improves, sets a new standard"},
    "food for thought": {"category": "performative", "severity": "hard", "suggestion": None},
    "the million-dollar question": {"category": "performative", "severity": "hard", "suggestion": "the question is"},
    "this is where it gets interesting": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "buckle up": {"category": "performative", "severity": "hard", "suggestion": None},
    "spoiler alert": {"category": "meta", "severity": "hard", "suggestion": None},
    "pro tip": {"category": "meta", "severity": "hard", "suggestion": None},
    "hot take": {"category": "meta", "severity": "hard", "suggestion": None},
    "unpopular opinion": {"category": "meta", "severity": "hard", "suggestion": None},
    "a closer look": {"category": "filler", "severity": "hard", "suggestion": None},

    # Reader-steering frames and vague endorsements
    "here's what's interesting": {"category": "reader_steering", "severity": "hard", "suggestion": "Lead with the actual point"},
    "here's what caught my eye": {"category": "reader_steering", "severity": "hard", "suggestion": "State the observation directly"},
    "here's what stood out": {"category": "reader_steering", "severity": "hard", "suggestion": "State what matters directly"},
    "worth reading": {"category": "vague_endorsement", "severity": "soft", "suggestion": "Say why it's worth reading"},
    "worth paying attention to": {"category": "vague_endorsement", "severity": "soft", "suggestion": "Say why it matters"},
    "worth a look": {"category": "vague_endorsement", "severity": "soft", "suggestion": "Say what's useful about it"},
    "worth exploring": {"category": "vague_endorsement", "severity": "soft", "suggestion": "Say what the reader will learn"},
    "worth checking out": {"category": "vague_endorsement", "severity": "soft", "suggestion": "Say what makes it useful"},
    "worth your time": {"category": "vague_endorsement", "severity": "soft", "suggestion": "Say why it matters"},

    # Reasoning-chain leakage and acknowledgment loops
    "let me think step by step": {"category": "reasoning_chain", "severity": "hard", "suggestion": "State the conclusion, then the evidence"},
    "breaking this down": {"category": "reasoning_chain", "severity": "soft", "suggestion": "State the point directly"},
    "to approach this systematically": {"category": "reasoning_chain", "severity": "hard", "suggestion": "Cut the scaffolding and make the point"},
    "here's my thought process": {"category": "reasoning_chain", "severity": "hard", "suggestion": "Remove internal-monologue framing"},
    "working through this logically": {"category": "reasoning_chain", "severity": "hard", "suggestion": "State the argument directly"},
    "you're asking about": {"category": "acknowledgment_loop", "severity": "hard", "suggestion": "Just answer directly"},
    "to answer your question": {"category": "acknowledgment_loop", "severity": "hard", "suggestion": "Just answer directly"},
    "the question of whether": {"category": "acknowledgment_loop", "severity": "soft", "suggestion": "State the issue directly"},

    # Novelty inflation
    "introduced a term": {"category": "novelty_inflation", "severity": "soft", "suggestion": "Describe what they explained instead"},
    "coined the phrase": {"category": "novelty_inflation", "severity": "soft", "suggestion": "Describe the concept or cite the source"},
    "a concept nobody's naming": {"category": "novelty_inflation", "severity": "hard", "suggestion": "Describe the concept without claiming novelty"},
    "a problem nobody talks about": {"category": "novelty_inflation", "severity": "hard", "suggestion": "Describe the problem without fake scarcity"},
    "the insight everyone's missing": {"category": "novelty_inflation", "severity": "hard", "suggestion": "Make the argument without hype framing"},
    "what nobody tells you about": {"category": "novelty_inflation", "severity": "hard", "suggestion": "State the point directly"},

    # Rhetorical question openers
    "what does this mean for": {"category": "rhetorical_question", "severity": "soft", "suggestion": "Answer directly instead of teeing it up"},
    "why should you care": {"category": "rhetorical_question", "severity": "hard", "suggestion": "State why it matters directly"},
    "what's next?": {"category": "rhetorical_question", "severity": "soft", "suggestion": "State the next step directly"},

    # Numbered-list inflation
    "three key takeaways": {"category": "numbered_list_inflation", "severity": "soft", "suggestion": "List only the points that matter"},
    "five things to know": {"category": "numbered_list_inflation", "severity": "soft", "suggestion": "List the points without hype framing"},
    "top seven": {"category": "numbered_list_inflation", "severity": "soft", "suggestion": "Use the real count only if it matters"},
}

# Structural patterns (regex)
STRUCTURAL_PATTERNS: list[dict[str, str]] = [
    # Standalone "Period." / "Full stop." for emphasis — only when it stands as
    # its own sentence, not when a clause merely ends in the word "period".
    {
        "pattern": r"(?:^|[.!?]\s+)(?:full stop|period)\.",
        "category": "emphasis_crutch",
        "severity": "hard",
        "suggestion": "Cut the one-word emphasis sentence."
    },
    # "The real <noun> is ..." throat-clearing (not "the real estate market").
    {
        "pattern": r"\bthe real \w+ (?:is|isn't|was|wasn't|remains)\b",
        "category": "throat_clearing",
        "severity": "hard",
        "suggestion": "State it directly."
    },
    # "<abstract noun> is/are real" — the meme-derived emphasis closer ("the
    # struggle is real", "the stakes are real", "the mechanic is real"). It
    # asserts significance instead of showing it. Restricted to abstract-emphasis
    # subjects so the literal authentication sense ("the painting is real, not a
    # forgery", "is this offer real?") is spared. Soft: it's a judgment call.
    {
        "pattern": r"(?i)\b(?:the\s+|that\s+|this\s+)?(?:struggle|stakes|pain|threat|risk|danger|fear|hype|magic|hustle|grind|stress|pressure|burnout|concern|consequences|impact|tension|anxiety|disconnect|divide|need|demand|love|chemistry|connection|mechanic|feels?)\s+(?:is|are|was|were)\s+(?:very\s+|so\s+|all\s+too\s+)?real\b",
        "category": "emphasis_crutch",
        "severity": "soft",
        "suggestion": "Cut the meme emphasis; state what is actually at stake."
    },
    # Jargon collocations: flag the business sense, spare the literal/financial one.
    {
        "pattern": r"\bleverag(?:e|es|ed|ing)\s+(?:our\s+|your\s+|their\s+|its\s+|the\s+)?(?:synerg|core\s+compet|strength|expertise|capabilit|technolog|resource|data\b|ai\b|platform|ecosystem|network|power\s+of)",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "use, apply"
    },
    {
        "pattern": r"\bnavigat(?:e|es|ed|ing)\s+(?:the\s+|this\s+|these\s+)?(?:complex|challeng|landscape|nuance|intricac|water|terrain|maze|minefield|uncertaint|world\s+of|ever-)",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "handle, address, manage"
    },
    {
        "pattern": r"\bharness(?:es|ed|ing)?\s+(?:the\s+|its\s+|their\s+|our\s+)?(?:power|potential|strength|capabilit|energy|momentum|force|full\s+)",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "use, tap, apply"
    },
    {
        "pattern": r"\bfoster(?:s|ed|ing)?\s+(?:a\s+|an\s+|greater\s+|deeper\s+|stronger\s+)?(?:culture|collaboration|innovation|sense\s+of|community|environment|growth|engagement|inclusion|creativity|dialogue|connection|belonging)",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "build, encourage, create"
    },
    {
        "pattern": r"\bunpack(?:s|ed|ing)?\s+(?:the\s+|this\s+|that\s+|our\s+)?(?:idea|argument|assumption|implication|implications|nuance|meaning|claim|concept|topic|dynamic|why|how|what)\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "explain, examine"
    },
    {
        "pattern": r"\blean(?:s|ed|ing)?\s+into\s+(?:the\s+|this\s+|that\s+|our\s+|your\s+)?(?:strength|strengths|opportunity|moment|change|uncertainty|discomfort|messiness|complexity|challenge|future)\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "accept, use, emphasize"
    },
    {
        "pattern": r"\bdoubl(?:e|es|ed|ing)\s+down\s+on\s+(?:the\s+|this\s+|that\s+|our\s+|your\s+|its\s+|their\s+|a\s+|an\s+)?(?:strategy|approach|investment|bet|commitment|vision|message|plan|position)\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "commit, increase"
    },
    {
        "pattern": r"\bshowcas(?:e|es|ed|ing)\s+(?:the\s+|this\s+|that\s+|our\s+|your\s+|their\s+)?(?:team|results|work|value|impact|capabilities|features|strengths|expertise|innovation)\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "show, demonstrate"
    },
    {
        "pattern": r"\bbolster(?:s|ed|ing)?\s+(?:the\s+|this\s+|that\s+|our\s+|your\s+)?(?:argument|case|claim|confidence|credibility|support|position|strategy|effort|security)\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "support, strengthen"
    },
    {
        "pattern": r"\bgarner(?:s|ed|ing)?\s+(?:significant\s+|considerable\s+|widespread\s+)?(?:attention|support|praise|interest|acclaim|criticism|votes)\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "get, earn, attract"
    },
    {
        "pattern": r"\bstakeholders?\b[^.!?\n]{0,50}\b(?:buy-in|alignment|engagement|feedback|input|management)\b|\b(?:buy-in|alignment|engagement)\b[^.!?\n]{0,50}\bstakeholders?\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "people involved"
    },
    {
        "pattern": r"\b(?:in\s+)?(?:today's|modern|contemporary|business|marketing|tech|ai|media|education|healthcare|finance|industry)\s+landscape\b|\bthe\s+(?:business|marketing|tech|ai|media|education|healthcare|finance|industry)\s+landscape\s+of\b|\bthe\s+landscape\s+of\s+(?:modern\s+|today's\s+|contemporary\s+)?(?:marketing|business|tech\w*|ai|work|media|education|healthcare|finance|the industry)\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "situation, field, market"
    },
    {
        "pattern": r"\bload-bearing\s+(?:part|piece|point|claim|idea|insight|assumption|detail|context|constraint|requirement|decision|argument|premise|section|paragraph|sentence|word|term|concept)\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "essential, important, necessary"
    },
    {
        "pattern": r"\b(?:our|the|a)\s+wedge\s+into\s+the\s+(?:\w+\s+)?(?:market|enterprise|industry|segment|category|account|vertical)s?\b|\bas\s+a\s+wedge\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "opening, angle, advantage, entry point"
    },
    {
        "pattern": r"\b(?:the\s+)?substrate\s+(?:for|of)\s+(?:everything|all|our|the\s+(?:company|business|movement|conversation|debate|work))\b|\bcultural\s+substrate\b",
        "category": "ai_vocabulary",
        "severity": "soft",
        "suggestion": "foundation, base, layer"
    },
    # Bare unattributed "research indicates/shows/suggests" — the same vague_attribution
    # move as "studies show": authority invoked with no source. Gated on the BARE,
    # clause-initial form (sentence start or after .!?;:) where "research" sits
    # immediately before the verb. An attributive phrase ("Research by the Kaiser group
    # indicates …") or a leading possessive ("Our research indicates …") breaks the
    # adjacency/anchor, so a named study or a concrete first-person claim stays clean.
    # Soft: attribution is a judgment call and the anchor is a heuristic. Matched on
    # lowercased text like every structural pattern.
    {
        "pattern": r"(?:^|[.!?;:]\s+)research\s+(?:indicates|shows|suggests)\b",
        "category": "vague_attribution",
        "severity": "soft",
        "suggestion": "Cite the specific research or name the source."
    },
    # Promotional "boasts <boastful complement>" (not "boasts a capacity of 50,000").
    {
        "pattern": r"\bboasts?\s+(?:a\s+|an\s+)?(?:world-class|state-of-the-art|cutting-edge|impressive|stunning|robust|comprehensive|unparalleled|rich|vibrant|array of|host of|range of|wealth of|plethora)",
        "category": "promotional",
        "severity": "hard",
        "suggestion": "has"
    },
    # "plays a crucial role / pivotal part" — the canonical AI academic frame.
    {
        "pattern": r"\bplays?\s+an?\s+(?:crucial|key|vital|pivotal|significant|central|important|critical|defining|major)\s+(?:role|part)\b",
        "category": "significance_inflation",
        "severity": "soft",
        "suggestion": "State the specific effect, not that something 'plays a role'."
    },
    # "a deeper/more nuanced understanding of" — inflated stand-in for "understanding".
    {
        "pattern": r"\ba\s+(?:deeper|better|more\s+nuanced|comprehensive|fuller|richer)\s+understanding\s+of\b",
        "category": "significance_inflation",
        "severity": "soft",
        "suggestion": "Just 'understanding of', or state what is understood."
    },
    # "highlights/emphasizes the need/importance of" — boilerplate significance closer.
    {
        "pattern": r"\b(?:highlight|emphasiz|reflect|underscor|stress)\w*\s+the\s+(?:need|importance)\s+(?:for|of)\b",
        "category": "significance_inflation",
        "severity": "soft",
        "suggestion": "State the takeaway directly."
    },
    {
        "pattern": r"\bit(?:'s| is)\s+(?:worth noting|(?:also\s+)?important to note)\b",
        "category": "filler",
        "severity": "hard",
        "suggestion": "Cut and state the point directly."
    },
    {
        "pattern": r"\bnotwithstanding\b(?!\s+(?:anything\s+to\s+the\s+contrary|the\s+foregoing|any(?:thing)?\s+(?:other\s+)?provision|section|clause|subsection|anything\s+in))",
        "category": "ai_vocabulary",
        "severity": "soft",
        "suggestion": "despite, regardless"
    },
    # Reader-addressing essay frame ("In this article, we will explore …").
    {
        "pattern": r"(?i)\bin this (?:article|section|post|guide|chapter|paper),?\s+(?:we|i)\s+(?:will|'ll|are going to|shall)\b",
        "category": "reader_addressing",
        "severity": "soft",
        "suggestion": "Drop the meta-framing; just deliver the content."
    },
    # Inflated "serves/stands as a <significance noun>" (not "serves as a kitchen").
    {
        "pattern": r"\b(?:acts|serves|stands|stood)\s+as\s+(?:a|an|the)\s+(?:testament|reminder|symbol|beacon|foundation|cornerstone|gateway|catalyst|bridge|hub|springboard|window|monument|hallmark|blueprint|cautionary|stark|powerful|shining|prime example|case study|model for)\b",
        "category": "copula_avoidance",
        "severity": "hard",
        "suggestion": "Use 'is', and state the specific fact."
    },
    # Anti-slop register tells: the skill's OWN house style. De-slopped text often
    # over-relies on bare fragment contrasts ("Not the technology. The people.") and
    # staccato runs of tiny sentences. These read as "LinkedIn-influencer / AI-
    # humanizer voice" — a tell in their own right — but the binary_contrast regex
    # only caught the full-clause form. Soft: judgment call, but it must be visible.
    {
        "pattern": r"(?im)(?:^|[.!?]\s+)(?:not|no)\b[^.!?]{0,28}[.!?]\s+(?:the\s+|it'?s?\s+|that'?s?\s+)?[a-z][^.!?]{0,28}[.!?]",
        "category": "anti_slop_register",
        "severity": "soft",
        "suggestion": "Bare fragment contrast ('Not X. Y.') is its own AI tell. Use one varied sentence."
    },
    {
        "pattern": r"(?:\b[\w'’]+(?:\s+[\w'’]+){0,4}[.!?]\s+){2,}[\w'’]+(?:\s+[\w'’]+){0,4}[.!?]",
        "category": "anti_slop_register",
        "severity": "soft",
        "suggestion": "Three+ consecutive tiny sentences is staccato AI cadence. Vary sentence length."
    },
    {
        "pattern": r"not because .+?\. because",
        "category": "binary_contrast",
        "severity": "hard",
        "suggestion": "State the actual reason directly"
    },
    {
        "pattern": r"isn't the problem\. .+ is\.",
        "category": "binary_contrast",
        "severity": "hard",
        "suggestion": "State the problem directly"
    },
    {
        "pattern": r"feels like .+?\. it's actually",
        "category": "binary_contrast",
        "severity": "hard",
        "suggestion": "State the reality directly"
    },
    {
        "pattern": r"\. that's it\. that's the",
        "category": "dramatic_fragment",
        "severity": "hard",
        "suggestion": "Use complete sentences"
    },
    {
        "pattern": r"(?:^|[.!?]\s+|\n)\s*the\s+[a-z][a-z\-']*(?:\s+[a-z][a-z\-']*){0,2}\s+loop\.",
        "category": "dramatic_fragment",
        "severity": "hard",
        "suggestion": "'The ___ loop.' is a dramatic fragment. Rewrite as a complete sentence or cut."
    },
    {
        "pattern": r"\b(?:\w+\s+(?:isn'?t|aren'?t|is\s+not|are\s+not)|(?:it|this|that)'s\s+not)\s+[^.\n]{1,80}\.\s+it'?s\s+[^.\n]{1,120}",
        "category": "binary_contrast",
        "severity": "hard",
        "suggestion": "'X isn't Y. It's Z.' is a formulaic contrast. State Z directly."
    },
    {
        "pattern": r"\b(?:it|this|that)'s not\b[^.!?\n]{1,60}[.!?]\s+(?:it|this|that)'s not\b",
        "category": "negative_listing",
        "severity": "hard",
        "suggestion": "Replace the repeated negative listing with the affirmative point."
    },
    {
        "pattern": r"\b\w+\s+things\.\s+one\s+thing\b",
        "category": "dramatic_fragment",
        "severity": "hard",
        "suggestion": "'X things. One thing.' is a dramatic reduction cliche. State the single point directly."
    },
    {
        "pattern": r"what if i told you",
        "category": "rhetorical_setup",
        "severity": "hard",
        "suggestion": "Make the point directly"
    },
    {
        "pattern": r"here's what i mean:",
        "category": "rhetorical_setup",
        "severity": "hard",
        "suggestion": "Remove and state directly"
    },
    {
        "pattern": r"think about it:",
        "category": "rhetorical_setup",
        "severity": "hard",
        "suggestion": "Remove - condescending"
    },
    {
        "pattern": r"and that's okay\.",
        "category": "unnecessary_permission",
        "severity": "hard",
        "suggestion": "Remove - unnecessary reassurance"
    },
    {
        "pattern": r",\s+(?:highlighting|showcasing|underscoring|fostering|demonstrating|reflecting|signaling)\b",
        "category": "superficial_ing",
        "severity": "hard",
        "suggestion": "Delete participial clause or make it a separate sentence with reasoning"
    },
    {
        "pattern": r"not only .+? but also",
        "category": "negative_parallelism",
        "severity": "hard",
        "suggestion": "State both points directly"
    },
    {
        "pattern": r"it's not just about .+?,\s*it's about",
        "category": "negative_parallelism",
        "severity": "hard",
        "suggestion": "State what it's about directly"
    },
    {
        "pattern": r"\b(?:it'?s not|it\s+is\s+not|this is not|that'?s not|isn'?t|is\s+not|wasn'?t|was\s+not|aren'?t|are\s+not|weren'?t|were\s+not)\s+just\b[^.;!?\n]{1,60}[,;—–-]\s*(?:it'?s|it (?:is|was)|they'?re|that'?s)\b",
        "category": "negative_parallelism",
        "severity": "hard",
        "suggestion": "State both points directly"
    },
    {
        "pattern": r"\bnot merely\s+[^,.\n]{1,60},?\s+but\b",
        "category": "negative_parallelism",
        "severity": "hard",
        "suggestion": "State the affirmative point directly."
    },
    {
        "pattern": r"\bnot\s+[^,\n]{1,40},\s+not\s+[^,\n]{1,40},\s+(?:just|but)\s",
        "category": "negative_parallelism",
        "severity": "hard",
        "suggestion": "Stacked negation for false drama. State the affirmative directly."
    },
    {
        "pattern": r"\bis not\b.+?\.\s*rather,\s+it\s+(?:is|constitutes|represents)",
        "category": "negative_parallelism",
        "severity": "hard",
        "suggestion": "Drop the negation + 'rather' setup. State what it is."
    },
    {
        "pattern": r"from .+? to .+?,\s*from .+? to",
        "category": "false_range",
        "severity": "hard",
        "suggestion": "Pick the most relevant items instead of stacking ranges"
    },
    {
        "pattern": r"despite its .+?,\s*.+? faces challenges",
        "category": "formulaic_challenges",
        "severity": "hard",
        "suggestion": "Restructure - formulaic concession pattern"
    },
    {
        "pattern": r"however,?\s*it is not without its challenges",
        "category": "formulaic_challenges",
        "severity": "hard",
        "suggestion": "Be specific about the actual challenges"
    },
    {
        "pattern": r"while .+?,\s*.+? remains a concern",
        "category": "formulaic_challenges",
        "severity": "hard",
        "suggestion": "State the concern directly without balanced-template framing"
    },
    {
        "pattern": r"(?:while|although)\s+[^.\n]{1,120}?,\s*[^.\n]{1,120}?\b(?:remains|is still)\b[^.\n]{0,80}\b(?:challenge|concern|open question|limitation|constraint)",
        "category": "false_concession",
        "severity": "hard",
        "suggestion": "Drop the fake balance. State the tradeoff directly."
    },
    {
        "pattern": r"paving the way for",
        "category": "superficial_ing",
        "severity": "hard",
        "suggestion": "State the consequence directly"
    },

    # Contrastive-definition tail: "<...>, not <noun phrase>." — the affirm-then-
    # negate template ("The design system is a build step, not an output." /
    # "Failures lived in the shared substrate, not the models."). Soft: it is a
    # judgment call and a factual correction ("born in Paris, not London") can look
    # the same. Two guards keep the common legitimate corrections out:
    #   * imperative-first lookahead spares instructions ("Use pnpm, not npm.")
    #   * requiring a letter-led noun after "not" spares numeric corrections
    #     ("Latency fell 40%, not 4%.")
    # A minimum lead length spares tiny fragments ("Cats, not dogs."). A set of
    # fixed-width negative lookbehinds spares the authentication idiom, where the
    # affirmed side is a genuineness adjective ("The painting is real, not a
    # forgery." / "The signature is genuine, not a copy.").
    {
        "pattern": r"(?:^|[.!?]\s+)(?!(?:use|run|type|call|pass|set|do|say|pick|choose|write|add|prefer|ship|keep|drop|make|see|note|try|go|get|put|give|take|send)\b)[a-z][^.!?\n]{10,}(?<!real)(?<!genuine)(?<!authentic)(?<!fake)(?<!true)(?<!false)(?<!original),\s+not\s+(?:a\s+|an\s+|the\s+|its\s+|your\s+|our\s+|their\s+|this\s+|that\s+)?[a-z][^.!?\n]{0,45}[.!?]",
        "category": "contrastive_definition",
        "severity": "soft",
        "suggestion": "'X, not Y.' contrastive tail manufactures drama. State the positive claim on its own."
    },
    # Contrastive-definition, negation-first comma variant: "X isn't a Y, it's a Z."
    # The period-split form ("X isn't Y. It's Z.") is already caught; this covers the
    # comma-joined skeleton, which is almost always the same tell.
    {
        "pattern": r"\b(?:isn'?t|aren'?t|wasn'?t|weren'?t)\s+(?:just\s+|only\s+|merely\s+|even\s+)?(?:a\s+|an\s+|the\s+)?[^,.!?\n]{2,45},\s+(?:it'?s|it\s+is|they'?re|that'?s|these\s+are|those\s+are)\s+[^.!?\n]{1,45}[.!?]",
        "category": "contrastive_definition",
        "severity": "soft",
        "suggestion": "'X isn't a Y, it's a Z.' is a formulaic contrast. State what it is directly."
    },
    # Two-beat parallel imperative slogan: two consecutive <=4-word sentences that
    # both start with an imperative verb ("Emit 1,100 tokens. Ship 237KB."). Encoded
    # conservatively via a curated verb list so subject-first pairs ("Reviewers
    # click. The agent fixes.") and imperative+noun-list ("Write once. Page, deck,
    # poster, video.") do NOT fire. Soft: a real two-step instruction can look the
    # same, so this is a judgment flag.
    {
        "pattern": r"(?:^|[.!?]\s+)\b(?:ship|emit|build|deploy|render|run|write|generate|export|compile|parse|cache|serve|stream|batch|encode|decode|paste|scan|flag|track|save|load|push|pull|spin|boot|wire|mount|patch|sync|scale|send|log|test|check|match|store|count|map|route|split|merge|trim|hash|sign|mint|queue|drop|cut|keep|skip|pick)\b(?:\s+[^\s.!?]+){1,3}[.!?]\s+\b(?:ship|emit|build|deploy|render|run|write|generate|export|compile|parse|cache|serve|stream|batch|encode|decode|paste|scan|flag|track|save|load|push|pull|spin|boot|wire|mount|patch|sync|scale|send|log|test|check|match|store|count|map|route|split|merge|trim|hash|sign|mint|queue|drop|cut|keep|skip|pick)\b(?:\s+[^\s.!?]+){1,3}[.!?]",
        "category": "imperative_slogan",
        "severity": "soft",
        "suggestion": "Two back-to-back tiny imperative sentences ('Emit X. Ship Y.') is a slogan cadence tell. Use one sentence."
    },
    # Repeated "<plural noun> that <verb>." headline fragment. A single instance can
    # be intentional; the tell is FREQUENCY, so this fires only at 2+ occurrences in
    # one document (min_matches). Leading token restricted to a plural-ish word
    # ending in "s" so ordinary sentences ("Note that this works.") are spared.
    {
        "pattern": r"(?:^|[.!?]\s+)[a-z][\w'’-]*s\s+that\s+[^.!?\n]{1,40}[.!?]",
        "category": "fragment_template",
        "severity": "soft",
        "suggestion": "Repeated '<plural noun> that <verb>.' fragments are an AI cadence tell. Vary the structure or use full sentences.",
        "min_matches": "2"
    },
    # Headline slogan cadence (DOCUMENT-LEVEL): the two-beat "Short statement. Short
    # statement." rhythm repeated across a document's HEADLINES. One such headline is
    # voice; the same cadence on 3+ standalone lines is template grammar, so this fires
    # only at min_matches=3. Generalizes imperative_slogan (which requires an imperative
    # curated verb first) to ANY line built wholly from 2-4 short sentences, each <=5
    # words and ending in terminal punctuation — including noun-phrase beats ("One
    # command. A real URL.") that imperative_slogan deliberately spares.
    #
    # Line-shape is the guard against ordinary staccato prose: the pattern is anchored
    # to a full line (line start .. end-of-line), and the FIRST beat must begin at the
    # line start, so a line that opens with any long sentence cannot match even if it
    # ends with short ones ("The meeting ran long and everyone was tired. We left."
    # stays clean). A run of short sentences flowing inside a paragraph is likewise
    # spared because the trailing long clause blocks the end-of-line anchor. The honest
    # limitation: in hard-wrapped plain text a genuinely headline-shaped standalone line
    # of 2-4 short sentences DOES count as one occurrence — which is why the tell is
    # gated purely on FREQUENCY (>=3), not on any semantic proof that the line is a
    # heading. A single such line, or two, stays clean.
    {
        "pattern": r"(?:^|\n)[ \t]*(?:[a-z0-9][\w'’-]*(?:[ ,]+[a-z0-9][\w'’-]*){0,4}[.!?][ \t]+){1,3}[a-z0-9][\w'’-]*(?:[ ,]+[a-z0-9][\w'’-]*){0,4}[.!?][ \t]*(?=\n|$)",
        "category": "headline_cadence",
        "severity": "soft",
        "suggestion": "The 'Short statement. Short statement.' headline cadence, repeated across a document (3+ headlines), is template grammar. Vary the headline shapes.",
        "min_matches": "3"
    },
    # Numeric-parallelism headline: "One X, N Y." Narrowed to the leading-"one" shape
    # on purpose so generic "<N> X, <N> Y." data lines ("Six aesthetics, zero
    # prompting.") are NOT swept in.
    {
        "pattern": r"(?:^|[.!?]\s+)one\s+[^,.!?\n]{1,30},\s+(?:two|three|four|five|six|seven|eight|nine|ten|\d+|a\s+dozen|dozens|hundreds|thousands)\s+[^,.!?\n]{1,30}[.!?]",
        "category": "numeric_parallelism",
        "severity": "soft",
        "suggestion": "'One X, N Y.' numeric-parallelism headline is a slogan tell. Rewrite as a normal sentence."
    },
    # Anthropomorphic shipping: an abstraction that "ships inside/with" something
    # ("The feedback loop ships inside the artifact."). Guarded so concrete
    # changelog uses ("The SDK ships with a CLI.") are spared: fire only when the
    # subject is an abstraction OR the verb is the "ships inside/within" form.
    {
        "pattern": r"\b(?:(?:loop|story|experience|magic|feedback|journey|narrative|workflow|feeling|insight|intelligence|value|understanding|context|logic|flow)\s+ships?\s+(?:inside|within|with|in|alongside)\b|ships?\s+(?:inside|within)\s+(?:the|your|its|our|a|an)\b)",
        "category": "anthropomorphic_shipping",
        "severity": "soft",
        "suggestion": "Abstractions don't 'ship inside' things. State the mechanism plainly."
    },

    # Em-dash overuse
    {
        "pattern": r"—(?:(?!\n\n)[^—])*—",
        "category": "em_dash_overuse",
        "severity": "hard",
        "suggestion": "Two+ em-dashes in a stretch is the tell. Keep at most one appositive dash; use periods/commas for the rest."
    },

    # Staccato fragmentation (3+ consecutive short sentences)
    {
        "pattern": r"(?:\.\s+\S{1,15}){3,}\.",
        "category": "staccato_fragmentation",
        "severity": "soft",
        "suggestion": "Vary sentence length. Stacked short sentences are an AI rhythm tell."
    },

    # Paragraph starting with "So," (comma required: bare "So the tenant remains
    # liable" is ordinary prose). Match lowercase: scan_for_violations lowercases
    # the text before applying structural patterns.
    {
        "pattern": r"(?:^|\n)so,\s",
        "category": "filler_opener",
        "severity": "soft",
        "suggestion": "Start with content, not 'So,'"
    },

    # False agency: inanimate subjects narrating. People tell stories literally;
    # data does not.
    {
        "pattern": r"\b(?:data|numbers?|charts?|graphs?|metrics?|figures?|results?|dashboards?|spreadsheets?|trend\s?lines?|statistics)\s+tells?\s+a\s+story\b",
        "category": "false_agency",
        "severity": "hard",
        "suggestion": "Say what the data shows."
    },

    # Colon-before-dramatic-reveal
    {
        "pattern": r"(?:the (?:answer|secret|key|trick|truth|reality|problem|issue|question|solution|takeaway|lesson|difference|reason) (?:is|was|isn't|remains))\s*:",
        "category": "colon_reveal",
        "severity": "hard",
        "suggestion": "Remove the setup. State the point directly."
    },

    # Excessive exclamation marks
    {
        "pattern": r"!(?:(?!\n\n)\s)+(?:(?!\n\n)[^.])*!",
        "category": "exclamation_overuse",
        "severity": "soft",
        "suggestion": "Multiple exclamation marks signal AI enthusiasm. Use sparingly."
    },

    # Parenthetical hedging
    {
        "pattern": r"\((?:and,?\s+)?(?:perhaps|more importantly|increasingly|more precisely|arguably)\b[^)]*\)",
        "category": "parenthetical_hedging",
        "severity": "soft",
        "suggestion": "If the aside matters, give it its own sentence. Otherwise cut it."
    },

    # Numbered-list inflation
    {
        "pattern": r"(?m)^(?:here are|these are|the top)\s+\d+\s+(?:reasons|things|takeaways|lessons|ways)\b",
        "category": "numbered_list_inflation",
        "severity": "soft",
        "suggestion": "Use a list only when the count matters."
    },

    # Rhetorical-question openers
    {
        "pattern": r"(?m)^\s*(?:but\s+)?what does this mean for\b",
        "category": "rhetorical_question",
        "severity": "soft",
        "suggestion": "Answer directly instead of opening with a rhetorical question."
    },
    {
        "pattern": r"(?m)^\s*so why should you care\??",
        "category": "rhetorical_question",
        "severity": "hard",
        "suggestion": "State why it matters directly."
    },
    {
        "pattern": r"(?im)(?:^|[.!?]\s+)(?:why does this matter|what's the (?:real )?takeaway|why this matters|so what does (?:this|that) mean)\b[^.!?\n]{0,40}[?:]",
        "category": "rhetorical_question",
        "severity": "soft",
        "suggestion": "Answer directly instead of teeing up a self-Q&A."
    },
    {
        "pattern": r"(?:^|[.!?]\s+)the (?:result|best part|catch|kicker|upshot|takeaway|twist|bottom line|payoff|difference)\?",
        "category": "rhetorical_question",
        "severity": "hard",
        "suggestion": "State the result directly."
    },
    {
        "pattern": r"\b(?:could|may|might|can)\s+(?:potentially|possibly)\b",
        "category": "hedge_stack",
        "severity": "soft",
        "suggestion": "Drop the redundant hedge."
    },
    {
        "pattern": r"(?im)(?:^|[.!?]\s+)whether you'?re (?=[^.!?\n]{0,60}\b(?:a|an|just starting)\s)[^.!?\n]{1,60}\bor\b",
        "category": "reader_addressing",
        "severity": "soft",
        "suggestion": "Cut the audience-flattering opener."
    },
    {
        "pattern": r"(?m)^#+\s*looking ahead\s*$",
        "category": "conclusion_scaffold",
        "severity": "soft",
        "suggestion": "Use a specific section title."
    },
    {
        "pattern": r"(?m)^(?:\s*#+\s*|\s*[-*]\s+|\s*)[\U0001F300-\U0001FAFF✀-➿☀-⛿]️?\s+\w",
        "category": "formatting",
        "severity": "soft",
        "suggestion": "Remove repeated emoji section-header decoration.",
        "min_matches": "2"
    },
]


def scan_for_violations(text: str, include_quoted: bool = False) -> list[Violation]:
    """Scan text for banned phrases and structural patterns."""
    violations: list[Violation] = []
    scan_text = mask_ignored_spans(text, include_quoted=include_quoted)
    text_lower = scan_text.lower()

    # Check banned phrases
    for phrase, info in BANNED_PHRASES.items():
        for match in _phrase_pattern(phrase).finditer(text_lower):
            pos = match.start()

            # Calculate line number and column
            line_num = text[:pos].count('\n') + 1
            line_start = text.rfind('\n', 0, pos) + 1
            column = pos - line_start + 1

            # Get context (the line containing the phrase)
            line_end = text.find('\n', pos)
            if line_end == -1:
                line_end = len(text)
            context = text[line_start:line_end].strip()

            violations.append({
                "phrase": phrase,
                "category": info["category"],
                "severity": info.get("severity", "hard"),
                "line_number": line_num,
                "column": column,
                "context": context[:100] + "..." if len(context) > 100 else context,
                "suggestion": info["suggestion"]
            })

    # Check structural patterns
    for pattern_info in STRUCTURAL_PATTERNS:
        matches = list(re.finditer(pattern_info["pattern"], text_lower))
        min_matches = int(pattern_info.get("min_matches", "1"))
        if len(matches) < min_matches:
            continue
        for match in matches:
            pos = match.start()
            line_num = text[:pos].count('\n') + 1
            line_start = text.rfind('\n', 0, pos) + 1
            column = pos - line_start + 1

            line_end = text.find('\n', pos)
            if line_end == -1:
                line_end = len(text)
            context = text[line_start:line_end].strip()

            violations.append({
                "phrase": match.group(),
                "category": pattern_info["category"],
                "severity": pattern_info.get("severity", "hard"),
                "line_number": line_num,
                "column": column,
                "context": context[:100] + "..." if len(context) > 100 else context,
                "suggestion": pattern_info["suggestion"]
            })

    filtered: list[Violation] = []
    spans: list[tuple[int, int]] = []
    for v in violations:
        start = sum(len(line) + 1 for line in text.splitlines()[:v["line_number"] - 1]) + v["column"] - 1
        end = start + len(v["phrase"])
        spans.append((start, end))

    # Frequency-gated structural findings (min_matches > 1) describe the DOCUMENT, not
    # a single span. A broad, unrelated match (e.g. anti_slop_register spanning several
    # short headlines) must not silently swallow every occurrence and erase the
    # document-level tell, so these categories are exempt from containment suppression.
    freq_gated = {
        p["category"] for p in STRUCTURAL_PATTERNS if int(p.get("min_matches", "1")) > 1
    }
    for i, v in enumerate(violations):
        start, end = spans[i]
        contained = any(
            i != j and other_start <= start and end <= other_end and (other_end - other_start) > (end - start)
            for j, (other_start, other_end) in enumerate(spans)
        )
        if not contained or v["category"] in freq_gated:
            filtered.append(v)
    violations = filtered

    # Sort by line number, then column
    violations.sort(key=lambda v: (v["line_number"], v["column"]))

    return violations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", nargs="?", help="Optional input file. Reads stdin when omitted.")
    parser.add_argument(
        "--include-quoted",
        action="store_true",
        help="Scan quoted examples and markdown blockquotes instead of skipping them.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Read input
    if args.input_file:
        try:
            with open(args.input_file, 'r') as f:
                text = f.read()
        except OSError as e:
            print(json.dumps({"error": f"Could not read input: {e}", "violations": []}))
            sys.exit(2)
    else:
        text = sys.stdin.read()

    if not text.strip():
        print(json.dumps({"error": "No input provided", "violations": []}))
        sys.exit(1)

    violations = scan_for_violations(text, include_quoted=args.include_quoted)

    # English-only graceful decline. Function-word absence alone is not evidence
    # of a foreign language: imperative stacks and buzzword lists are English
    # slop with few function words. Decline only when the text both fails the
    # function-word heuristic AND produced zero English-pattern hits.
    if not violations and not is_probably_english(text):
        print(json.dumps({"non_english": True, "total_violations": 0, "violations": []}, indent=2))
        print("note: input appears non-English; scanner declined (English-only).", file=sys.stderr)
        sys.exit(0)

    # Group by category for summary
    categories: dict[str, int] = {}
    by_severity: dict[str, int] = {"hard": 0, "soft": 0}
    for v in violations:
        categories[v["category"]] = categories.get(v["category"], 0) + 1
        by_severity[v["severity"]] = by_severity.get(v["severity"], 0) + 1

    output = {
        "total_violations": len(violations),
        "by_severity": by_severity,
        "by_category": categories,
        "violations": violations
    }

    print(json.dumps(output, indent=2))

    # Exit with 1 if violations found
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
