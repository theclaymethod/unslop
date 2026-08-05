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

from __future__ import annotations

import argparse
import bisect
import sys
import re
import json
from pathlib import Path
from typing import TypedDict

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _lang import (  # noqa: E402
    ENGLISH_FUNCTION_WORDS,
    english_function_share,
    is_probably_english,
)


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


# Case-insensitive variant used only at the scan_for_violations call site, so
# _phrase_pattern's case-sensitive default is unchanged for any other caller.
# BANNED_PHRASES keys are lowercase literals; matching case-insensitively
# against the original (unlowered) text avoids str.lower()'s non-length-
# preserving folds (e.g. U+0130 "İ" -> 2 chars), which corrupt offsets.
_phrase_pattern_ci_cache: dict[str, re.Pattern[str]] = {}


def _phrase_pattern_ci(phrase: str) -> re.Pattern[str]:
    cached = _phrase_pattern_ci_cache.get(phrase)
    if cached is None:
        pattern = _phrase_pattern(phrase).pattern
        # Curly apostrophes are typography, not a different phrase. Keep the
        # original phrase key (and its output spelling), but match both forms
        # without normalizing the input and corrupting offsets.
        if "'" in phrase:
            pattern = pattern.replace("'", "['’]")
        cached = re.compile(pattern, re.IGNORECASE)
        _phrase_pattern_ci_cache[phrase] = cached
    return cached


def _line_starts(text: str) -> list[int]:
    """0-indexed start offset of each line; line N (1-based) starts at index N-1."""
    starts = [0]
    for m in re.finditer("\n", text):
        starts.append(m.end())
    return starts


def _line_col_context(
    text: str,
    line_starts: list[int],
    pos: int,
    context_cache: dict[int, str] | None = None,
) -> tuple[int, int, str]:
    """Derive (1-based line, 1-based column, stripped line context) for an offset
    into ORIGINAL text from a precomputed line_starts index, in O(log n)."""
    idx = bisect.bisect_right(line_starts, pos) - 1
    line_start = line_starts[idx]
    line_end = line_starts[idx + 1] - 1 if idx + 1 < len(line_starts) else len(text)
    line_num = idx + 1
    column = pos - line_start + 1
    context = context_cache.get(idx) if context_cache is not None else None
    if context is None:
        context = text[line_start:line_end].strip()
        context = context[:100] + "..." if len(context) > 100 else context
        if context_cache is not None:
            context_cache[idx] = context
    return line_num, column, context


# Banned phrases with categories, suggestions, and severity.
# severity: "hard" = always an AI tell; "soft" = context-dependent

# Compact high-signal scanner pack. Literal/domain-sensitive cases stay explicit:
# broad vocabulary and low-value rhetorical variants are intentionally retired.
BANNED_PHRASES: dict[str, dict[str, str | None]] = {
    # Throat-clearing and conclusion scaffolding.
    "here's the thing:": {"category": "throat_clearing", "severity": "hard", "suggestion": None},
    "in conclusion": {
        "category": "conclusion_scaffold",
        "severity": "hard",
        "suggestion": "State the conclusion directly.",
    },

    # Significance inflation and vague attribution.
    "underscore the importance": {
        "category": "significance_inflation",
        "severity": "hard",
        "suggestion": "State the concrete effect.",
    },
    "analysts predict": {
        "category": "vague_attribution",
        "severity": "hard",
        "suggestion": "Name the analysts or cite the forecast.",
    },

    # High-signal AI vocabulary.
    "treasure trove": {
        "category": "ai_vocabulary",
        "severity": "hard",
        "suggestion": "collection, source",
    },

    # False agency, promotion, and assistant artifacts.
    "speak for themselves": {
        "category": "false_agency",
        "severity": "hard",
        "suggestion": "State the numbers and what they show.",
    },
    "rich cultural heritage": {
        "category": "promotional",
        "severity": "hard",
        "suggestion": None,
    },
    "as an ai language model": {
        "category": "assistant_artifact",
        "severity": "hard",
        "suggestion": "Delete the chatbot boilerplate.",
    },

    # Literal words remain out of the pack unless a jargon collocation is clear.
    "game changer": {
        "category": "jargon",
        "severity": "hard",
        "suggestion": "significant, important",
    },
    "synergy": {
        "category": "jargon",
        "severity": "hard",
        "suggestion": "cooperation, collaboration",
    },
    "robust": {
        "category": "jargon",
        "severity": "soft",
        "suggestion": "strong, solid, thorough",
    },
    "comprehensive": {
        "category": "jargon",
        "severity": "soft",
        "suggestion": "full, complete, thorough",
    },

    # Filler and chatbot knowledge-cutoff framing.
    "at the end of the day": {
        "category": "filler",
        "severity": "hard",
        "suggestion": None,
    },
    "in today's": {
        "category": "filler",
        "severity": "hard",
        "suggestion": None,
    },
    "as of my last": {
        "category": "knowledge_cutoff",
        "severity": "hard",
        "suggestion": "Delete the training-cutoff disclaimer.",
    },
    "why should you care": {
        "category": "rhetorical_question",
        "severity": "hard",
        "suggestion": "State why it matters directly.",
    },
}

# Compile literal phrase regexes once at module load. In-process callers may
# scan many documents; they should not pay this fixed compilation cost per
# document (subprocess callers still pay it once per process, as before).
for _banned_phrase in BANNED_PHRASES:
    _phrase_pattern_ci(_banned_phrase)

# Compact structural pack. Domain-sensitive branches are gated narrowly so
# literal construction, mechanics, law, medicine, and code remain clean.
STRUCTURAL_PATTERNS: list[dict[str, str]] = [
    # Emphasis and throat-clearing.
    {
        "pattern": r"(?:^|[.!?]\s+)(?:full stop|period)\.",
        "category": "emphasis_crutch",
        "severity": "hard",
        "suggestion": "Cut the one-word emphasis sentence.",
    },
    {
        "pattern": r"\bthe real \w+ (?:is|isn't|was|wasn't|remains)\b",
        "category": "throat_clearing",
        "severity": "hard",
        "suggestion": "State it directly.",
    },
    {
        "pattern": r"(?i)\b(?:the\s+|that\s+|this\s+)?(?:struggle|stakes|pain|threat|risk|danger|fear|hype|magic|hustle|grind|stress|pressure|burnout|concern|consequences|impact|tension|anxiety|disconnect|divide|need|demand|love|chemistry|connection|mechanic|feels?)\s+(?:is|are|was|were)\s+(?:very\s+|so\s+|all\s+too\s+)?real\b",
        "category": "emphasis_crutch",
        "severity": "soft",
        "suggestion": "State what is actually at stake.",
    },

    # Jargon collocations. Bare literal words with ordinary meanings are not
    # structural hits; the fixture keeps a protection for each domain branch.
    {
        "pattern": r"\bleverag(?:e|es|ed|ing)\s+(?:our\s+|your\s+|their\s+|its\s+|the\s+)?(?:synerg|core\s+compet|strength|expertise|capabilit|technolog|resource|data\b|ai\b|platform|ecosystem|network|audit\s+stream|power\s+of)",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "use, apply",
    },
    {
        "pattern": r"\bnavigat(?:e|es|ed|ing)\s+(?:the\s+|this\s+|these\s+)?(?:complex|challeng|landscape|nuance|intric|water|terrain|maze|minefield|uncertaint|world\s+of|ever-)",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "handle, address, manage",
    },
    {
        # Keep the high-signal abstract use, but leave literal excavation and
        # mining language ("delve into the mountain") alone.
        "pattern": r"\bdelv(?:e|es|ed|ing)\s+into\s+(?:the\s+)?(?:topic|topics|issue|issues|implication|implications|question|questions|subject|details?|nuance|nuances|meaning|argument|claim|concept|matter|problem|analysis|research|data|strategy|history|world|conversation|evidence|complexit(?:y|ies))\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "explore, examine, look at",
    },
    {
        "pattern": r"\bharness(?:es|ed|ing)?\s+(?:the\s+|its\s+|their\s+|our\s+)?(?:power|potential|strength|capabilit|momentum|force|full\s+)",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "use, tap, apply",
    },
    {
        "pattern": r"\bharness(?:es|ed|ing)?\s+(?:(?:(?:the|our|their|its)\s+)?(?:team|group|company|organization|workforce)(?:['’]s)\s+energy\b(?=[^.!?\n]{0,100}\b(?:growth|launch|customer\s+service|transition|collaboration|innovation|expertise|engagement|success|results?)\b)|(?:(?:the|our|their)\s+)?energy\s+(?:and\s+expertise\b|of\s+(?:(?:our|the)\s+)?(?:team|group|workforce|people)\s+(?:collaboration|innovation|expertise)\b|to\s+(?:drive|fuel|accelerate|unlock|advance)\s+(?:innovation|collaboration|engagement|growth|transformation|success|results?)\b))",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "use, focus, coordinate",
    },
    {
        "pattern": r"\bfoster(?:s|ed|ing)?\s+(?:a\s+|an\s+|greater\s+|deeper\s+|stronger\s+)?(?:culture|collaboration|innovation|sense\s+of|community|environment|growth|engagement|inclusion|creativity|dialogue|connection|belonging)",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "build, encourage, create",
    },
    {
        "pattern": r"\bunpack(?:s|ed|ing)?\s+(?:the\s+|this\s+|that\s+|our\s+)?(?:idea|argument|assumption|implication|implications|nuance|meaning|claim|concept|topic|dynamic|why|how|what)\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "explain, examine",
    },
    {
        "pattern": r"\bdoubl(?:e|es|ed|ing)\s+down\s+on\s+(?:the\s+|this\s+|that\s+|our\s+|your\s+|its\s+|their\s+|a\s+|an\s+)?(?:strategy|approach|investment|bet|commitment|vision|message|plan|position)\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "commit, increase",
    },
    {
        "pattern": r"\bbolster(?:s|ed|ing)?\s+(?:the\s+|this\s+|that\s+|our\s+|your\s+)?(?:argument|case|claim|confidence|credibility|support|position|strategy|effort|security)\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "support, strengthen",
    },
    {
        "pattern": r"\bstakeholders?\b[^.!?\n]{0,50}\b(?:buy-in|alignment|engagement|feedback|input|management)\b|\b(?:buy-in|alignment|engagement)\b[^.!?\n]{0,50}\bstakeholders?\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "people involved",
    },
    {
        "pattern": r"\b(?:in\s+)?(?:today's|modern|contemporary|business|marketing|tech|ai|media|education|healthcare|finance|industry)\s+landscape\b|\bthe\s+(?:business|marketing|tech|ai|media|education|healthcare|finance|industry)\s+landscape\s+of\b|\bthe\s+landscape\s+of\s+(?:modern\s+|today's\s+|contemporary\s+)?(?:marketing|business|tech\w*|ai|work|media|education|healthcare|finance|the industry)\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "situation, field, market",
    },
    {
        "pattern": r"\bload-bearing\s+(?:part|piece|point|claim|idea|insight|assumption|detail|context|constraint|requirement|decision|argument|premise|section|paragraph|sentence|word|term|concept)\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "essential, important, necessary",
    },
    {
        "pattern": r"\b(?:our|the|a)\s+wedge\s+into\s+the\s+(?:\w+\s+)?(?:market|enterprise|industry|segment|category|account|vertical)s?\b|\bas\s+a\s+wedge\b",
        "category": "jargon",
        "severity": "hard",
        "suggestion": "opening, angle, advantage, entry point",
    },
    {
        "pattern": r"\b(?:the\s+)?substrate\s+(?:for|of)\s+(?:everything|all|our|the\s+(?:company|business|movement|conversation|debate|work))\b|\bcultural\s+substrate\b",
        "category": "ai_vocabulary",
        "severity": "soft",
        "suggestion": "foundation, base, layer",
    },

    # Bare unattributed research is the vague-attribution move.
    {
        "pattern": r"(?:^|[.!?;:]\s+)research\s+(?:indicates|shows|suggests)\b",
        "category": "vague_attribution",
        "severity": "soft",
        "suggestion": "Cite the specific research or name the source.",
    },
    {
        "pattern": r"\bboasts?\s+(?:a\s+|an\s+)?(?:world-class|state-of-the-art|cutting-edge|impressive|stunning|robust|comprehensive|unparalleled|rich|vibrant|array of|host of|range of|wealth of|plethora)",
        "category": "promotional",
        "severity": "hard",
        "suggestion": "has",
    },
    {
        "pattern": r"\b(?:data|numbers?|charts?|graphs?|metrics?|figures?|results?|dashboards?|spreadsheets?|trend\s?lines?|statistics)\s+tells?\s+a\s+(?:clear\s+)?story\b",
        "category": "false_agency",
        "severity": "hard",
        "suggestion": "State what the data shows.",
    },
    {
        "pattern": r"\bplays?\s+an?\s+(?:crucial|key|vital|pivotal|significant|central|important|critical|defining|major)\s+(?:role|part)\b",
        "category": "significance_inflation",
        "severity": "soft",
        "suggestion": "State the specific effect.",
    },

    # Legal/technical and domain-valid protections.
    {
        "pattern": r"\bnotwithstanding\b(?!\s+(?:anything\s+to\s+the\s+contrary|the\s+foregoing|any(?:thing)?\s+(?:other\s+)?provision|section|clause|subsection|anything\s+in))",
        "category": "ai_vocabulary",
        "severity": "soft",
        "suggestion": "Use a direct transition.",
    },
    {
        "pattern": r"\b(?:acts|serves|stands|stood)\s+as\s+(?:a|an|the)\s+(?:testament|reminder|symbol|beacon|foundation|cornerstone|gateway|catalyst|bridge|hub|springboard|window|monument|hallmark|blueprint|cautionary|stark|powerful|shining|prime example|case study|model for)\b",
        "category": "copula_avoidance",
        "severity": "hard",
        "suggestion": "Use a direct verb.",
    },
    {
        "pattern": r"\bconstitutes\s+(?:a|an|the)\s+(?:(?:groundbreaking|transformative|trailblazing|seminal|revolutionary|landmark|pivotal|significant|major|key)\s+)?(?:transformation|breakthrough|milestone|achievement|innovation|advance|success|turning\s+point|cornerstone|testament|legacy|game[- ]changer)\b",
        "category": "copula_avoidance",
        "severity": "hard",
        "suggestion": "Use a direct verb.",
    },
    {
        "pattern": r"\bfunctions\s+as\s+(?:a|an|the)\s+(?:(?:seamless|comprehensive|robust|transformative|groundbreaking|strategic|powerful|key|central|critical|all-in-one|single)\s+)?(?:solution|framework|platform|hub|bridge|catalyst|cornerstone|benchmark|testament|symbol|beacon|transformation|milestone|game[- ]changer)\b",
        "category": "copula_avoidance",
        "severity": "hard",
        "suggestion": "Use a direct verb.",
    },

    # Anti-slop contrast and parallelism.
    {
        "pattern": r"(?im)(?:^|[.!?]\s+)(?:not|no)\b[^.!?]{0,28}[.!?]\s+(?:the\s+|it'?s?\s+|that'?s?\s+)?[a-z][^.!?]{0,28}[.!?]",
        "category": "anti_slop_register",
        "severity": "soft",
        "suggestion": "Join the fragments into a varied sentence.",
    },
    {
        "pattern": r"not because .+?\. because",
        "category": "binary_contrast",
        "severity": "hard",
        "suggestion": "State the reason in one sentence.",
    },
    {
        "pattern": r"feels like .+?\. it's actually",
        "category": "binary_contrast",
        "severity": "hard",
        "suggestion": "State the diagnosis directly.",
    },
    {
        "pattern": r"\bnot only .+? but also",
        "category": "negative_parallelism",
        "severity": "hard",
        "suggestion": "Use a direct sentence.",
    },
    {
        "pattern": r"\b(?:it'?s not|it\s+is\s+not|this is not|that'?s not|isn'?t|is\s+not|wasn'?t|was\s+not|aren'?t|are\s+not|weren'?t|were\s+not)\s+just\b[^.;!?\n]{1,60}[,;—–-]\s*(?:it'?s|it (?:is|was)|they'?re|that'?s)\b",
        "category": "negative_parallelism",
        "severity": "hard",
        "suggestion": "State the contrast directly.",
    },

    # Reader-steering and rhetorical-question scaffolding.
    {
        "pattern": r"(?i)\bin this (?:article|section|post|guide|chapter|paper),?\s+(?:we|i)\s+(?:will|'ll|are going to|shall)\b",
        "category": "reader_addressing",
        "severity": "soft",
        "suggestion": "Start with the point.",
    },
    {
        "pattern": r"(?im)(?:^|[.!?]\s+)whether you'?re (?=[^.!?\n]{0,60}\b(?:a|an|just starting)\s)[^.!?\n]{1,60}\bor\b",
        "category": "reader_addressing",
        "severity": "soft",
        "suggestion": "Cut the audience-flattering opener.",
    },
    {
        "pattern": r"(?im)(?:^|[.!?]\s+)(?:why does this matter|what's the (?:real )?takeaway|why this matters|so what does (?:this|that) mean)\b[^.!?\n]{0,40}[?:]",
        "category": "rhetorical_question",
        "severity": "soft",
        "suggestion": "Answer directly instead of teeing up a self-Q&A.",
    },
    {
        "pattern": r"(?m)^\s*(?:but\s+)?what does this mean for\b",
        "category": "rhetorical_question",
        "severity": "soft",
        "suggestion": "State the consequence directly.",
    },
    {
        "pattern": r"\b(?:could|may|might|can)\s+(?:potentially|possibly)\b",
        "category": "hedge_stack",
        "severity": "soft",
        "suggestion": "Drop the redundant hedge.",
    },
    {
        "pattern": r"(?m)^(?:here are|these are|the top)\s+\d+\s+(?:reasons|things|takeaways|lessons|ways)\b",
        "category": "numbered_list_inflation",
        "severity": "soft",
        "suggestion": "List only the points that matter.",
    },
]


def _sentence_context(text: str, start: int, end: int) -> str:
    """Return the sentence containing a match, preserving its original width."""
    left = max(text.rfind(mark, 0, start) for mark in ".!?\n")
    right_candidates = [text.find(mark, end) for mark in ".!?\n"]
    right_candidates = [pos for pos in right_candidates if pos >= 0]
    right = min(right_candidates) if right_candidates else len(text)
    return text[left + 1 : right]


def _context_has(pattern: str, text: str, start: int, end: int) -> bool:
    """Check a small sentence/window around a match for domain evidence."""
    sentence = _sentence_context(text, start, end)
    if re.search(pattern, sentence, re.IGNORECASE):
        return True
    window = text[max(0, start - 180) : min(len(text), end + 180)]
    return bool(re.search(pattern, window, re.IGNORECASE))


_LEGAL_CONTEXT = (
    r"\b(?:act|agreement|agency|clause|contract|court|defendant|filing|hearing|"
    r"judge|jury|landlord|law|lease|legal|liabilit(?:y|ies)|ordinance|part(?:y|ies)|plaintiff|"
    r"proceedings?|provision|pursuant|regulat(?:e|ed|ion|ory)|rights?|section|"
    r"statute|subsection|tenant\w*|warrant)\b"
)
_HISTORICAL_CONTEXT = (
    r"\b(?:archaeolog\w*|archive\w*|artifact\w*|catalog\w*|chronicle\w*|"
    r"document\w*|histor\w*|museum\w*|preserv\w*|record\w*|tradition\w*|"
    r"custom\w*|excavat\w*|ancestr\w*)\b"
)
_PROMOTIONAL_CONTEXT = (
    r"\b(?:boast\w*|celebrat\w*|famous|known|renowned|touris\w*|visitor\w*|"
    r"destination|vibrant|stunning|impressive|rich\s+in)\b"
)
_SOURCE_CONTEXT = (
    r"\b(?:according\s+to|per|citing|based\s+on|as\s+(?:reported|stated|"
    r"estimated)\s+by)\b|\b(?:survey|report|study|data|figures?)\s+"
    r"(?:from|by|of|says?|shows?|finds?|estimates?|projects?|predicts?)\b"
)
_MEDICAL_CONTEXT = (
    r"\b(?:anatom\w*|biolog\w*|cancer|cell\w*|clinical\w*|diagnos\w*|"
    r"disease\w*|dose\w*|drug\w*|genes?\b|genetic\w*|genomic\w*|health\w*|immune\w*|infection\w*|"
    r"inflamm\w*|kidney\w*|liver\w*|medical\w*|medicine|patient\w*|patholog\w*|physiolog\w*|"
    r"symptom\w*|therapy|tissue\w*|treatment\w*|tumou?r\w*|syndrome\w*)\b"
)


def _suppress_contextual_match(
    phrase: str,
    category: str,
    scan_text: str,
    start: int,
    end: int,
) -> bool:
    """Protect ordinary domain-valid uses of otherwise useful weak signals."""
    if phrase == "rich cultural heritage":
        # Historical/factual descriptions are not travel-brochure copy. Keep
        # the broad phrase for genuinely promotional "known for" language.
        sentence = _sentence_context(scan_text, start, end)
        return bool(
            re.search(_HISTORICAL_CONTEXT, sentence, re.IGNORECASE)
            and not re.search(_PROMOTIONAL_CONTEXT, sentence, re.IGNORECASE)
        )

    if phrase == "in today's":
        # Date-specific hearing/session language is ordinary reporting, unlike
        # the generic "in today's market/landscape" filler.
        return bool(
            re.match(
                r"\s+(?:hearing|court\s+hearing|trial|session|proceedings?)\b",
                scan_text[end:],
                re.IGNORECASE,
            )
        )

    if phrase == "analysts predict":
        # Keep unattributed forecasts flagged, but trust a nearby explicit
        # source/record cue ("according to the survey", "Reuters reports", …).
        sentence = _sentence_context(scan_text, start, end)
        if re.search(_SOURCE_CONTEXT, sentence, re.IGNORECASE):
            return True
        return False

    if category == "negative_parallelism" and scan_text[start:end].lower().startswith("not only"):
        # Legal drafting uses this parallel construction as precise scope, not
        # as the canned contrast the rule targets.
        return bool(
            re.search(
                _LEGAL_CONTEXT,
                _sentence_context(scan_text, start, end),
                re.IGNORECASE,
            )
        )

    if category == "significance_inflation" and re.match(
        r"plays?\s+an?\s+(?:crucial|key|vital|pivotal|significant|central|important|critical|defining|major)\s+(?:role|part)\b",
        scan_text[start:end],
        re.IGNORECASE,
    ):
        # Scientific and medical prose often needs this precise causal wording.
        return _context_has(_MEDICAL_CONTEXT, scan_text, start, end)

    return False


def scan_for_violations(text: str, include_quoted: bool = False) -> list[Violation]:
    """Scan text for banned phrases and structural patterns."""
    violations: list[Violation] = []
    spans: list[tuple[int, int]] = []
    scan_text = mask_ignored_spans(text, include_quoted=include_quoted)
    # Cheap presence index: most documents contain only a few of the
    # retained literal phrases.
    # literal phrases. Precise matches still run against the original-width
    # text, so Unicode case expansion cannot corrupt reported offsets.
    # Normalize curly apostrophes only for the cheap presence check. Match
    # against the original-width text below so reported offsets stay exact.
    scan_text_lower = scan_text.lower().replace("’", "'")
    line_starts = _line_starts(text)
    line_context_cache: dict[int, str] = {}

    # Check banned phrases. Matching runs case-insensitively directly on
    # scan_text (original case, masking is length-preserving) instead of on a
    # separately lowered copy, so match.start()/match.end() are valid offsets
    # into the original text with no re-derivation needed.
    for phrase, info in BANNED_PHRASES.items():
        if phrase not in scan_text_lower:
            continue
        for match in _phrase_pattern_ci(phrase).finditer(scan_text):
            if _suppress_contextual_match(
                phrase,
                info["category"],
                scan_text,
                match.start(),
                match.end(),
            ):
                continue
            tail = scan_text[match.end():]
            if (
                phrase == "robust"
                and re.match(
                    r"\s+(?:hash\s+verification|retry\s+mechanism|error\s+handling|test\s+suite)\b",
                    tail,
                    re.IGNORECASE,
                )
            ) or (
                phrase == "comprehensive"
                and re.match(
                    r"\s+(?:visual\s+survey|needs\s+screen)\b",
                    tail,
                    re.IGNORECASE,
                )
            ):
                continue
            pos = match.start()
            line_num, column, context = _line_col_context(
                text, line_starts, pos, line_context_cache
            )

            violations.append({
                "phrase": phrase,
                "category": info["category"],
                "severity": info.get("severity", "hard"),
                "line_number": line_num,
                "column": column,
                "context": context,
                "suggestion": info["suggestion"]
            })
            spans.append((match.start(), match.end()))

    # Check structural patterns
    for pattern_info in STRUCTURAL_PATTERNS:
        matches = list(re.finditer(pattern_info["pattern"], scan_text, re.IGNORECASE))
        min_matches = int(pattern_info.get("min_matches", "1"))
        if len(matches) < min_matches:
            continue
        for match in matches:
            if _suppress_contextual_match(
                match.group().lower(),
                pattern_info["category"],
                scan_text,
                match.start(),
                match.end(),
            ):
                continue
            pos = match.start()
            line_num, column, context = _line_col_context(
                text, line_starts, pos, line_context_cache
            )

            violations.append({
                # Preserve the pre-fix lowercase phrase field: STRUCTURAL_PATTERNS
                # regexes are lowercase literals, previously matched against a
                # lowered copy of the text, so match.group() was always lowercase.
                "phrase": match.group().lower(),
                "category": pattern_info["category"],
                "severity": pattern_info.get("severity", "hard"),
                "line_number": line_num,
                "column": column,
                "context": context,
                "suggestion": pattern_info["suggestion"]
            })
            spans.append((match.start(), match.end()))

    # Frequency-gated structural findings (min_matches > 1) describe the DOCUMENT, not
    # a single span. A broad, unrelated match (e.g. anti_slop_register spanning several
    # short headlines) must not silently swallow every occurrence and erase the
    # document-level tell, so these categories are exempt from containment suppression.
    freq_gated = {
        p["category"] for p in STRUCTURAL_PATTERNS if int(p.get("min_matches", "1")) > 1
    }

    # Linear containment sweep, equivalent to the O(n^2) "any other strictly
    # larger span fully encloses mine" check above, but O(n log n): sort by
    # (start ascending, end descending) and sweep once. For any two spans with
    # other_start <= start and end <= other_end, (other_end - other_start) >
    # (end - start) holds automatically UNLESS the spans are identical -- so
    # weak enclosure by a DISTINCT span is exactly the strict-length condition.
    # A running "tallest end seen among strictly earlier starts" plus a
    # within-group max (for spans sharing the current start) reproduces this
    # without ever comparing every pair.
    n = len(violations)
    order = sorted(range(n), key=lambda i: (spans[i][0], -spans[i][1]))
    contained = [False] * n
    max_end_before_group = -1
    idx = 0
    while idx < n:
        group_start = spans[order[idx]][0]
        group_end = idx
        while group_end < n and spans[order[group_end]][0] == group_start:
            group_end += 1
        running_max_in_group = -1
        for vi in order[idx:group_end]:
            end = spans[vi][1]
            if max_end_before_group >= end or running_max_in_group > end:
                contained[vi] = True
            if end > running_max_in_group:
                running_max_in_group = end
        if running_max_in_group > max_end_before_group:
            max_end_before_group = running_max_in_group
        idx = group_end

    violations = [
        v for i, v in enumerate(violations)
        if not contained[i] or v["category"] in freq_gated
    ]

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
            with open(args.input_file, 'r', errors="replace") as f:
                text = f.read()
        except OSError as e:
            print(json.dumps({"error": f"Could not read input: {e}", "violations": []}))
            sys.exit(2)
    else:
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")

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
