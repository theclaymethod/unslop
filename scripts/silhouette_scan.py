#!/usr/bin/env python3
"""Scan prose for discourse-level silhouette AI-writing patterns.

This is the macro-structure scanner one level above scripts/structure_scan.py.
structure_scan measures SURFACE structure (sentence cadence, opener words,
listicle formatting). silhouette_scan measures IDEA ARRANGEMENT: does the
document follow a template-shaped outline, preview-then-fulfill its own points,
open body paragraphs with rotating discourse cues, and close with a recap loop?

Five validated one-sided tells (all AI-high; humans cluster at zero):

  scaffold_opener_share  body paragraphs opening with a discourse-cue class
  callback_content       early vocab absent mid-document, returning at the end
                         (the recap loop; strongest single tell)
  role_entropy_bits      count of distinct cue-opener classes (a template rotates
                         "However / In addition / Ultimately" openers)
  preview_fulfillment    intro content words reappearing as body-paragraph heads
  heading_preview        heading head-nouns previewed in the intro (outline follow)

Composite:

  silhouette_penalty = sum_i weight_i * relu((m_i - median_i) / scale_i)

scored against a committed HUMAN reference distribution
(evals/fixtures/silhouette/human_reference.json), negative side clipped. The
document flags when silhouette_penalty >= 1.0.

Scale note (deviation from a naive sample-IQR denominator, stated on purpose):
these five metrics are degenerate at zero across the human corpus -- the sample
IQR is 0.0 for every one, so the literal (m - median)/IQR with a 0.05 floor
reduces to m/0.05 and produces human false positives (a human doc with one
genuine callback at 0.17 lands at penalty > 1.0). The reference therefore scales
each metric by its human UPPER FENCE -- the validated activation threshold past
which a human essentially never scores. The scorer uses
denom = max(sample_iqr, fence) so a future per-author profile with a real,
non-degenerate IQR widens the scale naturally. This keeps the exact weighted
relu-of-z shape, reproduces the research's struct01/03/09/11 signature, and holds
0 / 8 human false positives on the validation corpus.

Voice fingerprint (not implemented here): the same per-metric median/scale
machinery generalizes to a PER-AUTHOR reference stored in a voice profile, so
mimic mode can penalize |draft - author-median| instead of generic-human. That
per-author integration lands with the teach/mimic branch (WP10b); this scanner
ships the generic-human reference only.

stdlib only. JSON to stdout. Exit 1 on flag, 0 clean, 2 on a missing file.
"""

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

from structure_scan import STOPWORDS as _STRUCTURE_STOPWORDS  # noqa: E402
from _lang import is_probably_english  # noqa: E402


REFERENCE_PATH = (
    Path(__file__).resolve().parent.parent
    / "evals" / "fixtures" / "silhouette" / "human_reference.json"
)

# Flag the document when the composite reaches this penalty (research-validated).
PENALTY_THRESHOLD = 1.0

# Minimum prose paragraphs before the silhouette metrics are meaningful.
MIN_PARAGRAPHS = 3


# silhouette_scan's stopword list is a pure superset of structure_scan's: same
# core function words plus pronouns/quantifiers that matter for content-bigram
# and callback-content comparisons but that structure_scan doesn't need.
SILHOUETTE_STOPWORDS = _STRUCTURE_STOPWORDS | frozenset({
    "our", "your", "their", "my", "me", "us", "them", "his", "her", "what",
    "which", "who", "when", "where", "how", "why", "there", "here", "about",
    "just", "more", "most", "some", "all", "also", "out", "up", "one", "two",
    "get", "got", "like", "much", "many", "very", "every", "only",
})

# Discourse cue classes for paragraph-opener roles. Copied verbatim from the
# validated research prototype (scratchpad/research-silhouette/silhouette_probe.py).
ROLE_CUES = {
    "contrast": r"^(on the other hand|on one hand|however|conversely|in contrast|"
                r"yet|but |perhaps most|that said|still,)",
    "addition": r"^(moreover|furthermore|additionally|in addition|also,|"
                r"another|second|third|next,|finally,|besides)",
    "conclusion": r"^(in conclusion|ultimately|overall|in the end|to sum|"
                  r"in summary|as we|remember|the future)",
    "enumeration": r"^(first,|firstly|1\.|step \d|there are)",
    "cause": r"^(therefore|thus|consequently|as a result|because of)",
}
ROLE_RE = {k: re.compile(v, re.I) for k, v in ROLE_CUES.items()}


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text.lower())


def content(text: str) -> list[str]:
    return [w for w in words(text) if len(w) > 3 and w not in SILHOUETTE_STOPWORDS]


def strip_md(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "\n\n", text)
    kept = []
    for line in text.splitlines():
        if re.match(r"\s{0,3}#{1,6}\s+", line):
            kept.append("")  # drop heading text from the prose view
            continue
        line = re.sub(r"^\s*[-*+]\s+", "", line)
        line = re.sub(r"^\s*\d+[.)]\s+", "", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        kept.append(line)
    return "\n".join(kept)


def paragraphs(text: str) -> list[str]:
    stripped = strip_md(text)
    return [re.sub(r"\s+", " ", p).strip()
            for p in re.split(r"\n\s*\n", stripped) if p.strip()]


# ---------------- METRICS (verbatim from the validated prototype) ----------------

def m_scaffold_opener_share(paras: list[str]):
    """Share of body paragraphs opening with a discourse-connective/scaffold cue."""
    body = paras[1:] if len(paras) > 1 else paras
    if not body:
        return 0.0
    hits = 0
    for p in body:
        for rx in ROLE_RE.values():
            if rx.search(p):
                hits += 1
                break
    return round(hits / len(body), 3)


def m_role_entropy(paras: list[str]):
    """Shannon entropy (bits) over opener role classes incl. 'topic' (none).
    A human never opens paragraphs with cue classes -> entropy 0; a template
    rotates several distinct cue classes -> positive entropy."""
    if len(paras) < 3:
        return None
    roles = []
    for p in paras:
        r = "topic"
        for name, rx in ROLE_RE.items():
            if rx.search(p):
                r = name
                break
        roles.append(r)
    counts = Counter(roles)
    n = len(roles)
    ent = -sum((c / n) * math.log2(c / n) for c in counts.values())
    return round(ent, 3)


def m_preview_fulfillment(paras: list[str]):
    """Share of body paragraphs whose opening content word appears in the
    intro paragraph (outline-following / preview-then-fulfill tell)."""
    if len(paras) < 4:
        return None
    intro = set(content(paras[0]))
    if not intro:
        return 0.0
    body = paras[1:-1] if len(paras) > 2 else paras[1:]
    hits = tot = 0
    for p in body:
        cs = content(p)
        if not cs:
            continue
        tot += 1
        if cs[0] in intro:
            hits += 1
    return round(hits / tot, 3) if tot else 0.0


def m_callback_content(paras: list[str]):
    """Content words introduced in the first third, ABSENT from the middle,
    reappearing in the last third: a recap loop, not a sustained topic."""
    n = len(paras)
    if n < 5:
        return None
    third = max(1, n // 3)
    early = set().union(*[set(content(paras[i])) for i in range(third)])
    mid = (set().union(*[set(content(paras[i])) for i in range(third, n - third)])
           if n - 2 * third > 0 else set())
    late = set().union(*[set(content(paras[i])) for i in range(n - third, n)])
    cb = (early & late) - mid
    return round(len(cb) / n, 3)


def m_heading_preview(text: str):
    """Share of ## heading head-nouns whose key word also appears in the intro
    paragraph = outline preview-then-fulfill. Measures outline-following, not
    heading presence, so it is retained under --genre docs."""
    heads = re.findall(r"(?m)^\s{0,3}#{2,3}\s+(.*)$", text)
    if len(heads) < 3:
        return None
    paras = paragraphs(text)
    intro = set(content(paras[0])) if paras else set()
    if not intro:
        return 0.0
    hit = 0
    for h in heads:
        hc = set(content(h))
        if hc & intro:
            hit += 1
    return round(hit / len(heads), 3)


# Metric registry: name -> (paragraph-based? / text-based?, function).
PARA_METRICS = {
    "scaffold_opener_share": m_scaffold_opener_share,
    "role_entropy_bits": m_role_entropy,
    "preview_fulfillment": m_preview_fulfillment,
    "callback_content": m_callback_content,
}
TEXT_METRICS = {
    "heading_preview": m_heading_preview,
}
METRIC_ORDER = [
    "scaffold_opener_share",
    "role_entropy_bits",
    "heading_preview",
    "preview_fulfillment",
    "callback_content",
]

SUGGESTIONS = {
    "scaffold_opener_share":
        "Open body paragraphs on their own specific claim, not a discourse cue.",
    "role_entropy_bits":
        "Stop rotating 'However / In addition / Ultimately' scaffold openers.",
    "heading_preview":
        "Headings restate the intro's outline; let sections carry new ground.",
    "preview_fulfillment":
        "The body just fulfills an outline previewed in the intro; drop the preview.",
    "callback_content":
        "The ending loops back to opening vocabulary; end on a concrete final point.",
}


def compute_metrics(text: str, paras: list[str]) -> dict:
    row = {}
    for name in METRIC_ORDER:
        if name in PARA_METRICS:
            row[name] = PARA_METRICS[name](paras)
        else:
            row[name] = TEXT_METRICS[name](text)
    return row


def load_reference(path: Path) -> dict:
    data = json.loads(path.read_text())
    return data["metrics"]


def relu(x: float) -> float:
    return x if x > 0 else 0.0


def flag(metric, value, threshold, detail, suggestion) -> dict:
    return {
        "metric": metric,
        "value": value,
        "threshold": threshold,
        "severity": "soft",
        "detail": detail,
        "suggestion": suggestion,
    }


# Metrics a given --genre suppresses outright. See the docstring in scan()
# for why only callback_content is suppressed under --genre docs.
GENRE_SUPPRESSIONS = {
    "docs": {"callback_content"},
}


def scan(text: str, reference: dict, genre: str = "prose") -> dict:
    # Genre is a passthrough echoed for parity with structure_scan.
    # --genre docs suppresses ONLY callback_content: reference docs, specs, and
    # doctrine conventionally reprise opening themes at the end, which is not
    # the essay recap coda the metric exists to catch (SIL rows pin both
    # directions). heading_preview is deliberately retained under docs because
    # it measures outline-following (a tell even in reference docs), and the
    # metric already clears legitimate academic roadmaps (struct17) on its own.
    # --genre social documents that loose social copy rarely has the
    # >=3-paragraph structure these metrics need.
    paras = paragraphs(text)
    base = {
        "genre": genre,
        "prose_paragraphs": len(paras),
    }
    if len(paras) < MIN_PARAGRAPHS:
        base.update({
            "flags": [],
            "flagged": {},
            "metrics": None,
            "penalty": None,
            "note": f"fewer than {MIN_PARAGRAPHS} prose paragraphs; "
                    "silhouette metrics not scored",
        })
        return base

    metrics = compute_metrics(text, paras)
    contributions = {}
    penalty = 0.0
    flags = []
    for name in METRIC_ORDER:
        if name in GENRE_SUPPRESSIONS.get(genre, set()):
            contributions[name] = 0.0
            continue
        ref = reference[name]
        value = metrics[name]
        if not isinstance(value, (int, float)):
            contributions[name] = None
            continue
        median = ref["median"]
        scale = max(ref["iqr"], ref["fence"])
        weight = ref["weight"]
        contribution = round(weight * relu((value - median) / scale), 3)
        contributions[name] = contribution
        penalty += contribution
        # A metric individually clears the human fence when value >= fence,
        # i.e. its contribution reaches its full weight.
        if value >= ref["fence"]:
            flags.append(flag(
                name,
                value,
                f"human fence {ref['fence']} (weight {weight})",
                f"{name} at {value} clears the human upper fence "
                f"{ref['fence']}.",
                SUGGESTIONS[name],
            ))
    penalty = round(penalty, 3)

    if penalty >= PENALTY_THRESHOLD:
        flags.insert(0, flag(
            "silhouette_penalty",
            penalty,
            f">= {PENALTY_THRESHOLD}",
            "The document's idea arrangement matches a templated AI silhouette "
            "(preview-then-fulfill, rotating scaffold openers, recap loop).",
            "Rearrange around the actual argument instead of a symmetric outline; "
            "cut previews and the closing recap.",
        ))

    base.update({
        "flags": flags,
        "flagged": {f["metric"]: True for f in flags},
        "metrics": metrics,
        "contributions": contributions,
        "penalty": penalty,
    })
    return base


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?")
    parser.add_argument("--genre", choices=["prose", "docs", "social"], default="prose")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not REFERENCE_PATH.exists():
        print(f"Missing reference: {REFERENCE_PATH}", file=sys.stderr)
        return 2
    reference = load_reference(REFERENCE_PATH)

    if args.path:
        path = Path(args.path)
        if not path.exists():
            print(f"Missing file: {path}", file=sys.stderr)
            return 2
        text = path.read_text(errors="replace")
    else:
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")

    result = scan(text, reference, args.genre)

    if not result.get("flags") and not is_probably_english(text):
        print(json.dumps({"non_english": True, "flags": [], "penalty": None}, indent=2))
        print("note: input appears non-English; scanner declined (English-only).", file=sys.stderr)
        return 0

    print(json.dumps(result, indent=2))
    is_flagged = bool(result.get("penalty") is not None
                      and result["penalty"] >= PENALTY_THRESHOLD)
    return 1 if is_flagged else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
