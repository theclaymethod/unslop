#!/usr/bin/env python3
"""Validate the frozen blind-Luna v2 core corpus without opening holdback."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from _check_support import ROOT  # noqa: E402

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from core_metrics import InputError, validate_manifest  # noqa: E402
from core_runner import _needs_with_skill_generation, _source_diagnostics  # noqa: E402
from scripts.banned_phrase_scan import scan_for_violations  # noqa: E402


MANIFEST = ROOT / "evals" / "core-benchmark-v2.json"
POOL = ROOT / "evals" / "core-source-pool-v2.json"
HOLDBACK = ROOT / "evals" / "core-holdback-metadata-v2.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_SPLITS = Counter({"holdout": 14, "tune": 7})
HOLDOUT_COUNTS = {"issues": 5, "protected_spans": 24, "constraints": 78}
TUNE_COUNTS = {"issues": 0, "protected_spans": 8, "constraints": 39}
STRATUM_RULES = {
    "factual": {"count": 16, "holdback": slice(0, 2), "tune": slice(2, 4), "holdout": slice(4, 8)},
    "persuasive": {"count": 8, "holdback": slice(0, 2), "tune": slice(2, 4), "holdout": slice(4, 8)},
    "conventional_promotional": {
        "count": 12,
        "holdback": slice(0, 3),
        "tune": slice(3, 6),
        "holdout": slice(6, 12),
    },
}


def fail(message: str) -> int:
    print(f"core benchmark v2: {message}", file=sys.stderr)
    return 1


def load(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_sha256(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def line_starts(source: str) -> list[int]:
    starts = [0]
    starts.extend(match.end() for match in re.finditer("\n", source))
    return starts


def public_counts(cases: dict[str, dict], split: str) -> dict[str, int]:
    selected = [case for case in cases.values() if case["split"] == split]
    return {
        "issues": sum(len(case["issues"]) for case in selected),
        "protected_spans": sum(len(case["protected_spans"]) for case in selected),
        "constraints": sum(len(case["constraints"]) for case in selected),
    }


def main() -> int:
    try:
        payload = load(MANIFEST, "public manifest")
        pool = load(POOL, "source-pool ledger")
        holdback = load(HOLDBACK, "holdback metadata")
        cases = validate_manifest(payload)
    except (ValueError, InputError) as exc:
        return fail(str(exc))

    if payload.get("required_arms") != ["with_skill", "without_skill"]:
        return fail("required_arms must pin with_skill and without_skill")
    splits = Counter(case["split"] for case in cases.values())
    if splits != EXPECTED_SPLITS:
        return fail(f"unexpected split counts: {dict(splits)}")
    if any(case["split"] == "holdback" for case in cases.values()):
        return fail("sealed holdback sources must not be committed")
    if public_counts(cases, "tune") != TUNE_COUNTS:
        return fail("tune annotation counts drifted")
    if public_counts(cases, "holdout") != HOLDOUT_COUNTS:
        return fail("holdout annotation counts drifted")

    if pool.get("schema") != "unslop-core-source-pool-v2":
        return fail("invalid source-pool schema")
    hashes_by_stratum = pool.get("sorted_source_sha256_by_stratum")
    if not isinstance(hashes_by_stratum, dict):
        return fail("source-pool hashes are missing")
    all_hashes: list[str] = []
    expected_public: dict[tuple[str, str], set[str]] = {}
    expected_holdback: dict[str, list[str]] = {}
    for stratum, rule in STRATUM_RULES.items():
        rows = hashes_by_stratum.get(stratum)
        if (
            not isinstance(rows, list)
            or len(rows) != rule["count"]
            or rows != sorted(rows)
            or any(not isinstance(row, str) or not SHA256_RE.fullmatch(row) for row in rows)
        ):
            return fail(f"{stratum} source commitments are malformed")
        all_hashes.extend(rows)
        expected_holdback[stratum] = rows[rule["holdback"]]
        expected_public[(stratum, "tune")] = set(rows[rule["tune"]])
        expected_public[(stratum, "holdout")] = set(rows[rule["holdout"]])
    if len(all_hashes) != 36 or len(set(all_hashes)) != 36:
        return fail("source pool must contain 36 unique commitments")

    observed_public: dict[tuple[str, str], set[str]] = {
        key: set() for key in expected_public
    }
    scanner_gold = 0
    tune_short_circuit_eligible = 0
    clean_holdout = 0
    dirty_holdout = 0
    for case_id, case in cases.items():
        provenance = case.get("provenance")
        if not isinstance(provenance, dict):
            return fail(f"{case_id}: provenance is required")
        required_provenance = {
            "kind", "stratum", "model", "generator_task", "blinded_from",
            "source_prompt", "source_sha256", "annotation_task",
        }
        if not required_provenance <= set(provenance):
            return fail(f"{case_id}: provenance is incomplete")
        if provenance.get("model") != "gpt-5.6-luna":
            return fail(f"{case_id}: source model is not Luna")
        actual_source_hash = source_sha256(case["source"])
        if provenance.get("source_sha256") != actual_source_hash:
            return fail(f"{case_id}: source hash is stale")
        key = (provenance.get("stratum"), case["split"])
        if key not in observed_public or actual_source_hash not in expected_public[key]:
            return fail(f"{case_id}: source is outside its preregistered split")
        observed_public[key].add(actual_source_hash)

        word_count = len(re.findall(r"\b\w+(?:[-'’]\w+)*\b", case["source"], re.UNICODE))
        if not 170 <= word_count <= 270:
            return fail(f"{case_id}: word count {word_count} is outside 170..270")
        issue_spans = {(row["start"], row["end"], row.get("category")) for row in case["issues"]}
        protected_intervals = [(row["start"], row["end"]) for row in case["protected_spans"]]
        protected_exact = set(protected_intervals)
        if not any(row.get("kind") == "good_prose" for row in case["protected_spans"]):
            return fail(f"{case_id}: broad good-prose protection is required")
        for issue in case["issues"]:
            if not issue.get("category") or not issue.get("rationale"):
                return fail(f"{case_id}/{issue['id']}: category and rationale are required")
            if any(issue["start"] < end and start < issue["end"] for start, end in protected_intervals):
                return fail(f"{case_id}/{issue['id']}: issue overlaps protected prose")
        for protected in case["protected_spans"]:
            if not protected.get("policy"):
                return fail(f"{case_id}/{protected['id']}: protection policy is required")

        starts = line_starts(case["source"])
        for violation in scan_for_violations(case["source"]):
            start = starts[violation["line_number"] - 1] + violation["column"] - 1
            end = start + len(violation["phrase"])
            key_span = (start, end, violation["category"])
            if key_span in issue_spans:
                scanner_gold += 1
            elif (start, end) not in protected_exact:
                return fail(
                    f"{case_id}: scanner finding {violation['phrase']!r} is neither gold nor protected"
                )

        diagnostics = _source_diagnostics(case)
        if (
            case["split"] == "tune"
            and not case["issues"]
            and not _needs_with_skill_generation(
                diagnostics["banned_phrase"], [], diagnostics
            )
        ):
            tune_short_circuit_eligible += 1
        if case["split"] == "holdout":
            if case["issues"]:
                dirty_holdout += 1
            else:
                clean_holdout += 1

    if observed_public != expected_public:
        return fail("public cases do not exactly match preregistered source ranks")
    if (dirty_holdout, clean_holdout) != (5, 9):
        return fail("holdout dirty/clean composition drifted")
    if tune_short_circuit_eligible != 5:
        return fail("tune clean-short-circuit coverage drifted")

    if holdback.get("schema") != "unslop-core-holdback-metadata-v2":
        return fail("invalid holdback metadata schema")
    if holdback.get("count") != 7:
        return fail("holdback case count must be 7")
    if holdback.get("selected_source_sha256_by_stratum") != expected_holdback:
        return fail("holdback component commitments differ from preregistered ranks")
    sealed_rel = holdback.get("sealed_path")
    sealed_hash = holdback.get("manifest_sha256")
    if not isinstance(sealed_rel, str) or not sealed_rel.startswith("evals/runs/"):
        return fail("sealed holdback path must live under ignored evals/runs/")
    if not isinstance(sealed_hash, str) or not SHA256_RE.fullmatch(sealed_hash):
        return fail("sealed holdback hash is invalid")
    sealed_path = ROOT / sealed_rel
    if sealed_path.exists() and sha256_bytes(sealed_path) != sealed_hash:
        return fail("local sealed holdback hash mismatch")

    raw_artifact = pool.get("raw_pool_artifact")
    if not isinstance(raw_artifact, dict):
        return fail("raw source-pool commitment is missing")
    raw_rel = raw_artifact.get("path")
    raw_hash = raw_artifact.get("sha256")
    if (
        not isinstance(raw_rel, str)
        or not raw_rel.startswith("evals/runs/")
        or raw_artifact.get("committed") is not False
        or raw_artifact.get("contains_sealed_sources") is not True
        or not isinstance(raw_hash, str)
        or not SHA256_RE.fullmatch(raw_hash)
    ):
        return fail("raw source-pool commitment is malformed")
    raw_path = ROOT / raw_rel
    if raw_path.exists() and sha256_bytes(raw_path) != raw_hash:
        return fail("local raw source-pool hash mismatch")

    public_hashes = {source_sha256(case["source"]) for case in cases.values()}
    sealed_hashes = {row for rows in expected_holdback.values() for row in rows}
    if public_hashes & sealed_hashes:
        return fail("public and sealed source commitments overlap")
    excluded = set(all_hashes) - public_hashes - sealed_hashes
    if len(excluded) != 8:
        return fail("source-pool partition must leave exactly 8 excluded cases")

    print("core benchmark v2: public=21 tune=7 holdout=14 sealed=7 excluded=8")
    print("holdout: dirty=5 clean=9 issues=5 protected=24 constraints=78")
    print(f"scanner-visible gold issues={scanner_gold}; semantic/style gold issues=5")
    print("tune clean-short-circuit eligible=5")
    print("source selection: deterministic=true public_sealed_overlap=0 raw_pool=hash-bound")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
