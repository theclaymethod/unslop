#!/usr/bin/env python3
"""Macro-structure hill-climb: generate -> scan -> targeted directives -> regenerate.

The recorded parity matrix (references/pipeline.md, "Behavioral parity matrix")
shows every model tested -- opus, sonnet, haiku, the GPT ladder, the open-weights
flagships -- fails macro-structure self-checking: told in prose to drop a
conclusion coda / connective scaffold / outline echo, each ships it anyway. No
model reliably self-checks document SHAPE from a prose instruction.

But the deterministic scanners SEE those failures precisely. structure_scan.py
catches surface macro tells (coda, opener repetition, connective/Every openers,
signposts, participial closers, staccato, listicle, burstiness); silhouette_scan.py
catches idea-arrangement tells (scaffold openers, rotating cue classes,
preview-then-fulfill, the recap/callback loop, outline-following headings). So a
LOOP can climb where a single pass cannot:

    generate -> scan both -> if clean, done
             -> else convert each finding into a TARGETED directive that names
                WHERE and WHAT (the model can't see the tell, so the directive
                must locate it for it) -> feed directives + current draft back ->
                regenerate -> repeat, capped at N rounds.

The core IP is the DIRECTIVE BUILDER (build_directives): a deterministic mapping
from scanner findings to instructions that name the offending paragraph, opener
word, callback vocabulary, or region -- derived by re-reading the draft with the
scanners' own helpers, not by echoing the scanner's generic suggestion string.

Two candidate sources, both driving the identical scan/directive/regenerate path:

* LIVE (default): each round assembles a prompt (the base task + the current
  draft + the round's directives) and invokes ``--generate-cmd`` once, feeding the
  prompt on stdin and reading the new draft on stdout. ``MOCK_ROUND`` carries the
  round index in the environment (a real generator ignores it).
* MOCK: ``--generate-cmd`` points at a deterministic stand-in
  (evals/fixtures/climb/mock_generate.py --scenario NAME) that emits a canned
  per-round fixture. The CLIMB-* eval rows drive this path, LLM-free.

Preservation guard: each round is validated with validate_preservation against a
fixed anchor -- the ``--source-file`` authoritative text when given (round 0
included), otherwise the first generated draft -- so climbing toward clean
structure can never eat a fact, number, or negation. A regression aborts the climb.

Honest terminal states (exit codes):
    converged               0  both scanners clean
    capped                  3  hit the round cap still dirty
    preservation_violation  4  a round dropped a must-keep constraint
    (missing prompt/gen)    2  bad input or a failed generator call

JSON report to --out/report.json; a one-line summary to stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import structure_scan  # noqa: E402
import silhouette_scan  # noqa: E402
import validate_preservation  # noqa: E402

EXIT_CONVERGED = 0
EXIT_BAD_INPUT = 2
EXIT_CAPPED = 3
EXIT_PRESERVATION = 4

SILHOUETTE_REFERENCE = silhouette_scan.load_reference(silhouette_scan.REFERENCE_PATH)


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #

def _first_words(text: str, n: int = 8) -> str:
    toks = text.strip().split()
    head = " ".join(toks[:n])
    return head + ("..." if len(toks) > n else "")


def scan_draft(text: str, genre: str) -> dict:
    """Run both macro scanners and fold their output into a climb-round view.

    structure is dirty iff it emits any flag (its exit-1 semantics).
    silhouette is dirty iff its composite penalty clears the blocking threshold
    (its exit-1 semantics); individual metric flags still inform the directives.
    """
    struct = structure_scan.scan(text, genre)
    silh = silhouette_scan.scan(text, SILHOUETTE_REFERENCE, genre)

    structure_flags = [f["metric"] for f in struct["flags"]]
    penalty = silh.get("penalty")
    silhouette_dirty = penalty is not None and penalty >= silhouette_scan.PENALTY_THRESHOLD
    # Individual metric flags (exclude the composite pseudo-metric).
    silh_metric_flags = [f["metric"] for f in silh.get("flags", [])
                         if f["metric"] != "silhouette_penalty"]
    # If the composite trips on summed partial contributions with no single
    # metric clearing its fence, still count it as one violation so the round's
    # dirtiness is never invisible to the monotonic-progress tracker.
    silh_violations = len(silh_metric_flags) if silh_metric_flags else (1 if silhouette_dirty else 0)

    clean = (not structure_flags) and (not silhouette_dirty)
    return {
        "structure": struct,
        "silhouette": silh,
        "structure_flags": structure_flags,
        "silhouette_flags": silh_metric_flags,
        "silhouette_penalty": penalty,
        "silhouette_dirty": silhouette_dirty,
        "violation_count": len(structure_flags) + silh_violations,
        "clean": clean,
    }


# --------------------------------------------------------------------------- #
# Directive builder -- the core IP. Each entry names WHERE and WHAT, derived by
# re-reading the draft with the scanners' own helpers.
# --------------------------------------------------------------------------- #

def _openers(sentences: list[str]) -> list[str]:
    """First word of each sentence, mirroring structure_scan's opener census
    (drops the pure-enumeration leaders it also ignores)."""
    enumeration = {"the", "a", "an", "section", "chapter", "figure", "table",
                   "step", "part", "appendix"}
    out = []
    for s in sentences:
        ws = structure_scan.words(s)
        if ws and ws[0] not in enumeration:
            out.append(ws[0])
    return out


def _dir_conclusion_coda(text, paras, sentences) -> str:
    last = paras[-1] if paras else ""
    stock = structure_scan.CODA_START_RE.search(last)
    where = f'The final paragraph ("{_first_words(last)}")'
    if stock:
        return (f'{where} opens on the stock coda "{stock.group(0).strip()}". '
                "Delete the wrap-up or rewrite the final paragraph to close on a "
                "specific new fact, not a restatement of the opening.")
    return (f"{where} restates the opening instead of adding information. Delete it "
            "or rewrite the final paragraph to end on a concrete new point, not a recap.")


def _dir_opener_repetition(text, paras, sentences) -> str:
    openers = _openers(sentences)
    if not openers:
        return "Sentence openings repeat in a template rhythm; vary the sentence openers."
    counts = Counter(openers)
    word, n = counts.most_common(1)[0]
    return (f'Sentence openings repeat: "{word}" leads {n} of {len(openers)} '
            "sentences. Rewrite so no single word starts more than a couple of "
            "sentences, and avoid an identical-opener run.")


def _dir_connective_openers(text, paras, sentences) -> str:
    hits = []
    for i, p in enumerate(paras):
        m = structure_scan.CONNECTIVE_OPENERS.search(p)
        if m:
            hits.append(f'paragraph {i + 1} ("{m.group(0).strip()}")')
    named = "; ".join(hits) if hits else "several paragraphs"
    return (f"These paragraphs open with a formal transition word: {named}. Replace "
            "each scaffold opener with a specific topic sentence about that paragraph.")


def _dir_every_template(text, paras, sentences) -> str:
    hits = []
    for i, p in enumerate(paras):
        if structure_scan.EVERY_OPENER_RE.search(p):
            hits.append(f'paragraph {i + 1} ("{_first_words(p, 4)}")')
    named = "; ".join(hits) if hits else "multiple paragraphs"
    return (f"These paragraphs repeat the 'Every ___ is/does ...' opener template: "
            f"{named}. Vary the openings so the rhythm stops being mechanical.")


def _dir_signpost(text, paras, sentences) -> str:
    found = sorted({m.strip() for m in structure_scan.SIGNPOST_RE.findall(
        "\n\n".join(paras))})
    named = ", ".join(f'"{f}"' for f in found) if found else "roadmap phrases"
    return (f"The text narrates its own structure with signpost phrases ({named}). "
            "Remove the roadmap language and let the content carry the order.")


def _dir_participial_closer(text, paras, sentences) -> str:
    examples = []
    for s in sentences:
        m = structure_scan.CLOSER_RE.search(s)
        if m:
            examples.append(f'"...{m.group(1)}..."')
        if len(examples) >= 3:
            break
    named = ", ".join(examples) if examples else "editorial -ing tails"
    return (f"Sentences end on editorial -ing consequence tails ({named}). Make each "
            "consequence a concrete claim or cut the trailing clause.")


def _dir_burstiness(text, paras, sentences) -> str:
    lengths = [len(structure_scan.words(s)) for s in sentences]
    mean = round(sum(lengths) / len(lengths), 1) if lengths else 0
    return (f"Sentence lengths are uniform (about {mean} words each across "
            f"{len(lengths)} sentences). Vary the cadence: cut some sentences well "
            "under that and let others run well over it.")


def _dir_bold_colon(text, paras, sentences) -> str:
    labels = structure_scan.BOLD_COLON_RE.findall(text)
    n = len(labels)
    return (f"There are {n} bold-label colon listicle lines. Convert them to flowing "
            "prose or plain sentences instead of a bolded label stack.")


def _dir_one_line_staccato(text, paras, sentences) -> str:
    return ("Most paragraphs are single short sentences (staccato beats). Merge "
            "related beats into fuller paragraphs and vary paragraph length.")


STRUCTURE_DIRECTIVES = {
    "conclusion_coda": _dir_conclusion_coda,
    "opener_repetition": _dir_opener_repetition,
    "connective_paragraph_openers": _dir_connective_openers,
    "every_template_openers": _dir_every_template,
    "signpost_density": _dir_signpost,
    "participial_closer_share": _dir_participial_closer,
    "sentence_burstiness": _dir_burstiness,
    "bold_colon_listicle": _dir_bold_colon,
    "one_line_staccato": _dir_one_line_staccato,
}


def _silh_paras(text):
    return silhouette_scan.paragraphs(text)


def _dir_scaffold_opener(text, sparas) -> str:
    body = sparas[1:] if len(sparas) > 1 else sparas
    hits = []
    for i, p in enumerate(body):
        for name, rx in silhouette_scan.ROLE_RE.items():
            m = rx.search(p)
            if m:
                hits.append(f'"{m.group(0).strip()}" ({name})')
                break
    named = ", ".join(hits) if hits else "discourse cues"
    return (f"Body paragraphs open on discourse cues instead of their own claim: "
            f"{named}. Start each body paragraph on the specific point it makes.")


def _dir_role_entropy(text, sparas) -> str:
    classes = []
    for p in sparas:
        for name, rx in silhouette_scan.ROLE_RE.items():
            if rx.search(p):
                classes.append(name)
                break
    named = ", ".join(sorted(set(classes))) if classes else "several cue classes"
    return (f"Paragraph openers rotate through scaffold cue classes ({named}) -- the "
            "'However / In addition / Ultimately' template. Drop the rotation and "
            "open paragraphs on content.")


def _dir_preview_fulfillment(text, sparas) -> str:
    if len(sparas) < 2:
        return ("The body just fulfills an outline previewed in the intro; drop the "
                "preview and let the argument unfold.")
    intro = set(silhouette_scan.content(sparas[0]))
    body = sparas[1:-1] if len(sparas) > 2 else sparas[1:]
    echoes = []
    for p in body:
        cs = silhouette_scan.content(p)
        if cs and cs[0] in intro:
            echoes.append(f'"{cs[0]}"')
    named = ", ".join(sorted(set(echoes))) if echoes else "intro keywords"
    return (f"Body paragraphs open on words previewed in the intro ({named}) -- a "
            "preview-then-fulfill outline. Cut the intro preview so sections carry "
            "new ground.")


def _dir_callback_content(text, sparas) -> str:
    n = len(sparas)
    third = max(1, n // 3)
    early = set().union(*[set(silhouette_scan.content(sparas[i])) for i in range(third)]) if n else set()
    mid = (set().union(*[set(silhouette_scan.content(sparas[i])) for i in range(third, n - third)])
           if n - 2 * third > 0 else set())
    late = set().union(*[set(silhouette_scan.content(sparas[i])) for i in range(n - third, n)]) if n else set()
    cb = sorted((early & late) - mid)
    named = ", ".join(f'"{w}"' for w in cb[:6]) if cb else "the opening's vocabulary"
    return (f"The ending re-uses the opening's vocabulary ({named}) after it was "
            "absent from the middle -- a recap loop. End on the last concrete point "
            "instead of circling back to the opening.")


def _dir_heading_preview(text, sparas) -> str:
    heads = re.findall(r"(?m)^\s{0,3}#{2,3}\s+(.*)$", text)
    intro = set(silhouette_scan.content(sparas[0])) if sparas else set()
    echoing = [h.strip() for h in heads if set(silhouette_scan.content(h)) & intro]
    named = "; ".join(f'"{h}"' for h in echoing[:4]) if echoing else "the section headings"
    return (f"Headings restate the intro's outline ({named}). Let each section break "
            "new ground rather than echo the preview.")


def _dir_silhouette_composite(text, sparas) -> str:
    return ("The document's overall idea arrangement matches a templated silhouette "
            "(symmetric preview-then-fulfill outline with a closing recap). Rearrange "
            "around the actual argument: cut the previews and the closing loop.")


SILHOUETTE_DIRECTIVES = {
    "scaffold_opener_share": _dir_scaffold_opener,
    "role_entropy_bits": _dir_role_entropy,
    "preview_fulfillment": _dir_preview_fulfillment,
    "callback_content": _dir_callback_content,
    "heading_preview": _dir_heading_preview,
}


def build_directives(text: str, scan: dict, genre: str) -> list[dict]:
    """Deterministic findings -> targeted directives. Each directive names the
    offending location and the fix, because the model cannot see the tell."""
    paras = structure_scan.prose_paragraphs(text)
    prose_text = "\n\n".join(paras)
    sentences = structure_scan.split_sentences(prose_text)
    sparas = _silh_paras(text)

    directives: list[dict] = []
    for metric in scan["structure_flags"]:
        fn = STRUCTURE_DIRECTIVES.get(metric)
        if fn is None:
            continue
        directives.append({
            "source": "structure",
            "metric": metric,
            "directive": fn(text, paras, sentences),
        })

    fired_silh = False
    for metric in scan["silhouette_flags"]:
        fn = SILHOUETTE_DIRECTIVES.get(metric)
        if fn is None:
            continue
        fired_silh = True
        directives.append({
            "source": "silhouette",
            "metric": metric,
            "directive": fn(text, sparas),
        })
    # Composite tripped on summed partials with no single metric flag: still
    # tell the model the shape is wrong.
    if scan["silhouette_dirty"] and not fired_silh:
        directives.append({
            "source": "silhouette",
            "metric": "silhouette_penalty",
            "directive": _dir_silhouette_composite(text, sparas),
        })
    return directives


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #

def build_prompt(base_prompt: str, draft: str, directives: list[dict], round_index: int) -> str:
    if round_index == 0 or not draft:
        return base_prompt.rstrip() + "\n"
    lines = [base_prompt.rstrip(), "",
             "You previously wrote this draft:", "---", draft.strip(), "---", "",
             "A structural scanner you cannot run found these specific problems. "
             "Fix exactly these and nothing else. Keep every fact, number, name, "
             "and negation intact:"]
    for i, d in enumerate(directives, 1):
        lines.append(f"{i}. {d['directive']}")
    lines += ["", "Return only the rewritten piece."]
    return "\n".join(lines) + "\n"


def generate(generate_cmd: str, prompt: str, round_index: int) -> str:
    env = dict(os.environ, MOCK_ROUND=str(round_index))
    proc = subprocess.run(
        shlex.split(generate_cmd), input=prompt, text=True,
        capture_output=True, env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"generate-cmd failed ({proc.returncode}): {proc.stderr.strip()[:300]}")
    return proc.stdout


# --------------------------------------------------------------------------- #
# Loop
# --------------------------------------------------------------------------- #

def climb(base_prompt, generate_cmd, genre, max_rounds, source_text=None):
    rounds = []
    # Preservation anchor. With an explicit --source-file, facts are pinned to the
    # authoritative source and EVERY round (round 0 included) is validated against
    # it; this is the real de-slop case (you own a document, its facts must
    # survive). Without one, the first generated draft becomes the anchor and
    # rounds after it are validated against it -- the mock scenarios' contract.
    anchor_text = source_text
    have_source = source_text is not None
    draft = ""
    directives: list[dict] = []
    terminal = None
    converged = False

    for i in range(max_rounds):
        draft = generate(generate_cmd, build_prompt(base_prompt, draft, directives, i), i)
        scan = scan_draft(draft, genre)

        preservation = None
        if anchor_text is None:
            anchor_text = draft
        if have_source or i > 0:
            pres = validate_preservation.validate_preservation(anchor_text, draft)
            preservation = {
                "passed": pres["passed"],
                "total_constraints": pres["total_constraints"],
                "preserved": pres["preserved"],
                "missing": pres["missing"],
            }

        directives = [] if scan["clean"] else build_directives(draft, scan, genre)

        rounds.append({
            "index": i,
            "structure_flags": scan["structure_flags"],
            "silhouette_flags": scan["silhouette_flags"],
            "silhouette_penalty": scan["silhouette_penalty"],
            "violation_count": scan["violation_count"],
            "clean": scan["clean"],
            "preservation": preservation,
            "directives": directives,
            "draft": draft,
        })

        if preservation is not None and not preservation["passed"]:
            terminal = "preservation_violation"
            break
        if scan["clean"]:
            terminal = "converged"
            converged = True
            break

    if terminal is None:
        terminal = "capped"

    return rounds, terminal, converged


def build_report(args, rounds, terminal, converged):
    initial = rounds[0]["violation_count"] if rounds else None
    final = rounds[-1]["violation_count"] if rounds else None
    return {
        "genre": args.genre,
        "max_rounds": args.max_rounds,
        "rounds_used": len(rounds),
        "terminal_state": terminal,
        "converged": converged,
        "initial_violations": initial,
        "final_violations": final,
        "violation_trajectory": [r["violation_count"] for r in rounds],
        "rounds": rounds,
    }


def write_outputs(out_dir, report):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if report["rounds"]:
        (out / "final.md").write_text(report["rounds"][-1]["draft"])


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prompt-file", required=True,
                   help="base task prompt handed to the generator each round")
    p.add_argument("--out", required=True)
    p.add_argument("--generate-cmd", default="claude -p")
    p.add_argument("--max-rounds", type=int, default=4)
    p.add_argument("--genre", choices=["prose", "docs", "social"], default="prose")
    p.add_argument("--source-file",
                   help="authoritative text whose facts must survive every round; "
                        "when set, preservation is anchored here (round 0 included) "
                        "instead of to the first generated draft")
    return p.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    prompt_path = Path(args.prompt_file)
    if not prompt_path.exists():
        print(f"missing prompt file: {args.prompt_file}", file=sys.stderr)
        return EXIT_BAD_INPUT
    base_prompt = prompt_path.read_text(errors="replace")
    if args.max_rounds < 1:
        print("--max-rounds must be >= 1", file=sys.stderr)
        return EXIT_BAD_INPUT

    source_text = None
    if args.source_file:
        src = Path(args.source_file)
        if not src.exists():
            print(f"missing source file: {args.source_file}", file=sys.stderr)
            return EXIT_BAD_INPUT
        source_text = src.read_text(errors="replace")

    try:
        rounds, terminal, converged = climb(
            base_prompt, args.generate_cmd, args.genre, args.max_rounds,
            source_text=source_text)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return EXIT_BAD_INPUT

    report = build_report(args, rounds, terminal, converged)
    write_outputs(args.out, report)

    print(json.dumps({
        "terminal_state": report["terminal_state"],
        "converged": report["converged"],
        "rounds_used": report["rounds_used"],
        "initial_violations": report["initial_violations"],
        "final_violations": report["final_violations"],
    }, sort_keys=True))

    return {
        "converged": EXIT_CONVERGED,
        "capped": EXIT_CAPPED,
        "preservation_violation": EXIT_PRESERVATION,
    }[terminal]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
