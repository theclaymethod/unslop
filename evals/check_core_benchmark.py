#!/usr/bin/env python3
"""Validate the committed span-annotated core product corpus."""

from __future__ import annotations

import json
import hashlib
import re
import sys
from collections import Counter

from _check_support import ROOT  # noqa: E402

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from core_metrics import InputError, validate_manifest  # noqa: E402
from scripts.banned_phrase_scan import scan_for_violations  # noqa: E402


MANIFEST = ROOT / "evals" / "core-benchmark.json"
HOLDBACK_METADATA = ROOT / "evals" / "core-holdback-metadata.json"


def line_starts(source: str) -> list[int]:
    starts = [0]
    starts.extend(match.end() for match in re.finditer("\n", source))
    return starts


def fail(message: str) -> int:
    print(f"core benchmark: {message}", file=sys.stderr)
    return 1


def main() -> int:
    try:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cases = validate_manifest(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, InputError) as exc:
        return fail(str(exc))

    if payload.get("required_arms") != ["with_skill", "without_skill"]:
        return fail("required_arms must pin with_skill and without_skill")
    splits = Counter(case["split"] for case in cases.values())
    if splits != Counter({"tune": 2, "holdout": 4}):
        return fail(f"unexpected split counts: {dict(splits)}")
    if not any(not case.get("issues") for case in cases.values()):
        return fail("at least one clean no-op case is required")
    if any(case["split"] == "holdback" for case in cases.values()):
        return fail("holdback sources must not be committed in the public corpus")

    try:
        holdback = json.loads(HOLDBACK_METADATA.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return fail(f"cannot read holdback metadata: {exc}")
    if holdback.get("schema") != "unslop-core-holdback-metadata-v1":
        return fail("invalid holdback metadata schema")
    if holdback.get("counts", {}).get("cases") != 4 or "source" in json.dumps(holdback).lower():
        return fail("holdback metadata must contain counts but no source text")
    sealed_rel = holdback.get("sealed_path")
    if not isinstance(sealed_rel, str) or not sealed_rel.startswith("evals/runs/"):
        return fail("sealed holdback path must live under ignored evals/runs/")
    expected_hash = holdback.get("manifest_sha256")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        return fail("holdback metadata hash must be SHA-256")
    sealed_path = ROOT / sealed_rel
    if sealed_path.exists():
        actual_hash = hashlib.sha256(sealed_path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            return fail("local sealed holdback does not match public metadata hash")

    contextual_fp_by_split: Counter[str] = Counter()
    scanner_independent_by_split: Counter[str] = Counter()
    for case_id, case in cases.items():
        provenance = case.get("provenance")
        if not isinstance(provenance, dict):
            return fail(f"{case_id}: provenance must be an object")
        for key in ("kind", "model", "generator_task", "description"):
            if not isinstance(provenance.get(key), str) or not provenance[key]:
                return fail(f"{case_id}: provenance.{key} is required")
        if provenance["kind"] != "luna_synthetic" or provenance["model"] != "gpt-5.6-luna":
            return fail(f"{case_id}: corpus provenance must identify Luna")
        if not isinstance(case.get("genre"), str) or not isinstance(case.get("register"), str):
            return fail(f"{case_id}: genre and register are required")
        word_count = len(re.findall(r"\b\w+(?:[-'’]\w+)*\b", case["source"], re.UNICODE))
        if not 120 <= word_count <= 220:
            return fail(f"{case_id}: word count {word_count} is outside 120..220")

        issue_spans = {(row["start"], row["end"], row.get("category")) for row in case["issues"]}
        protected_intervals = [(row["start"], row["end"]) for row in case["protected_spans"]]
        protected_exact = set(protected_intervals)
        for issue in case["issues"]:
            if not issue.get("category") or not issue.get("rationale"):
                return fail(f"{case_id}/{issue['id']}: category and rationale are required")
            if any(issue["start"] < end and start < issue["end"] for start, end in protected_intervals):
                return fail(f"{case_id}/{issue['id']}: issue overlaps protected prose")
        for protected in case["protected_spans"]:
            if not protected.get("policy"):
                return fail(f"{case_id}/{protected['id']}: protection policy is required")
        good_prose = [
            protected for protected in case["protected_spans"]
            if protected.get("kind") == "good_prose"
        ]
        if not good_prose:
            return fail(f"{case_id}: at least one broad good-prose protection is required")
        for protected in good_prose:
            protected_words = len(re.findall(r"\b\w+(?:[-'’]\w+)*\b", protected["text"]))
            if not 15 <= protected_words <= 45:
                return fail(
                    f"{case_id}/{protected['id']}: good-prose span must be 15..45 words"
                )

        starts = line_starts(case["source"])
        scanner_gold_keys = set()
        for violation in scan_for_violations(case["source"]):
            start = starts[violation["line_number"] - 1] + violation["column"] - 1
            end = start + len(violation["phrase"])
            key = (start, end, violation["category"])
            if key in issue_spans:
                scanner_gold_keys.add(key)
                continue
            if (start, end) in protected_exact:
                contextual_fp_by_split[case["split"]] += 1
                continue
            if key not in issue_spans:
                return fail(
                    f"{case_id}: scanner finding {violation['phrase']!r}/"
                    f"{violation['category']} at {start}:{end} is neither a gold issue nor "
                    "an exact protected contextual use"
                )
        scanner_independent_by_split[case["split"]] += len(issue_spans - scanner_gold_keys)

    missing_fp_splits = [
        split for split in ("tune", "holdout")
        if contextual_fp_by_split[split] < 1
    ]
    if missing_fp_splits:
        return fail("missing contextual scanner false positives in: " + ", ".join(missing_fp_splits))
    missing_independent_splits = [
        split for split in ("tune", "holdout")
        if scanner_independent_by_split[split] < 1
    ]
    if missing_independent_splits:
        return fail(
            "missing scanner-independent gold issues in: "
            + ", ".join(missing_independent_splits)
        )

    print(
        "core benchmark: 6 public cases; tune=2 holdout=4 holdback=0; scanner parity OK"
    )
    print("contextual scanner false positives: tune>=1 holdout>=1")
    print("sealed holdback: 4 cases; sources_committed=false; metadata_hash=valid")
    print("scanner-independent gold issues: tune>=1 holdout>=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
