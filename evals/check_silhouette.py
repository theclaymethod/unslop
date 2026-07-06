#!/usr/bin/env python3
"""Drift and separation gate for the silhouette scanner.

Two modes:

  --reference    Regenerate the human reference distribution from the named
                 source docs and assert it equals the committed
                 evals/fixtures/silhouette/human_reference.json. This is the
                 drift gate: editing the scanner's metrics or the human corpus
                 without regenerating the reference fails here. Pass --write to
                 rewrite the committed file (regeneration, not a check).

  --separation   Score the in-repo ai/ and human/ corpora with the committed
                 reference and assert the research-validated separation:
                 >= 8/12 ai docs flagged and 0/8 human docs flagged.

Exit 0 on success, 1 on drift / separation failure, 2 on a missing input.
stdlib only.
"""

import argparse
import json
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from scripts.silhouette_scan import (  # noqa: E402
    METRIC_ORDER,
    PENALTY_THRESHOLD,
    compute_metrics,
    paragraphs,
    scan,
)

REFERENCE_PATH = ROOT / "evals" / "fixtures" / "silhouette" / "human_reference.json"
CORPUS = ROOT / "evals" / "fixtures" / "silhouette" / "corpus"

# Research-validated constants (scratchpad/research/silhouette.md). fence is the
# human upper fence used as the per-metric scale floor; weight is the composite
# weight. These are hand-validated, not corpus-derived, so they live here and are
# baked into the regenerated reference file.
RESEARCH_FENCE = {
    "scaffold_opener_share": 0.20,
    "role_entropy_bits": 0.80,
    "heading_preview": 0.20,
    "preview_fulfillment": 0.25,
    "callback_content": 0.30,
}
RESEARCH_WEIGHT = {
    "scaffold_opener_share": 2.0,
    "role_entropy_bits": 1.0,
    "heading_preview": 1.0,
    "preview_fulfillment": 1.0,
    "callback_content": 1.5,
}
IQR_FLOOR = 0.05

# Human reference sources, relative to the repo root. macro-probe human docs plus
# the human-ish (structure_scan-clean) structure fixtures.
SOURCES = [
    "evals/fixtures/silhouette/corpus/human/01_linkedin.txt",
    "evals/fixtures/silhouette/corpus/human/02_blog_intro.txt",
    "evals/fixtures/silhouette/corpus/human/03_howto.txt",
    "evals/fixtures/silhouette/corpus/human/04_essay.txt",
    "evals/fixtures/silhouette/corpus/human/05_readme.txt",
    "evals/fixtures/silhouette/corpus/human/06_email.txt",
    "evals/fixtures/silhouette/corpus/human/07_personal_story.txt",
    "evals/fixtures/silhouette/corpus/human/08_technical_explainer.txt",
    "evals/fixtures/structure/struct02_bursty_narrative.md",
    "evals/fixtures/structure/struct04_concrete_end.md",
    "evals/fixtures/structure/struct10_varied_openers.md",
    "evals/fixtures/structure/struct12_moderate_signpost.md",
    "evals/fixtures/structure/struct15_one_closer.md",
    "evals/fixtures/structure/struct16_parallel_enumeration.md",
    "evals/fixtures/structure/struct17_academic_roadmap.md",
]


def sample_iqr(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    q = st.quantiles(values, n=4, method="inclusive")
    return q[2] - q[0]


def build_reference() -> dict:
    columns = {name: [] for name in METRIC_ORDER}
    for rel in SOURCES:
        path = ROOT / rel
        if not path.exists():
            raise FileNotFoundError(rel)
        text = path.read_text()
        paras = paragraphs(text)
        if len(paras) < 3:
            continue
        row = compute_metrics(text, paras)
        for name in METRIC_ORDER:
            v = row[name]
            if isinstance(v, (int, float)):
                columns[name].append(v)

    metrics = {}
    for name in METRIC_ORDER:
        vals = sorted(columns[name])
        median = round(st.median(vals), 4) if vals else 0.0
        iqr = round(max(sample_iqr(vals), IQR_FLOOR), 4)
        metrics[name] = {
            "median": median,
            "iqr": iqr,
            "fence": RESEARCH_FENCE[name],
            "weight": RESEARCH_WEIGHT[name],
            "n": len(vals),
        }

    return {
        "description": (
            "Human reference distribution for scripts/silhouette_scan.py. "
            "Regenerate with: python3 evals/check_silhouette.py --reference --write. "
            "median/iqr/n are derived from the sources below; fence and weight are "
            "research-validated constants (scratchpad/research/silhouette.md). The "
            "scorer scales each metric by max(iqr, fence): the sample IQR is "
            "degenerate at zero for these one-sided tells, so the fence is the "
            "effective scale."
        ),
        "penalty_threshold": PENALTY_THRESHOLD,
        "iqr_floor": IQR_FLOOR,
        "sources": SOURCES,
        "metric_order": METRIC_ORDER,
        "metrics": metrics,
    }


def mode_reference(write: bool) -> int:
    try:
        generated = build_reference()
    except FileNotFoundError as e:
        print(f"Missing reference source: {e}", file=sys.stderr)
        return 2

    serialized = json.dumps(generated, indent=2) + "\n"
    if write:
        REFERENCE_PATH.write_text(serialized)
        print(f"wrote {REFERENCE_PATH}")
        return 0

    if not REFERENCE_PATH.exists():
        print(f"Missing reference file: {REFERENCE_PATH}", file=sys.stderr)
        return 2
    committed = json.loads(REFERENCE_PATH.read_text())
    if committed != generated:
        print("human_reference.json is out of sync with the sources.")
        print("Regenerate: python3 evals/check_silhouette.py --reference --write")
        return 1
    print(f"reference ok: {len(generated['metrics'])} metrics over "
          f"{len(SOURCES)} human sources")
    return 0


def mode_separation() -> int:
    ai_dir = CORPUS / "ai"
    human_dir = CORPUS / "human"
    if not REFERENCE_PATH.exists():
        print(f"Missing reference file: {REFERENCE_PATH}", file=sys.stderr)
        return 2
    if not ai_dir.is_dir() or not human_dir.is_dir():
        print(f"Missing corpus under {CORPUS}", file=sys.stderr)
        return 2
    reference = json.loads(REFERENCE_PATH.read_text())["metrics"]

    def flagged(directory: Path) -> list[tuple[str, float, bool]]:
        out = []
        for p in sorted(directory.glob("*.txt")):
            result = scan(p.read_text(), reference)
            penalty = result.get("penalty") or 0.0
            out.append((p.name, penalty, penalty >= PENALTY_THRESHOLD))
        return out

    ai = flagged(ai_dir)
    human = flagged(human_dir)
    ai_hits = sum(1 for _, _, f in ai if f)
    human_hits = sum(1 for _, _, f in human if f)

    print(f"AI corpus:    {ai_hits}/{len(ai)} flagged")
    for name, pen, f in ai:
        print(f"  {'FLAG' if f else '    '} {name:34} penalty={pen:.2f}")
    print(f"HUMAN corpus: {human_hits}/{len(human)} flagged")
    for name, pen, f in human:
        print(f"  {'FLAG' if f else '    '} {name:34} penalty={pen:.2f}")

    ok = ai_hits >= 8 and len(ai) == 12 and human_hits == 0 and len(human) == 8
    if not ok:
        print("\nseparation FAILED: require >= 8/12 ai flagged and 0/8 human flagged")
        return 1
    print(f"\nseparation ok: {ai_hits}/12 ai flagged, {human_hits}/8 human flagged")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", action="store_true",
                        help="check the committed human reference against the sources")
    parser.add_argument("--separation", action="store_true",
                        help="check ai/human corpus separation")
    parser.add_argument("--write", action="store_true",
                        help="with --reference, regenerate the committed reference file")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not args.reference and not args.separation:
        args.reference = args.separation = True
    rc = 0
    if args.reference:
        rc = mode_reference(args.write) or rc
    if args.separation and not args.write:
        rc = mode_separation() or rc
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
