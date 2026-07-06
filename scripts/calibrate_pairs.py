#!/usr/bin/env python3
"""
Deterministic dimension-controlled pair generation for the teach calibration game.

Given a base passage and ONE voice dimension, produce a minimal pair (A, B) where
B differs from A along exactly that dimension. The direction of the transform
(e.g. contract -> expand vs expand -> contract) is auto-detected from whichever
pole the base passage already sits at, so every dimension is reversible: feed it
a passage already on one pole and it moves to the other.

Every transform must preserve the must-preserve constraint tokens extracted by
scripts/extract_constraints.py (numbers, dates, names, quotes, units, etc). If a
dimension has no expressible transform in the given passage (neither pole's
pattern is present, or the only candidate transform would drop a constraint),
the command exits 3 with "dimension not expressible in this passage".

Usage:
    python3 calibrate_pairs.py generate --base FILE --dimension DIM --seed N
    python3 calibrate_pairs.py --list-dimensions

Dimensions: contractions, em_dash, sentence_length, connectives, staccato.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from extract_constraints import extract_constraints  # noqa: E402
from banned_phrase_scan import scan_for_violations  # noqa: E402

DIMENSIONS = ["contractions", "em_dash", "sentence_length", "connectives", "staccato"]

# Each dimension has two named poles. transform_applied is "<dimension>:<pole of B>".
POLES: dict[str, tuple[str, str]] = {
    "contractions": ("contracted", "expanded"),
    "em_dash": ("dashed", "plain"),
    "sentence_length": ("long", "short"),
    "connectives": ("plain", "formal"),
    "staccato": ("staccato", "flowing"),
}


class NotExpressible(Exception):
    """Raised when a dimension has no applicable transform in the passage."""


# --------------------------------------------------------------------------
# contractions: expand <-> contract via a fixed, unambiguous mapping table.
# --------------------------------------------------------------------------

_CONTRACTION_PAIRS = [
    ("do not", "don't"), ("does not", "doesn't"), ("did not", "didn't"),
    ("cannot", "can't"), ("will not", "won't"), ("would not", "wouldn't"),
    ("should not", "shouldn't"), ("could not", "couldn't"), ("must not", "mustn't"),
    ("is not", "isn't"), ("are not", "aren't"), ("was not", "wasn't"), ("were not", "weren't"),
    ("have not", "haven't"), ("has not", "hasn't"), ("had not", "hadn't"),
    ("I am", "I'm"), ("you are", "you're"), ("we are", "we're"), ("they are", "they're"),
    ("I will", "I'll"), ("you will", "you'll"), ("we will", "we'll"), ("they will", "they'll"),
    ("he will", "he'll"), ("she will", "she'll"), ("it will", "it'll"),
    ("I have", "I've"), ("you have", "you've"), ("we have", "we've"), ("they have", "they've"),
    ("let us", "let's"),
    ("it is", "it's"), ("that is", "that's"), ("there is", "there's"),
    ("here is", "here's"), ("who is", "who's"), ("what is", "what's"),
]
# Pairs whose expanded side always keeps a hard-capitalized pronoun ("I ...").
_HARD_CAPITAL = {e for e, c in _CONTRACTION_PAIRS if e.startswith("I ")}


def _case_like(template: str, source_first_char: str) -> str:
    if source_first_char.isupper():
        return template[0].upper() + template[1:]
    return template[0].lower() + template[1:]


# Words safe to lowercase when a sentence is folded mid-clause. A capitalized
# word NOT in this set is assumed to be a proper noun (constraint) and is left
# alone -- lowercasing "Priya" into a joined clause would corrupt a name.
_LOWERABLE_JOINERS = {
    "the", "it", "she", "he", "they", "this", "that", "there", "i", "we", "you",
    "who", "what", "when", "where", "why", "how", "a", "an", "and", "but", "so",
    "yet", "or", "nobody", "everybody", "everyone", "someone", "something",
    "nothing", "no", "her", "his", "its", "their", "our", "your",
}


def _lower_first_word(s: str) -> str:
    """Lowercase the leading word only if it is a common function word/pronoun,
    never a token that looks like a proper noun a constraint might depend on."""
    m = re.match(r"[A-Za-z']+", s)
    if not m:
        return s
    word = m.group(0)
    if word.lower() in _LOWERABLE_JOINERS:
        return word.lower() + s[len(word):]
    return s


_WORD_BEFORE_RE = re.compile(r"([A-Za-z']+)\s*$")
_WORD_AFTER_RE = re.compile(r"^\s*([A-Za-z']+)")


def _is_title_case(word: str) -> bool:
    return bool(word) and word[0].isupper() and word[1:].islower()


def _in_capitalized_span(m: "re.Match[str]") -> bool:
    """True if this contraction/expansion match sits inside a capitalized
    multi-word span (e.g. "Venue Can't Stop") that looks like a proper noun,
    rather than an ordinary sentence-level contraction.

    A contraction rewrite is only skipped when the match ITSELF is
    capitalized (so an ordinary sentence-initial "Can't you..." is untouched)
    AND an immediately adjacent word is also Title Case, forming a >= 2-word
    capitalized run. "Maria Chen can't attend" is not skipped (the match is
    lowercase); "the Venue Can't Stop" is skipped (both "Venue" and "Can't"
    are capitalized and adjacent).
    """
    matched = m.group(0)
    if not matched[0].isupper():
        return False
    text = m.string
    before_m = _WORD_BEFORE_RE.search(text[: m.start()])
    after_m = _WORD_AFTER_RE.match(text[m.end() :])
    before_word = before_m.group(1) if before_m else ""
    after_word = after_m.group(1) if after_m else ""
    return _is_title_case(before_word) or _is_title_case(after_word)


def _apply_contractions(text: str) -> tuple[str, str]:
    contract_hits = []
    expand_hits = []
    for expanded, contracted in _CONTRACTION_PAIRS:
        if expanded in _HARD_CAPITAL:
            # "I am"/"I'll"/... always literally capitalized; case-sensitive match.
            if re.search(re.escape(contracted), text):
                contract_hits.append((expanded, contracted))
            if re.search(re.escape(expanded), text):
                expand_hits.append((expanded, contracted))
        else:
            if re.search(r"\b" + re.escape(contracted) + r"\b", text, re.IGNORECASE):
                contract_hits.append((expanded, contracted))
            if re.search(r"\b" + re.escape(expanded) + r"\b", text, re.IGNORECASE):
                expand_hits.append((expanded, contracted))

    if contract_hits:
        out = text
        for expanded, contracted in contract_hits:
            if expanded in _HARD_CAPITAL:
                def repl_hard(m, _expanded=expanded):
                    if _in_capitalized_span(m):
                        return m.group(0)
                    return _expanded
                out = re.sub(re.escape(contracted), repl_hard, out)
            else:
                def repl(m, _expanded=expanded):
                    if _in_capitalized_span(m):
                        return m.group(0)
                    return _case_like(_expanded, m.group(0)[0])
                out = re.sub(r"\b" + re.escape(contracted) + r"\b", repl, out, flags=re.IGNORECASE)
        return out, "expanded"

    if expand_hits:
        out = text
        for expanded, contracted in expand_hits:
            if expanded in _HARD_CAPITAL:
                def repl_hard2(m, _contracted=contracted):
                    if _in_capitalized_span(m):
                        return m.group(0)
                    return _contracted
                out = re.sub(re.escape(expanded), repl_hard2, out)
            else:
                def repl2(m, _contracted=contracted):
                    if _in_capitalized_span(m):
                        return m.group(0)
                    return _case_like(_contracted, m.group(0)[0])
                out = re.sub(r"\b" + re.escape(expanded) + r"\b", repl2, out, flags=re.IGNORECASE)
        return out, "contracted"

    raise NotExpressible("no contraction or expandable phrase found")


# --------------------------------------------------------------------------
# em_dash: paired em-dash parentheticals <-> paired-comma parentheticals ONLY.
#
# Only the paired-dash<->paired-comma path is expressible for this dimension.
# A lone joiner dash (" — nobody objected") has no comma-pair equivalent that
# preserves sentence count: turning it into a period (the old behavior) split
# one sentence into two, silently changing sentence count between A and B.
# Passages with only a lone dash (no paired construction) are declined rather
# than forced through a transform that shifts sentence count.
# --------------------------------------------------------------------------

_PAIRED_DASH_RE = re.compile(r"\s—\s(.+?)\s—\s")
_PAIRED_COMMA_RE = re.compile(r",\s+(.+?),\s+")


def _apply_em_dash(text: str) -> tuple[str, str]:
    if _PAIRED_DASH_RE.search(text):
        out = _PAIRED_DASH_RE.sub(lambda m: ", " + m.group(1) + ", ", text)
        if "—" in out:
            # A lone dash survived alongside the paired one -- the restricted
            # paired-dash<->comma path can't fully express this passage
            # without also touching the lone dash (and changing sentence
            # count), so decline rather than ship a half-converted pair.
            raise NotExpressible(
                "passage mixes a paired em dash with a lone em dash; "
                "the paired-dash<->comma path can't resolve the lone dash "
                "without changing sentence count"
            )
        return out, "plain"

    if "—" in text:
        raise NotExpressible(
            "only a lone em dash found; the em_dash dimension is restricted "
            "to the paired-dash<->comma path so sentence count stays stable"
        )

    if _PAIRED_COMMA_RE.search(text):
        out = _PAIRED_COMMA_RE.sub(lambda m: " — " + m.group(1) + " — ", text)
        return out, "dashed"

    raise NotExpressible("no paired em dash or comma-bounded parenthetical found")


# --------------------------------------------------------------------------
# sentence_length: split at coordinators <-> join short adjacent sentences.
# --------------------------------------------------------------------------

_COORD_RE = re.compile(r",\s+(and|but|or|so|yet)\s+", re.IGNORECASE)


def _apply_sentence_length(text: str) -> tuple[str, str]:
    sentences = re.findall(r"[^.!?]+[.!?]+", text)

    for sent in sentences:
        for m in _COORD_RE.finditer(sent):
            before = sent[:m.start()]
            after = sent[m.end():]
            if len(before.split()) >= 3 and len(after.split()) >= 3:
                new_sent = before.rstrip() + ". " + m.group(1).capitalize() + " " + after
                out = text.replace(sent, new_sent, 1)
                return re.sub(r"\s+", " ", out).strip(), "short"

    for i in range(len(sentences) - 1):
        a_words = sentences[i].strip().split()
        b_words = sentences[i + 1].strip().split()
        if len(a_words) <= 8 and len(b_words) <= 8:
            first_no_period = re.sub(r"[.!?]+\s*$", "", sentences[i].strip())
            second = sentences[i + 1].strip()
            second_body = re.sub(r"[.!?]+\s*$", "", second)
            end_punct = second[len(second_body):].strip() or "."
            joined = first_no_period + ", and " + _lower_first_word(second_body) + end_punct
            prefix = "".join(sentences[:i])
            suffix = "".join(sentences[i + 2:])
            out = (prefix + " " + joined + " " + suffix).strip()
            return re.sub(r"\s+", " ", out), "long"

    raise NotExpressible("no coordinator split site or joinable short sentences found")


# --------------------------------------------------------------------------
# connectives: formal <-> plain via a fixed table.
# --------------------------------------------------------------------------

_FORMAL_TO_PLAIN = {
    "however": "But", "additionally": "Also", "therefore": "So",
    "furthermore": "Also", "moreover": "Also", "nevertheless": "Still",
    "consequently": "So", "nonetheless": "Still", "subsequently": "Then",
    "thus": "So",
}
_PLAIN_TO_FORMAL = {
    "but": "However", "also": "Additionally", "so": "Therefore",
    "still": "Nevertheless", "then": "Subsequently",
}
_FORMAL_RE = re.compile(
    r"(?:^|(?<=[.!?]\s))(" + "|".join(_FORMAL_TO_PLAIN) + r"),?\s+", re.IGNORECASE
)
_PLAIN_RE = re.compile(
    r"(?:^|(?<=[.!?]\s))(" + "|".join(_PLAIN_TO_FORMAL) + r"),?\s+", re.IGNORECASE
)


def _apply_connectives(text: str) -> tuple[str, str]:
    if _FORMAL_RE.search(text):
        def repl(m):
            # No comma after the plain form: "But " reads as ordinary speech;
            # "But, " is stilted, and "So, " specifically trips the scanner's
            # filler_opener structural pattern. Dropping the comma across the
            # board keeps every plain form clean of that tell.
            return _FORMAL_TO_PLAIN[m.group(1).lower()] + " "
        out = _FORMAL_RE.sub(repl, text)
        return out, "plain"

    if _PLAIN_RE.search(text):
        def repl2(m):
            return _PLAIN_TO_FORMAL[m.group(1).lower()] + ", "
        out = _PLAIN_RE.sub(repl2, text)
        return out, "formal"

    raise NotExpressible("no formal or plain connective found")


# --------------------------------------------------------------------------
# staccato: fragment runs <-> flowing clauses.
# --------------------------------------------------------------------------

_LEADING_JOINER_RE = re.compile(
    r"^(?:because|although|while|since|if|when|and|but|so|yet|or)\s+", re.IGNORECASE
)


def _apply_staccato(text: str, rng: random.Random) -> tuple[str, str]:
    sentences = re.findall(r"[^.!?]+[.!?]+", text)

    # Reverse direction: a run of >= 3 consecutive short (<=6 word) sentences -> flow.
    runs = []
    run_start = None
    for i, sent in enumerate(sentences):
        words = sent.strip().split()
        if len(words) <= 6:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None and i - run_start >= 3:
                runs.append((run_start, i))
            run_start = None
    if run_start is not None and len(sentences) - run_start >= 3:
        runs.append((run_start, len(sentences)))

    if runs:
        start, end = runs[rng.randrange(len(runs))] if len(runs) > 1 else runs[0]
        parts = []
        for idx in range(start, end):
            body = re.sub(r"[.!?]+\s*$", "", sentences[idx].strip())
            parts.append(body)
        joined_parts = []
        for i, p in enumerate(parts):
            if i == 0:
                joined_parts.append(p)
            elif i == len(parts) - 1:
                joined_parts.append("and " + _lower_first_word(p))
            else:
                joined_parts.append(_lower_first_word(p))
        joined = ", ".join(joined_parts) + "."
        prefix = "".join(sentences[:start])
        suffix = "".join(sentences[end:])
        out = (prefix + " " + joined + " " + suffix).strip()
        return re.sub(r"\s+", " ", out), "flowing"

    # Forward direction: the sentence with the most commas (>= 2) fragments.
    best_idx, best_commas = None, 1
    for i, sent in enumerate(sentences):
        commas = sent.count(",")
        if commas > best_commas:
            best_idx, best_commas = i, commas

    if best_idx is not None:
        sent = sentences[best_idx]
        body = re.sub(r"[.!?]+\s*$", "", sent.strip())
        end_punct = sent.strip()[len(body):].strip() or "."
        fragments = [f.strip() for f in body.split(",")]
        cleaned = []
        for frag in fragments:
            frag = _LEADING_JOINER_RE.sub("", frag).strip()
            if not frag:
                continue
            frag = frag[0].upper() + frag[1:]
            cleaned.append(frag)
        if len(cleaned) < 3:
            raise NotExpressible("comma split did not yield a fragment run")
        cleaned[-1] = cleaned[-1] + end_punct if not cleaned[-1].endswith((".", "!", "?")) else cleaned[-1]
        new_sent = " ".join(
            f if f.endswith((".", "!", "?")) else f + "." for f in cleaned
        )
        out = text.replace(sent, new_sent, 1)
        return re.sub(r"\s+", " ", out).strip(), "staccato"

    raise NotExpressible("no fragment run or multi-comma sentence found")


_APPLY = {
    "contractions": lambda text, rng: _apply_contractions(text),
    "em_dash": lambda text, rng: _apply_em_dash(text),
    "sentence_length": lambda text, rng: _apply_sentence_length(text),
    "connectives": lambda text, rng: _apply_connectives(text),
    "staccato": _apply_staccato,
}

_EXAMPLES = {
    "contractions": {
        "description": "Expand <-> contract via a fixed, unambiguous mapping table "
                        "(do not <-> don't, I am <-> I'm, it is <-> it's, ...).",
        "a": "The rollout is not finished, and I am not confident it will ship Friday.",
        "b": "The rollout isn't finished, and I'm not confident it'll ship Friday.",
    },
    "em_dash": {
        "description": "Paired em-dash parentheticals <-> paired-comma parentheticals only "
                        "(a lone joiner dash has no comma-pair equivalent that preserves "
                        "sentence count, so it is declined rather than converted).",
        "a": "The plan — untested and rushed — still shipped on time.",
        "b": "The plan, untested and rushed, still shipped on time.",
    },
    "sentence_length": {
        "description": "Split at a coordinator <-> join two short adjacent sentences.",
        "a": "The team shipped the fix, and the client renewed the contract.",
        "b": "The team shipped the fix. And the client renewed the contract.",
    },
    "connectives": {
        "description": "Formal <-> plain connective swap via a fixed table "
                        "(However -> But, Additionally -> Also, Therefore -> So, ...). "
                        "Plain forms drop the comma after the connective (\"But \", not "
                        "\"But, \") so they read as ordinary speech, not a filler-opener tell.",
        "a": "However, the numbers slipped in March.",
        "b": "But the numbers slipped in March.",
    },
    "staccato": {
        "description": "Fragment runs <-> flowing clauses.",
        "a": "Because the deploy failed, and the on-call missed the page, the team lost an hour.",
        "b": "The deploy failed. The on-call missed the page. The team lost an hour.",
    },
}


def _is_word_char(ch: str) -> bool:
    return ch.isalnum()


def _has_whole_occurrence(value: str, text: str) -> bool:
    """True if `value` occurs in `text` as a standalone span rather than as a
    substring straddling the edge of a longer, different word.

    Plain substring containment is not enough: expanding "Can't" to "Cannot"
    still contains the literal characters "Can", so a naive `"Can" in
    "Cannot"` check reports a corrupted proper noun as "preserved". At each
    edge of a candidate match, this only counts as a clash (disqualifying the
    match) when BOTH the value's own boundary character and the adjacent text
    character are alphanumeric -- i.e. when `value` could be glued onto a
    longer token. Values that start/end with punctuation (currency signs,
    quotes) never clash on that edge, since punctuation can't be silently
    swallowed into a bigger word the way a letter/digit can.
    """
    if not value:
        return False
    start = 0
    while True:
        idx = text.find(value, start)
        if idx == -1:
            return False
        left_clash = idx > 0 and _is_word_char(text[idx - 1]) and _is_word_char(value[0])
        end = idx + len(value)
        right_clash = end < len(text) and _is_word_char(text[end]) and _is_word_char(value[-1])
        if not left_clash and not right_clash:
            return True
        start = idx + 1


def _verify_constraints_preserved(base_text: str, transformed_text: str) -> list[str]:
    """Return constraint values from base_text missing from transformed_text.

    Uses whole-occurrence (token-boundary) comparison rather than plain
    substring containment -- see `_has_whole_occurrence` for why a substring
    check is unsafe here.
    """
    missing = []
    for c in extract_constraints(base_text):
        value = c["value"]
        if _has_whole_occurrence(value, transformed_text):
            continue
        # Allow whitespace-normalized matches (transforms may collapse spacing).
        normalized_value = re.sub(r"\s+", " ", value)
        normalized_text = re.sub(r"\s+", " ", transformed_text)
        if normalized_value != value and _has_whole_occurrence(normalized_value, normalized_text):
            continue
        missing.append(value)
    return missing


def _scan_flags(text: str) -> list[str]:
    """Category names banned_phrase_scan raises on `text`, deduped and sorted.

    Empty when the text scans clean. Generated B-variants can legitimately
    trip the scanner (e.g. a staccato pole reads as anti_slop_register; see
    references/calibrate.md "Voice overrides defaults") -- that is surfaced
    here, not treated as a reason to decline the pair.
    """
    categories = {v["category"] for v in scan_for_violations(text)}
    return sorted(categories)


def generate_pair(base_text: str, dimension: str, seed: int) -> dict:
    if dimension not in DIMENSIONS:
        raise ValueError(f"unknown dimension: {dimension}")

    rng = random.Random(seed)
    transformed, pole = _APPLY[dimension](base_text, rng)

    if transformed.strip() == base_text.strip():
        raise NotExpressible("transform produced no change")

    missing = _verify_constraints_preserved(base_text, transformed)
    if missing:
        raise NotExpressible(
            "transform would drop must-preserve constraint(s): " + ", ".join(missing)
        )

    pair_id = hashlib.sha256(
        f"{base_text}|{dimension}|{seed}".encode("utf-8")
    ).hexdigest()

    return {
        "pair_id": pair_id,
        "dimension": dimension,
        "a_text": base_text,
        "b_text": transformed,
        "transform_applied": f"{dimension}:{pole}",
        "a_flags": _scan_flags(base_text),
        "b_flags": _scan_flags(transformed),
    }


def list_dimensions() -> dict:
    return {
        dim: {
            "poles": list(POLES[dim]),
            "description": _EXAMPLES[dim]["description"],
            "example": {"a": _EXAMPLES[dim]["a"], "b": _EXAMPLES[dim]["b"]},
        }
        for dim in DIMENSIONS
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="generate one dimension-controlled pair")
    gen.add_argument("--base", required=True, help="path to base passage file")
    gen.add_argument("--dimension", required=True, choices=DIMENSIONS)
    gen.add_argument("--seed", type=int, default=0)

    parser.add_argument("--list-dimensions", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.list_dimensions:
        print(json.dumps(list_dimensions(), indent=2, sort_keys=True))
        return 0

    if args.command != "generate":
        print(json.dumps({"error": "no command given; use generate or --list-dimensions"}))
        return 1

    try:
        base_text = Path(args.base).read_text()
    except OSError as e:
        print(json.dumps({"error": f"could not read base file: {e}"}))
        return 2

    try:
        pair = generate_pair(base_text, args.dimension, args.seed)
    except NotExpressible as e:
        print(json.dumps({
            "error": "dimension not expressible in this passage",
            "dimension": args.dimension,
            "detail": str(e),
        }))
        return 3

    print(json.dumps(pair, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
