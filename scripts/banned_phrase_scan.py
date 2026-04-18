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

    quote_patterns = [
        r'"[^"\n]{1,500}"',
        r"“[^”\n]{1,500}”",
        r"(?<!\w)'[^'\n]{2,500}'(?!\w)",
        r"(?<!\w)‘[^’\n]{2,500}’(?!\w)",
    ]
    for pattern in quote_patterns:
        masked = re.sub(pattern, lambda m: _mask_non_newlines(m.group(0)), masked)

    return masked


# Banned phrases with categories, suggestions, and severity.
# severity: "hard" = always an AI tell; "soft" = context-dependent
BANNED_PHRASES: dict[str, dict[str, str | None]] = {
    # Throat-clearing openers
    "here's the thing:": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "the uncomfortable truth is": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "it turns out": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "the real": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
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
    "full stop.": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},
    "period.": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},
    "let that sink in": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},
    "this matters because": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},
    "make no mistake": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},
    "here's why that matters": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},
    "read that again": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},
    "this is important": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},
    "this cannot be overstated": {"category": "emphasis_crutch", "severity": "hard", "suggestion": None},

    # Business jargon
    "navigate": {"category": "jargon", "severity": "hard", "suggestion": "handle, address, manage"},
    "unpack": {"category": "jargon", "severity": "hard", "suggestion": "explain, examine"},
    "lean into": {"category": "jargon", "severity": "hard", "suggestion": "accept, embrace"},
    "landscape": {"category": "jargon", "severity": "soft", "suggestion": "situation, field, market"},
    "game-changer": {"category": "jargon", "severity": "hard", "suggestion": "significant, important"},
    "game changer": {"category": "jargon", "severity": "hard", "suggestion": "significant, important"},
    "double down": {"category": "jargon", "severity": "hard", "suggestion": "commit, increase"},
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
    "leverage": {"category": "jargon", "severity": "hard", "suggestion": "use, apply"},
    "scalable": {"category": "jargon", "severity": "soft", "suggestion": "expandable, growable"},
    "actionable": {"category": "jargon", "severity": "hard", "suggestion": "practical, usable"},
    "ecosystem": {"category": "jargon", "severity": "soft", "suggestion": "environment, system"},
    "stakeholder": {"category": "jargon", "severity": "hard", "suggestion": "people involved"},
    "touch base": {"category": "jargon", "severity": "hard", "suggestion": "talk, connect"},
    "value-add": {"category": "jargon", "severity": "hard", "suggestion": "benefit, contribution"},
    "thought leader": {"category": "jargon", "severity": "hard", "suggestion": "expert"},
    "best-in-class": {"category": "jargon", "severity": "hard", "suggestion": "leading, top-tier"},
    "cutting-edge": {"category": "jargon", "severity": "hard", "suggestion": "modern, advanced"},
    "delve": {"category": "jargon", "severity": "hard", "suggestion": "explore, examine, look at"},
    "garner": {"category": "jargon", "severity": "hard", "suggestion": "get, earn, attract"},
    "robust": {"category": "jargon", "severity": "soft", "suggestion": "strong, solid, thorough"},
    "comprehensive": {"category": "jargon", "severity": "soft", "suggestion": "full, complete, thorough"},
    "utilize": {"category": "jargon", "severity": "hard", "suggestion": "use"},
    "facilitate": {"category": "jargon", "severity": "hard", "suggestion": "help, enable, run"},
    "spearhead": {"category": "jargon", "severity": "hard", "suggestion": "lead, start, run"},
    "bolster": {"category": "jargon", "severity": "hard", "suggestion": "support, strengthen"},
    "streamline": {"category": "jargon", "severity": "soft", "suggestion": "simplify, speed up"},
    "harness": {"category": "jargon", "severity": "hard", "suggestion": "use, tap, apply"},
    "multifaceted": {"category": "jargon", "severity": "hard", "suggestion": "complex, varied"},
    "foster": {"category": "jargon", "severity": "hard", "suggestion": "build, encourage, create"},
    "enhance": {"category": "jargon", "severity": "soft", "suggestion": "improve, strengthen"},
    "showcase": {"category": "jargon", "severity": "hard", "suggestion": "show, demonstrate"},
    "align with": {"category": "jargon", "severity": "hard", "suggestion": "match, fit, support"},

    # Filler phrases
    "at its core": {"category": "filler", "severity": "hard", "suggestion": None},
    "in today's": {"category": "filler", "severity": "hard", "suggestion": None},
    "it's worth noting": {"category": "filler", "severity": "hard", "suggestion": None},
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
    "it is important to note that": {"category": "filler", "severity": "hard", "suggestion": None},

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
    "boasts a": {"category": "promotional", "severity": "hard", "suggestion": "has a"},
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
    "serves as a": {"category": "copula_avoidance", "severity": "hard", "suggestion": "is a"},
    "stands as a": {"category": "copula_avoidance", "severity": "hard", "suggestion": "is a"},
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
    "tapestry": {"category": "ai_vocabulary", "severity": "hard", "suggestion": None},
    "paramount": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "important, critical"},
    "pertaining to": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "about, regarding"},
    "aforementioned": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "this, that, the"},
    "henceforth": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "from now on"},
    "whereby": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "where, by which"},
    "therein": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "in it, there"},
    "notwithstanding": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "despite, regardless"},
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
    "bolstered": {"category": "ai_vocabulary", "severity": "hard", "suggestion": "supported, boosted"},
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
    "the landscape of": {"category": "jargon", "severity": "hard", "suggestion": "cut or use specific domain"},
    "a game changer": {"category": "jargon", "severity": "hard", "suggestion": "significant, important"},
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
        "pattern": r"it'?s not just .+?,?\s*it'?s\s",
        "category": "negative_parallelism",
        "severity": "hard",
        "suggestion": "State both points directly"
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

    # Em-dash overuse
    {
        "pattern": r"—[^—]*—",
        "category": "em_dash_overuse",
        "severity": "hard",
        "suggestion": "Max one em-dash per paragraph. Use commas, periods, or parentheses instead."
    },
    {
        "pattern": r"—",
        "category": "em_dash_usage",
        "severity": "soft",
        "suggestion": "Prefer commas or periods over em-dashes. Em-dashes are an AI tell when overused."
    },

    # Staccato fragmentation (3+ consecutive short sentences)
    {
        "pattern": r"(?:\.\s+\S{1,15}){3,}\.",
        "category": "staccato_fragmentation",
        "severity": "soft",
        "suggestion": "Vary sentence length. Stacked short sentences are an AI rhythm tell."
    },

    # Paragraph starting with "So,"
    {
        "pattern": r"(?:^|\n)So,?\s",
        "category": "filler_opener",
        "severity": "hard",
        "suggestion": "Start with content, not 'So'"
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
        "pattern": r"!\s+[^.]*!",
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
]


def scan_for_violations(text: str, include_quoted: bool = False) -> list[Violation]:
    """Scan text for banned phrases and structural patterns."""
    violations: list[Violation] = []
    scan_text = mask_ignored_spans(text, include_quoted=include_quoted)
    text_lower = scan_text.lower()

    # Check banned phrases
    for phrase, info in BANNED_PHRASES.items():
        start = 0
        while True:
            pos = text_lower.find(phrase, start)
            if pos == -1:
                break

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

            start = pos + 1

    # Check structural patterns
    for pattern_info in STRUCTURAL_PATTERNS:
        for match in re.finditer(pattern_info["pattern"], text_lower):
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
        with open(args.input_file, 'r') as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    if not text.strip():
        print(json.dumps({"error": "No input provided", "violations": []}))
        sys.exit(1)

    violations = scan_for_violations(text, include_quoted=args.include_quoted)

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
