#!/usr/bin/env python3
"""Spike harness for Plan 015: per-author silhouette reference stability.

Read-only measurement script for plans/015-report-silhouette-stability.md.
Imports scripts/silhouette_scan.py via the same scripts-dir sys.path.insert
the scanner's own dual-mode import uses (so this harness works whether it's
invoked from the repo root or elsewhere), computes the five silhouette
metrics over four "author" corpora -- three synthetic voice authors
(evals/fixtures/voice/authors/{amara,boris,celia}) plus the committed human
silhouette fixtures (evals/fixtures/silhouette/corpus/human/) treated as a
4th author -- and answers three questions:

  1. Extraction  -- are per-author metric distributions degenerate
     (median/IQR) at these doc counts?
  2. Stability   -- how much do median/IQR swing under leave-one-out and (for
     corpora with >4 docs beyond the LOO fold) 4-doc random subsampling?
  3. Discrimination -- does a held-out doc score closer to its own author's
     per-author reference than to other authors' or the generic reference?

Nothing under scripts/ or evals/ is modified; this only reads fixtures and
scripts/silhouette_scan.py. fence/weight constants are copied read-only from
evals/check_silhouette.py (research-validated constants, not re-derived
here). Run: python3 plans/scratch/015-silhouette-stability.py
stdlib only. Deterministic: fixed SEED below.
"""

from __future__ import annotations

import json
import random
import statistics as st
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from silhouette_scan import METRIC_ORDER, compute_metrics, paragraphs  # noqa: E402

# ---------------------------------------------------------------- constants
SEED = 20260706  # date this spike was planned; fixed for reproducibility
N_SUBSAMPLES = 20
SUBSAMPLE_SIZE = 4

# Research-validated constants, copied read-only from evals/check_silhouette.py.
FENCE = {
    "scaffold_opener_share": 0.20,
    "role_entropy_bits": 0.80,
    "heading_preview": 0.20,
    "preview_fulfillment": 0.25,
    "callback_content": 0.30,
}
WEIGHT = {
    "scaffold_opener_share": 2.0,
    "role_entropy_bits": 1.0,
    "heading_preview": 1.0,
    "preview_fulfillment": 1.0,
    "callback_content": 1.5,
}
IQR_FLOOR = 0.05

# PRE-REGISTERED stability threshold (fixed before running, per plans/015).
STABILITY_SWING_FRACTION = 0.5  # median swing > 50% of fence = unstable metric
STABILITY_METRIC_COUNT = 2      # >= this many unstable metrics = author verdict fails

VOICE_AUTHORS_DIR = REPO_ROOT / "evals" / "fixtures" / "voice" / "authors"
HUMAN_CORPUS_DIR = REPO_ROOT / "evals" / "fixtures" / "silhouette" / "corpus" / "human"
GENERIC_REFERENCE_PATH = (
    REPO_ROOT / "evals" / "fixtures" / "silhouette" / "human_reference.json"
)


# ---------------------------------------------------------------- corpus IO
def load_author_corpora() -> dict[str, list[Path]]:
    corpora: dict[str, list[Path]] = {}
    for author_dir in sorted(VOICE_AUTHORS_DIR.iterdir()):
        if author_dir.is_dir():
            corpora[author_dir.name] = sorted(author_dir.glob("*.md"))
    corpora["human_fixtures"] = sorted(HUMAN_CORPUS_DIR.glob("*.txt"))
    return corpora


def compute_all_doc_metrics(corpora: dict[str, list[Path]]) -> dict[Path, dict]:
    """Compute each doc's metric row exactly once (folds reuse these)."""
    rows: dict[Path, dict] = {}
    for docs in corpora.values():
        for path in docs:
            text = path.read_text()
            paras = paragraphs(text)
            rows[path] = compute_metrics(text, paras)
    return rows


# ---------------------------------------------------------------- reference stats
def sample_iqr(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    q = st.quantiles(sorted(values), n=4, method="inclusive")
    return q[2] - q[0]


def author_reference(rows: list[dict]) -> dict:
    """median/iqr/n per metric over a list of per-doc metric dicts, skipping
    None (undercounted-paragraph) values. Mirrors evals/check_silhouette.py's
    build_reference() column logic, generalized to any author's doc list."""
    ref: dict[str, dict] = {}
    for name in METRIC_ORDER:
        vals = sorted(r[name] for r in rows if isinstance(r.get(name), (int, float)))
        if not vals:
            ref[name] = {"median": None, "iqr": None, "raw_iqr": None, "n": 0}
            continue
        raw_iqr = sample_iqr(vals)
        ref[name] = {
            "median": round(st.median(vals), 4),
            "iqr": round(max(raw_iqr, IQR_FLOOR), 4),
            "raw_iqr": round(raw_iqr, 4),
            "n": len(vals),
        }
    return ref


def load_generic_reference() -> dict:
    data = json.loads(GENERIC_REFERENCE_PATH.read_text())
    return data["metrics"]


# ---------------------------------------------------------------- distance
def distance(doc_row: dict, ref: dict) -> float | None:
    """Sum over metrics valid in both doc and reference of
    |value - ref_median| / max(ref_iqr, fence) -- the same denom = max(iqr,
    fence) scaling scan() itself uses. None if no metric can be compared."""
    total = 0.0
    used = 0
    for name in METRIC_ORDER:
        v = doc_row.get(name)
        m = ref.get(name, {})
        if not isinstance(v, (int, float)) or m.get("median") is None:
            continue
        scale = max(m["iqr"], FENCE[name])
        total += abs(v - m["median"]) / scale
        used += 1
    return total / used if used else None


# ---------------------------------------------------------------- step 1: extraction
def step1_extraction(corpora, doc_rows) -> dict:
    print("=" * 78)
    print("STEP 1: EXTRACTION -- per-author median/IQR/degenerate-count table")
    print("=" * 78)
    result = {}
    for author, docs in corpora.items():
        rows = [doc_rows[p] for p in docs]
        ref = author_reference(rows)
        degenerate = sum(1 for name in METRIC_ORDER if ref[name]["raw_iqr"] == 0.0)
        result[author] = {"n_docs": len(docs), "ref": ref, "degenerate_metrics": degenerate}
        print(f"\n-- {author} (n={len(docs)} docs) --")
        print(f"{'metric':<24}{'median':>10}{'raw_iqr':>10}{'n_valid':>10}{'degenerate':>12}")
        for name in METRIC_ORDER:
            m = ref[name]
            deg = "YES" if m["raw_iqr"] == 0.0 else "no"
            med = "None" if m["median"] is None else f"{m['median']:.3f}"
            iqr = "None" if m["raw_iqr"] is None else f"{m['raw_iqr']:.3f}"
            print(f"{name:<24}{med:>10}{iqr:>10}{m['n']:>10}{deg:>12}")
        print(f"  degenerate metrics (raw IQR == 0.0): {degenerate}/{len(METRIC_ORDER)}")
    return result


# ---------------------------------------------------------------- step 2: stability
def jackknife_folds(docs: list[Path]) -> list[list[Path]]:
    return [docs[:i] + docs[i + 1:] for i in range(len(docs))]


def random_subsample_folds(docs: list[Path], size: int, n_draws: int, rng: random.Random):
    if len(docs) <= size:
        return None  # can't subsample below full size
    return [rng.sample(docs, size) for _ in range(n_draws)]


def fold_swings(fold_doc_lists: list[list[Path]], doc_rows, full_ref: dict) -> dict:
    """max |fold_median - full_median| and max |fold_iqr - full_iqr| per metric
    across folds."""
    swings = {name: {"median": 0.0, "iqr": 0.0} for name in METRIC_ORDER}
    for fold_docs in fold_doc_lists:
        fold_rows = [doc_rows[p] for p in fold_docs]
        fold_ref = author_reference(fold_rows)
        for name in METRIC_ORDER:
            fm, fr = fold_ref[name], full_ref[name]
            if fm["median"] is not None and fr["median"] is not None:
                swings[name]["median"] = max(
                    swings[name]["median"], abs(fm["median"] - fr["median"])
                )
            if fm["raw_iqr"] is not None and fr["raw_iqr"] is not None:
                swings[name]["iqr"] = max(
                    swings[name]["iqr"], abs(fm["raw_iqr"] - fr["raw_iqr"])
                )
    return swings


def step2_stability(corpora, doc_rows, extraction) -> dict:
    print()
    print("=" * 78)
    print("STEP 2: STABILITY -- jackknife + 4-doc subsample swings vs. fence")
    print("=" * 78)
    rng = random.Random(SEED)
    result = {}
    for author, docs in corpora.items():
        full_ref = extraction[author]["ref"]
        print(f"\n-- {author} (n={len(docs)} docs) --")

        jk_folds = jackknife_folds(docs)
        jk_swings = fold_swings(jk_folds, doc_rows, full_ref)

        sub_folds = random_subsample_folds(docs, SUBSAMPLE_SIZE, N_SUBSAMPLES, rng)
        if sub_folds is None:
            print(
                f"  4-doc subsampling SKIPPED: n={len(docs)} docs means a 4-doc "
                f"subsample is a complement of exactly one held-out doc -- "
                f"identical in composition to a jackknife fold. Running it would "
                f"just re-poll the same {len(docs)} possible 4-doc sets with "
                f"replacement, adding no information beyond jackknife."
            )
            sub_swings = None
        elif len(docs) < SUBSAMPLE_SIZE:
            print(f"  4-doc subsampling SKIPPED: n={len(docs)} < {SUBSAMPLE_SIZE}.")
            sub_swings = None
        else:
            sub_swings = fold_swings(sub_folds, doc_rows, full_ref)

        print(
            f"{'metric':<24}{'fence':>8}{'jk_med_swing':>14}{'jk_%fence':>11}"
            f"{'sub_med_swing':>15}{'sub_%fence':>12}{'verdict':>10}"
        )
        unstable_count = 0
        metric_verdicts = {}
        for name in METRIC_ORDER:
            fence = FENCE[name]
            jk = jk_swings[name]["median"]
            jk_pct = (jk / fence * 100) if fence else float("nan")
            if sub_swings is not None:
                sub = sub_swings[name]["median"]
                sub_pct = sub / fence * 100 if fence else float("nan")
                sub_str = f"{sub:.3f}"
                sub_pct_str = f"{sub_pct:.0f}%"
                worst = max(jk, sub)
            else:
                sub_str = "n/a"
                sub_pct_str = "n/a"
                worst = jk
            unstable = worst > STABILITY_SWING_FRACTION * fence
            metric_verdicts[name] = unstable
            if unstable:
                unstable_count += 1
            print(
                f"{name:<24}{fence:>8.2f}{jk:>14.3f}{jk_pct:>10.0f}%"
                f"{sub_str:>15}{sub_pct_str:>12}{'UNSTABLE' if unstable else 'ok':>10}"
            )
        author_verdict = unstable_count >= STABILITY_METRIC_COUNT
        print(
            f"  {unstable_count}/{len(METRIC_ORDER)} metrics UNSTABLE "
            f"(threshold: >={STABILITY_METRIC_COUNT} => author verdict fails) "
            f"=> author verdict: {'NOT STABLE' if author_verdict else 'stable'}"
        )
        result[author] = {
            "jk_swings": jk_swings,
            "sub_swings": sub_swings,
            "metric_verdicts": metric_verdicts,
            "unstable_count": unstable_count,
            "author_verdict_not_stable": author_verdict,
        }
    return result


# ---------------------------------------------------------------- step 3: discrimination
def step3_discrimination(corpora, doc_rows, extraction) -> dict:
    print()
    print("=" * 78)
    print("STEP 3: DISCRIMINATION -- nearest-reference accuracy over held-out docs")
    print("=" * 78)
    generic_ref = load_generic_reference()
    authors = list(corpora.keys())
    full_refs = {a: extraction[a]["ref"] for a in authors}

    total = 0
    correct = 0
    rows_out = []
    for author, docs in corpora.items():
        for held_out in docs:
            # own-author reference computed LOO (exclude the held-out doc itself)
            remaining = [p for p in docs if p != held_out]
            own_loo_ref = author_reference([doc_rows[p] for p in remaining])

            candidates = {author: own_loo_ref}
            for other in authors:
                if other != author:
                    candidates[other] = full_refs[other]
            candidates["generic"] = generic_ref

            doc_row = doc_rows[held_out]
            dists = {name: distance(doc_row, ref) for name, ref in candidates.items()}
            valid_dists = {k: v for k, v in dists.items() if v is not None}
            nearest = min(valid_dists, key=valid_dists.get) if valid_dists else None

            total += 1
            is_correct = nearest == author
            if is_correct:
                correct += 1
            rows_out.append(
                {
                    "author": author,
                    "doc": held_out.name,
                    "nearest": nearest,
                    "correct": is_correct,
                    "distances": {k: round(v, 3) for k, v in valid_dists.items()},
                }
            )

    print(f"\n{'author':<16}{'doc':<24}{'nearest':<16}{'correct':<10}distances")
    for r in rows_out:
        dist_str = ", ".join(f"{k}={v:.2f}" for k, v in sorted(r["distances"].items()))
        print(
            f"{r['author']:<16}{r['doc']:<24}{str(r['nearest']):<16}"
            f"{'YES' if r['correct'] else 'no':<10}{dist_str}"
        )

    accuracy = correct / total if total else 0.0
    print(f"\nOverall nearest-reference accuracy: {correct}/{total} = {accuracy:.1%}")

    per_author = {}
    for author in authors:
        a_rows = [r for r in rows_out if r["author"] == author]
        a_correct = sum(1 for r in a_rows if r["correct"])
        per_author[author] = (a_correct, len(a_rows))
        print(f"  {author}: {a_correct}/{len(a_rows)} = {a_correct / len(a_rows):.1%}")

    return {
        "overall_accuracy": accuracy,
        "overall_correct": correct,
        "overall_total": total,
        "per_author": per_author,
        "rows": rows_out,
    }


# ---------------------------------------------------------------- main
def main() -> int:
    corpora = load_author_corpora()
    doc_rows = compute_all_doc_metrics(corpora)

    print(f"Loaded {len(corpora)} author corpora:")
    for author, docs in corpora.items():
        print(f"  {author}: {len(docs)} docs")
    if any(len(docs) < 5 for docs in corpora.values()):
        small = [a for a, d in corpora.items() if len(d) < 5]
        if all(len(corpora[a]) < 5 for a in corpora):
            print(f"STOP CONDITION: all author corpora have <5 docs.", file=sys.stderr)
            return 2
        print(f"NOTE: shrinking design for small corpora: {small}")

    extraction = step1_extraction(corpora, doc_rows)
    stability = step2_stability(corpora, doc_rows, extraction)
    discrimination = step3_discrimination(corpora, doc_rows, extraction)

    print()
    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    for author in corpora:
        deg = extraction[author]["degenerate_metrics"]
        verdict = "NOT STABLE" if stability[author]["author_verdict_not_stable"] else "stable"
        a_correct, a_total = discrimination["per_author"][author]
        print(
            f"  {author}: {deg}/{len(METRIC_ORDER)} degenerate metrics, "
            f"stability={verdict}, discrimination={a_correct}/{a_total}"
        )
    print(f"  overall discrimination accuracy: {discrimination['overall_accuracy']:.1%}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
