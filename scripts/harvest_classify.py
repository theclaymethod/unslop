#!/usr/bin/env python3
"""Classify harvested candidates into situation/register coverage cells."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harvest_samples import DATE_FLOOR, recency_value  # noqa: E402


CELLS = [
    "numbers_data",
    "question_addressed",
    "anecdote_markers",
    "disagreement",
    "openings_closings",
]


def load_candidates(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        return data.get("candidates", [])
    if isinstance(data, list):
        return data
    raise ValueError("candidates file must contain a list or {candidates: [...]}")


def cells_for(text: str) -> list[str]:
    lowered = text.lower()
    cells = []
    if re.search(r"\b\d+(?:[,.]\d+)?%?\b", lowered):
        cells.append("numbers_data")
    if "?" in text or re.search(r"\b(?:why|how|what|when|where|which)\b", lowered):
        cells.append("question_addressed")
    if re.search(r"\b(?:last quarter|yesterday|once|during|when we|i noticed|i remember)\b", lowered):
        cells.append("anecdote_markers")
    if re.search(r"\b(?:disagree|however|instead|not convinced|push back)\b", lowered):
        cells.append("disagreement")
    if re.search(r"\b(?:hi|thanks|best|regards|closing|opening|first off)\b", lowered):
        cells.append("openings_closings")
    return cells


def quality_for(candidate: dict[str, Any], cells: list[str]) -> int:
    words = int(candidate.get("words") or len(re.findall(r"\w+", candidate.get("text", ""))))
    score = 3
    if 40 <= words <= 220:
        score += 1
    if cells:
        score += 1
    if candidate.get("suspect_ai"):
        score -= 2
    if candidate.get("dictated"):
        score -= 1
    return max(1, min(5, score))


def candidate_id(candidate: dict[str, Any], index: int) -> Any:
    return candidate.get("id", index)


def source_position(candidate: dict[str, Any]) -> str:
    source = candidate.get("source", {})
    return str(source.get("line", source.get("offset", "")))


def coverage_from(candidates: list[dict[str, Any]]) -> dict[str, int]:
    coverage = {cell: 0 for cell in CELLS}
    for candidate in candidates:
        for cell in candidate.get("cells", []):
            coverage[cell] = coverage.get(cell, 0) + 1
    return coverage


def rank_enriched(candidates: list[dict[str, Any]]) -> list[int]:
    seen_empty = set()
    rank_rows = []
    for idx, candidate in enumerate(candidates):
        cells = candidate.get("cells", [])
        fills_empty = any(cell not in seen_empty for cell in cells)
        seen_empty.update(cells)
        rank_rows.append((idx, fills_empty))
    ranked = sorted(
        rank_rows,
        key=lambda row: (
            not row[1],
            -int(candidates[row[0]].get("quality") or 0),
            -recency_value(candidates[row[0]]),
            bool(candidates[row[0]].get("suspect_ai")),
            bool(candidates[row[0]].get("dictated")),
            str(candidates[row[0]].get("source", {}).get("path", "")),
            source_position(candidates[row[0]]),
            row[0],
        ),
    )
    return [candidate_id(candidates[idx], idx) for idx, _ in ranked]


def heuristic(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    enriched = []
    seen_empty = set()
    for idx, candidate in enumerate(candidates):
        cells = cells_for(candidate.get("text", ""))
        quality = quality_for(candidate, cells)
        fills_empty = any(cell not in seen_empty for cell in cells)
        seen_empty.update(cells)
        enriched.append({
            "index": idx,
            "id": candidate.get("id", idx),
            "cells": cells,
            "quality": quality,
            "why": "lexical heuristic matched " + (", ".join(cells) if cells else "no named cell"),
            "fills_empty_coverage_cell": fills_empty,
            "source": candidate.get("source", {}),
            "suspect_ai": candidate.get("suspect_ai"),
            "dictated": candidate.get("dictated"),
        })
    return {
        "coverage_matrix": coverage_from(enriched),
        "candidates": enriched,
        "ranking": rank_enriched(enriched),
    }


def write_agent_tasks(candidates: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    prompt = (
        "Classify each candidate into WP10b situation/register cells. "
        "Return JSONL rows with candidate_index, cells, quality 1-5, and one-line why. "
        "Cells include numbers_data, question_addressed, anecdote_markers, "
        "disagreement, openings_closings, plus any clearly justified additional cell."
    )
    for start in range(0, len(candidates), 10):
        chunk = candidates[start:start + 10]
        path = out_dir / f"harvest-classify-{start // 10 + 1:03d}.json"
        payload = {
            "contract": "tier-1-pack-detector",
            "prompt": prompt,
            "candidates": [
                {"candidate_index": start + i, "text": c.get("text", ""), "source": c.get("source", {})}
                for i, c in enumerate(chunk)
            ],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        chunks.append(str(path))
    return {"task_files": chunks, "chunk_size": 10}


def result_candidate_key(row: dict[str, Any]) -> Any:
    for key in ("candidate_id", "id", "candidate_index", "index"):
        if key in row:
            return row[key]
    raise ValueError("result row missing candidate id")


def merge_results(candidates_path: Path, results_path: Path) -> dict[str, Any]:
    candidates = load_candidates(candidates_path)
    rows_by_id: dict[Any, dict[str, Any]] = {}
    for line in results_path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            rows_by_id[result_candidate_key(row)] = row

    merged = []
    for idx, candidate in enumerate(candidates):
        cid = candidate_id(candidate, idx)
        row = rows_by_id.get(cid)
        if row is None and idx in rows_by_id:
            row = rows_by_id[idx]
        cells = list(row.get("cells", [])) if row else []
        quality = int(row.get("quality")) if row and row.get("quality") is not None else quality_for(candidate, cells)
        why = str(row.get("why", "no classifier result")) if row else "no classifier result"
        merged.append({
            **candidate,
            "id": cid,
            "cells": cells,
            "quality": max(1, min(5, quality)),
            "why": why,
        })

    return {
        "coverage_matrix": coverage_from(merged),
        "candidates": merged,
        "ranking": rank_enriched(merged),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--mode", choices=["heuristic", "agent"], default="heuristic")
    parser.add_argument("--out-dir", default="harvest-agent-tasks")
    parser.add_argument("--merge")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.merge:
        print(json.dumps(merge_results(Path(args.candidates), Path(args.merge)), indent=2, sort_keys=True))
        return 0
    candidates = load_candidates(Path(args.candidates))
    if args.mode == "heuristic":
        print(json.dumps(heuristic(candidates), indent=2, sort_keys=True))
    else:
        print(json.dumps(write_agent_tasks(candidates, Path(args.out_dir)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
