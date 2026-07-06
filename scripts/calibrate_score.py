#!/usr/bin/env python3
"""
Aggregate a teach-calibration preferences JSONL into per-dimension confidence,
surface conflicts against a measured stylometric profile, and pick the next
dimension to play.

Preferences JSONL rows (one per game round):
    {"pair_id": "...", "dimension": "contractions", "choice": "a"|"b"|"neither",
     "ts": "...", "a_label": "contracted", "b_label": "expanded"}

`a_label`/`b_label` are optional. When present (calibrate_pairs.py's
transform_applied names the B pole; A sits at the other pole in the same
dimension's POLES pair) they let this script report a semantic preferred
DIRECTION ("expanded", "short", "formal", ...) instead of the bare literal
"a"/"b" tally, which is what --profile conflict detection needs. Rows without
labels still count toward n and the confidence interval; they just can't
resolve to a named pole (direction is reported as "a" or "b").

Usage:
    python3 calibrate_score.py --preferences prefs.jsonl
    python3 calibrate_score.py --preferences prefs.jsonl --profile profile.json
    python3 calibrate_score.py --preferences prefs.jsonl --next
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from calibrate_pairs import DIMENSIONS, POLES  # noqa: E402

MIN_K = 5
Z = 1.96

# Dimension -> (profile_key, pole_meaning) used only for --profile conflict
# detection. `low_pole`/`high_pole` say which named pole a LOW vs HIGH measured
# value corresponds to, so a confident stated preference for the opposite pole
# of what the measured value implies is flagged.
_PROFILE_LINKS: dict[str, dict] = {
    "contractions": {
        "profile_key": "contraction_rate",
        "low_pole": "expanded",
        "high_pole": "contracted",
        "low_threshold": 0.05,
        "high_threshold": 0.20,
    },
    "sentence_length": {
        "profile_key": "avg_sentence_length",
        "low_pole": "short",
        "high_pole": "long",
        "low_threshold": 12.0,
        "high_threshold": 20.0,
    },
    "staccato": {
        "profile_key": "avg_sentence_length",
        "low_pole": "staccato",
        "high_pole": "flowing",
        "low_threshold": 12.0,
        "high_threshold": 20.0,
    },
    "em_dash": {
        "profile_key": "em_dash_rate",
        "low_pole": "plain",
        "high_pole": "dashed",
        "low_threshold": 0.02,
        "high_threshold": 0.15,
    },
    "connectives": {
        "profile_key": "formal_connective_rate",
        "low_pole": "plain",
        "high_pole": "formal",
        "low_threshold": 0.10,
        "high_threshold": 0.40,
    },
}

CONFIDENCE_STOP = 0.7
K_STOP = 9


def wilson_lower_bound(successes: int, n: int, z: float = Z) -> float:
    if n == 0:
        return 0.0
    phat = successes / n
    denom = 1 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)
    return round(max(0.0, (center - margin) / denom), 3)


def load_preferences(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def aggregate(rows: list[dict]) -> dict[str, dict]:
    result = {dim: {"n": 0, "tally": {}, "neither": 0} for dim in DIMENSIONS}

    for row in rows:
        dim = row.get("dimension")
        if dim not in result:
            continue
        result[dim]["n"] += 1
        choice = row.get("choice")
        if choice == "neither":
            result[dim]["neither"] += 1
            continue
        if choice not in ("a", "b"):
            continue
        label = row.get(f"{choice}_label") or choice
        result[dim]["tally"][label] = result[dim]["tally"].get(label, 0) + 1

    dimensions = {}
    for dim, data in result.items():
        n = data["n"]
        decisive = sum(data["tally"].values())
        if n < MIN_K or decisive == 0:
            dimensions[dim] = {
                "n": n,
                "status": "insufficient",
                "preferred": None,
                "confidence": 0.0,
            }
            continue
        preferred_label, preferred_count = max(
            data["tally"].items(), key=lambda kv: (kv[1], kv[0])
        )
        confidence = wilson_lower_bound(preferred_count, decisive)
        dimensions[dim] = {
            "n": n,
            "status": "confident",
            "preferred": preferred_label,
            "confidence": confidence,
        }
    return dimensions


def detect_conflicts(dimensions: dict[str, dict], profile: dict) -> list[dict]:
    conflicts = []
    for dim, data in dimensions.items():
        if data["status"] != "confident" or data["confidence"] < CONFIDENCE_STOP:
            continue
        link = _PROFILE_LINKS.get(dim)
        if not link or link["profile_key"] not in profile:
            continue
        measured = profile[link["profile_key"]]
        preferred = data["preferred"]
        conflict_pole = None
        if preferred == link["low_pole"] and measured >= link["high_threshold"]:
            conflict_pole = link["high_pole"]
        elif preferred == link["high_pole"] and measured <= link["low_threshold"]:
            conflict_pole = link["low_pole"]
        if conflict_pole is None:
            continue
        conflicts.append({
            "dimension": dim,
            "preferred": preferred,
            "preferred_confidence": data["confidence"],
            "preferred_provenance": "stated-preference",
            "measured_key": link["profile_key"],
            "measured_value": measured,
            "measured_provenance": "measured-from-samples",
            "message": (
                f"Stated preference for '{preferred}' ({dim}) contradicts "
                f"{link['profile_key']}={measured} measured from samples, "
                f"which points toward '{conflict_pole}'."
            ),
        })
    return conflicts


def next_dimension(dimensions: dict[str, dict]) -> dict:
    def sort_key(dim: str) -> tuple:
        data = dimensions[dim]
        confidence = data["confidence"] if data["status"] == "confident" else 0.0
        return (data["n"], confidence, DIMENSIONS.index(dim))

    ordered = sorted(DIMENSIONS, key=sort_key)
    chosen = ordered[0]
    data = dimensions[chosen]
    if data["n"] == min(dimensions[d]["n"] for d in DIMENSIONS):
        reason = "fewest_observations"
    else:
        reason = "lowest_confidence"
    return {
        "next_dimension": chosen,
        "reason": reason,
        "n": data["n"],
        "confidence": data["confidence"],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preferences", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--next", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    try:
        rows = load_preferences(Path(args.preferences))
    except OSError as e:
        print(json.dumps({"error": f"could not read preferences file: {e}"}))
        return 2

    dimensions = aggregate(rows)

    if args.next:
        print(json.dumps(next_dimension(dimensions), indent=2, sort_keys=True))
        return 0

    output = {"dimensions": dimensions}

    if args.profile:
        try:
            profile = json.loads(Path(args.profile).read_text())
        except OSError as e:
            print(json.dumps({"error": f"could not read profile file: {e}"}))
            return 2
        output["conflicts"] = detect_conflicts(dimensions, profile)

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
