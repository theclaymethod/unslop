#!/usr/bin/env python3
"""Classify harvested candidates into situation/register coverage cells."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


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


def heuristic(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    coverage = {cell: 0 for cell in CELLS}
    enriched = []
    seen_empty = set()
    for idx, candidate in enumerate(candidates):
        cells = cells_for(candidate.get("text", ""))
        for cell in cells:
            coverage[cell] += 1
        quality = quality_for(candidate, cells)
        fills_empty = any(cell not in seen_empty for cell in cells)
        seen_empty.update(cells)
        enriched.append({
            "index": idx,
            "cells": cells,
            "quality": quality,
            "why": "lexical heuristic matched " + (", ".join(cells) if cells else "no named cell"),
            "fills_empty_coverage_cell": fills_empty,
            "source": candidate.get("source", {}),
        })
    ranked = sorted(
        enriched,
        key=lambda row: (
            not row["fills_empty_coverage_cell"],
            -row["quality"],
            bool(candidates[row["index"]].get("suspect_ai")),
            bool(candidates[row["index"]].get("dictated")),
            row["index"],
        ),
    )
    return {
        "coverage_matrix": coverage,
        "candidates": enriched,
        "ranking": [row["index"] for row in ranked],
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


def merge_results(path: Path) -> dict[str, Any]:
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return {"merged": rows, "count": len(rows)}


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
        print(json.dumps(merge_results(Path(args.merge)), indent=2, sort_keys=True))
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
