#!/usr/bin/env python3
"""Enforce the frozen, end-to-end UNSLOP core shipping contract.

This gate is intentionally separate from :mod:`core_metrics`.  The scorer
answers *what* a recorded run scored; this module answers whether that run was
performed against the exact frozen corpus and implementation, with the pinned
Luna/independent-judge controls, and whether every release threshold is met.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

try:  # Running as ``python -m evals.core_acceptance``.
    from .core_metrics import score
    from .core_runner import (
        ARMS,
        _shipping_contract,
        _validation_blockers,
        _validation_stack_sha256,
    )
except ImportError:  # Running as ``python evals/core_acceptance.py``.
    from core_metrics import score
    from core_runner import (
        ARMS,
        _shipping_contract,
        _validation_blockers,
        _validation_stack_sha256,
    )


ROOT = Path(__file__).resolve().parents[1]
THRESHOLD_SCHEMA = "unslop-core-thresholds-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GENERATION_MODEL = "gpt-5.6-luna"
JUDGE_MODEL = "gpt-5.6-sol"


class AcceptanceError(ValueError):
    """A frozen-input, control, evidence, or threshold failure."""


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AcceptanceError(f"{label} {path} must contain a JSON object")
    return value


def _sha256_file(path: Path, label: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, UnicodeError) as exc:
        raise AcceptanceError(f"cannot hash {label} {path}: {exc}") from exc


def _require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise AcceptanceError(f"{label} must be a lowercase SHA-256")
    return value


def _manifest_hash_key(manifest_path: Path, frozen_inputs: dict[str, Any]) -> str:
    """Resolve the manifest hash key without trusting a caller-supplied hash.

    The current freeze calls the public v7 corpus
    ``public_holdout_v7_sha256``.  Future freezes can use another version; the
    path-derived lookup keeps the gate reusable while still requiring one
    explicit, frozen manifest hash.
    """
    stem = manifest_path.stem
    normalized = re.sub(r"^core-", "", stem).replace("-", "_")
    candidates = (
        "manifest_sha256",
        f"public_{normalized}_sha256",
        f"{normalized}_sha256",
    )
    for key in candidates:
        if key in frozen_inputs:
            return key
    reserved = {
        "shipping_contract_sha256", "core_runner_sha256", "core_metrics_sha256",
        "core_acceptance_sha256", "protocol_sha256",
        "model_adapter_source_sha256", "validation_stack_sha256", "scanner_sha256",
    }
    remaining = [
        key
        for key in frozen_inputs
        if key.endswith("_sha256") and key not in reserved
    ]
    if len(remaining) == 1:
        return remaining[0]
    raise AcceptanceError(
        "frozen_inputs must name the supplied manifest with one explicit *_sha256 entry"
    )


def _verify_frozen_inputs(
    manifest_path: Path,
    thresholds: dict[str, Any],
) -> dict[str, str]:
    if thresholds.get("schema") != THRESHOLD_SCHEMA:
        raise AcceptanceError(f"threshold schema must be {THRESHOLD_SCHEMA}")
    frozen_inputs = thresholds.get("frozen_inputs")
    if not isinstance(frozen_inputs, dict):
        raise AcceptanceError("frozen_inputs must be an object")

    manifest_key = _manifest_hash_key(manifest_path, frozen_inputs)
    required = {
        manifest_key,
        "shipping_contract_sha256",
        "core_runner_sha256",
        "core_metrics_sha256",
        "core_acceptance_sha256",
        "protocol_sha256",
        "model_adapter_source_sha256",
        "validation_stack_sha256",
        "scanner_sha256",
    }
    missing = sorted(key for key in required if key not in frozen_inputs)
    if missing:
        raise AcceptanceError("frozen_inputs missing: " + ", ".join(missing))
    protocol_path_value = frozen_inputs.get("protocol_path")
    if not isinstance(protocol_path_value, str) or not protocol_path_value:
        raise AcceptanceError("frozen_inputs.protocol_path must be a path")
    expected = {key: _require_hash(frozen_inputs[key], f"frozen_inputs.{key}") for key in required}

    actual_manifest = _sha256_file(manifest_path, "frozen manifest")
    if actual_manifest != expected[manifest_key]:
        raise AcceptanceError(
            f"frozen manifest hash mismatch: expected {expected[manifest_key]}, got {actual_manifest}"
        )
    actual_runner = _sha256_file(ROOT / "evals" / "core_runner.py", "core_runner.py")
    if actual_runner != expected["core_runner_sha256"]:
        raise AcceptanceError(
            f"core_runner.py hash mismatch: expected {expected['core_runner_sha256']}, got {actual_runner}"
        )
    actual_metrics = _sha256_file(ROOT / "evals" / "core_metrics.py", "core_metrics.py")
    if actual_metrics != expected["core_metrics_sha256"]:
        raise AcceptanceError(
            f"core_metrics.py hash mismatch: expected {expected['core_metrics_sha256']}, got {actual_metrics}"
        )
    actual_acceptance = _sha256_file(
        ROOT / "evals" / "core_acceptance.py", "core_acceptance.py"
    )
    if actual_acceptance != expected["core_acceptance_sha256"]:
        raise AcceptanceError(
            "core_acceptance.py hash mismatch: expected {}, got {}".format(
                expected["core_acceptance_sha256"], actual_acceptance
            )
        )
    protocol_path = Path(protocol_path_value)
    if not protocol_path.is_absolute():
        protocol_path = ROOT / protocol_path
    actual_protocol = _sha256_file(protocol_path, "frozen protocol")
    if actual_protocol != expected["protocol_sha256"]:
        raise AcceptanceError(
            "frozen protocol hash mismatch: expected {}, got {}".format(
                expected["protocol_sha256"], actual_protocol
            )
        )
    actual_adapter = _sha256_file(
        ROOT / "evals" / "model_generate.py", "model_generate.py"
    )
    if actual_adapter != expected["model_adapter_source_sha256"]:
        raise AcceptanceError(
            "model_generate.py hash mismatch: expected {}, got {}".format(
                expected["model_adapter_source_sha256"], actual_adapter
            )
        )
    actual_validation_stack = _validation_stack_sha256()
    if actual_validation_stack != expected["validation_stack_sha256"]:
        raise AcceptanceError(
            "validation stack hash mismatch: expected {}, got {}".format(
                expected["validation_stack_sha256"], actual_validation_stack
            )
        )
    actual_scanner = _sha256_file(
        ROOT / "scripts" / "banned_phrase_scan.py", "banned_phrase_scan.py"
    )
    if actual_scanner != expected["scanner_sha256"]:
        raise AcceptanceError(
            "banned_phrase_scan.py hash mismatch: expected {}, got {}".format(
                expected["scanner_sha256"], actual_scanner
            )
        )
    return expected


def _verify_shipping_contract(
    predictions: dict[str, Any], expected_contract_hash: str
) -> None:
    try:
        resolved = _shipping_contract()
    except Exception as exc:  # pragma: no cover - defensive import/file failure
        raise AcceptanceError(f"cannot resolve shipping contract: {exc}") from exc
    actual_hash = resolved.get("resolved_sha256")
    if actual_hash != expected_contract_hash:
        raise AcceptanceError(
            "resolved shipping contract hash mismatch: expected {}, got {}".format(
                expected_contract_hash, actual_hash
            )
        )
    contract = predictions.get("shipping_contract")
    if not isinstance(contract, dict):
        raise AcceptanceError("predictions are missing resolved shipping contract")
    if contract.get("resolved_sha256") != actual_hash:
        raise AcceptanceError("prediction shipping contract hash is stale")
    if contract.get("resolved_contract") != resolved.get("resolved_contract"):
        raise AcceptanceError("prediction resolved shipping contract is stale")
    if contract.get("components") != resolved.get("components"):
        raise AcceptanceError("prediction shipping contract components are stale")
    if contract.get("behavior_sources") != resolved.get("behavior_sources"):
        raise AcceptanceError("prediction shipping behavior sources are stale")


def _verify_controls(predictions: dict[str, Any], thresholds: dict[str, Any]) -> None:
    controls = thresholds.get("required_controls")
    if not isinstance(controls, dict):
        raise AcceptanceError("required_controls must be an object")
    expected_generation = controls.get("generation_model_both_arms")
    expected_judge = controls.get("independent_blinded_judge")
    if expected_generation != GENERATION_MODEL:
        raise AcceptanceError("threshold generation model is not gpt-5.6-luna")
    if expected_judge != JUDGE_MODEL:
        raise AcceptanceError("threshold judge model is not gpt-5.6-sol")
    if controls.get("isolated_model_workspaces") is not True:
        raise AcceptanceError("thresholds must require isolated model workspaces")
    if controls.get("paired_comparison") != "raw_luna_vs_luna_plus_unslop":
        raise AcceptanceError("thresholds must require the paired Luna comparison")

    provenance = predictions.get("provenance")
    if not isinstance(provenance, dict):
        raise AcceptanceError("prediction provenance is required")
    if provenance.get("model") != GENERATION_MODEL:
        raise AcceptanceError("generation model must be gpt-5.6-luna")
    if provenance.get("judge_model") != JUDGE_MODEL:
        raise AcceptanceError("independent judge must be gpt-5.6-sol")
    if provenance.get("isolated_workspace") is not True:
        raise AcceptanceError("model calls were not isolated")
    if provenance.get("user_config_loaded") is not False:
        raise AcceptanceError("user configuration was loaded during model calls")
    if provenance.get("project_rules_loaded") is not False:
        raise AcceptanceError("project rules were loaded during model calls")
    if provenance.get("comparison_design") != "paired_same_luna_raw_vs_luna_plus_unslop":
        raise AcceptanceError("prediction comparison is not raw Luna vs Luna+UNSLOP")
    if provenance.get("arm_labels") != {
        "with_skill": "luna_plus_unslop",
        "without_skill": "raw_luna",
    }:
        raise AcceptanceError("prediction arm labels do not bind the paired design")

    runs = predictions.get("runs")
    if not isinstance(runs, list) or not runs:
        raise AcceptanceError("prediction runs are required")
    seen_arms: set[str] = set()
    for run in runs:
        if not isinstance(run, dict):
            raise AcceptanceError("prediction runs must be objects")
        arm = run.get("arm")
        run_provenance = run.get("provenance")
        if arm not in ARMS:
            raise AcceptanceError(f"unknown prediction arm {arm!r}")
        if not isinstance(run_provenance, dict):
            raise AcceptanceError(f"{arm}: run provenance is required")
        if run_provenance.get("model") != GENERATION_MODEL:
            raise AcceptanceError(f"{arm}: generation model must be gpt-5.6-luna")
        if run_provenance.get("judge_model") != JUDGE_MODEL:
            raise AcceptanceError(f"{arm}: independent judge must be gpt-5.6-sol")
        seen_arms.add(arm)
    if seen_arms != set(ARMS):
        raise AcceptanceError("predictions must contain both with_skill and without_skill arms")

    if controls.get("shipping_validation_clean") is True:
        evidence_rows = predictions.get("evidence")
        if not isinstance(evidence_rows, list):
            raise AcceptanceError("shipping validation evidence is required")
        for evidence in evidence_rows:
            if not isinstance(evidence, dict):
                raise AcceptanceError("malformed canonical evidence row")
            validation = evidence.get("validation")
            if not isinstance(validation, dict):
                raise AcceptanceError("shipping validation evidence is missing")
            with_skill = validation.get("with_skill")
            if not isinstance(with_skill, dict) or _validation_blockers(with_skill):
                raise AcceptanceError("with_skill shipping validation is not clean")


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AcceptanceError(f"{label} must be numeric")
    return float(value)


def _verify_thresholds(result: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    with_skill = result.get("by_arm", {}).get("with_skill")
    if not isinstance(with_skill, dict):
        raise AcceptanceError("scored result has no with_skill metrics")
    absolute = thresholds.get("with_skill")
    if not isinstance(absolute, dict):
        raise AcceptanceError("with_skill thresholds must be an object")
    fallback_rate = _verify_safe_fallback_rate(result, absolute)
    minimums = {
        "detection_precision": "minimum_detection_precision",
        "detection_recall": "minimum_detection_recall",
        "repair_success": "minimum_repair_success",
        "preservation": "minimum_preservation",
        "net_improvement": "minimum_net_improvement",
        "clean_noop_rate": "minimum_clean_noop_rate",
    }
    for metric, threshold_key in minimums.items():
        threshold = _number(absolute.get(threshold_key), f"with_skill.{threshold_key}")
        actual = _number(with_skill.get(metric), f"with_skill.{metric}")
        if actual < threshold:
            raise AcceptanceError(
                f"with_skill {metric} {actual:.6f} is below {threshold:.6f}"
            )
    raw_detection = result.get("raw_source_audit", {}).get("overall")
    if not isinstance(raw_detection, dict):
        raise AcceptanceError("raw source-audit detection metrics are required")
    for metric, threshold_key in {
        "detection_precision": "minimum_raw_detection_precision",
        "detection_recall": "minimum_raw_detection_recall",
    }.items():
        threshold = _number(
            absolute.get(threshold_key), f"with_skill.{threshold_key}"
        )
        actual = _number(
            raw_detection.get(metric), f"raw_source_audit.overall.{metric}"
        )
        if actual < threshold:
            raise AcceptanceError(
                f"raw source-audit {metric} {actual:.6f} is below {threshold:.6f}"
            )
    maximum_damage = _number(
        absolute.get("maximum_damage_rate"), "with_skill.maximum_damage_rate"
    )
    damage = _number(with_skill.get("damage_rate"), "with_skill.damage_rate")
    if damage > maximum_damage:
        raise AcceptanceError(
            f"with_skill damage_rate {damage:.6f} exceeds {maximum_damage:.6f}"
        )
    comparison = thresholds.get("comparison")
    if not isinstance(comparison, dict):
        raise AcceptanceError("comparison thresholds must be an object")
    paired = result.get("paired_comparison")
    if not isinstance(paired, dict):
        raise AcceptanceError("paired comparison is required")
    win_rate = _number(paired.get("with_skill_win_rate"), "paired with_skill_win_rate")
    minimum_win_rate = _number(
        comparison.get("minimum_paired_win_rate"), "comparison.minimum_paired_win_rate"
    )
    if win_rate < minimum_win_rate:
        raise AcceptanceError(
            f"with_skill paired win rate {win_rate:.6f} is below {minimum_win_rate:.6f}"
        )
    without_wins = _number(
        paired.get("without_skill_wins"), "paired without_skill_wins"
    )
    maximum_without_wins = _number(
        comparison.get("maximum_without_skill_wins"),
        "comparison.maximum_without_skill_wins",
    )
    if without_wins > maximum_without_wins:
        raise AcceptanceError(
            f"without_skill wins {without_wins:.0f} exceeds {maximum_without_wins:.0f}"
        )

    quality_lifts = comparison.get("quality_lifts")
    if not isinstance(quality_lifts, list) or not quality_lifts:
        raise AcceptanceError("comparison.quality_lifts must be a non-empty list")
    lift = result.get("with_skill_minus_without_skill")
    without_skill = result.get("by_arm", {}).get("without_skill")
    if not isinstance(lift, dict) or not isinstance(without_skill, dict):
        raise AcceptanceError("both arm metrics and quality lifts are required")
    positive_lifts = 0
    for metric in quality_lifts:
        if metric == "damage_rate_inverse":
            with_damage = _number(with_skill.get("damage_rate"), "with_skill.damage_rate")
            without_damage = _number(
                without_skill.get("damage_rate"), "without_skill.damage_rate"
            )
            positive_lifts += with_damage < without_damage
            continue
        if not isinstance(metric, str) or metric not in lift:
            raise AcceptanceError(f"unknown quality lift {metric!r}")
        value = lift.get(metric)
        if value is not None and _number(value, f"quality lift {metric}") > 0:
            positive_lifts += 1
    minimum_positive = _number(
        comparison.get("minimum_positive_quality_lifts"),
        "comparison.minimum_positive_quality_lifts",
    )
    if positive_lifts < minimum_positive:
        raise AcceptanceError(
            f"positive quality lifts {positive_lifts} is below {minimum_positive:.0f}"
        )
    return {
        "with_skill": with_skill,
        "paired": paired,
        "positive_quality_lifts": positive_lifts,
        "safe_fallback_rate": fallback_rate,
    }


def _verify_safe_fallback_rate(
    result: dict[str, Any], absolute: dict[str, Any]
) -> float:
    maximum_fallback = _number(
        absolute.get("maximum_safe_fallback_rate"),
        "with_skill.maximum_safe_fallback_rate",
    )
    operational = result.get("operational")
    if not isinstance(operational, dict):
        raise AcceptanceError("operational metrics are required")
    fallback_rate = _number(
        operational.get("with_skill_safe_fallback_rate"),
        "operational.with_skill_safe_fallback_rate",
    )
    if fallback_rate > maximum_fallback:
        raise AcceptanceError(
            f"with_skill safe fallback rate {fallback_rate:.6f} "
            f"exceeds {maximum_fallback:.6f}"
        )
    return fallback_rate


def _verify_efficiency(
    result: dict[str, Any], thresholds: dict[str, Any]
) -> dict[str, float]:
    """Enforce preregistered maxima for every case and report corpus averages."""
    budget = thresholds.get("efficiency")
    operational = result.get("operational")
    if not isinstance(budget, dict) or not isinstance(operational, dict):
        raise AcceptanceError("efficiency thresholds and operational metrics are required")
    case_count = _number(
        operational.get("with_skill_runs"), "operational.with_skill_runs"
    )
    if case_count <= 0:
        raise AcceptanceError("operational.with_skill_runs must be positive")
    by_case = operational.get("by_case")
    if not isinstance(by_case, dict) or len(by_case) != int(case_count):
        raise AcceptanceError(
            "operational.by_case must contain every with-skill benchmark case"
        )
    mappings = {
        "model_calls": "maximum_model_calls_per_case",
        "uncached_input_tokens": "maximum_uncached_input_tokens_per_case",
        "output_tokens": "maximum_output_tokens_per_case",
        "elapsed_seconds": "maximum_elapsed_seconds_per_case",
    }
    per_case: dict[str, float] = {}
    for metric, threshold_key in mappings.items():
        total = _number(operational.get(metric), f"operational.{metric}")
        maximum = _number(budget.get(threshold_key), f"efficiency.{threshold_key}")
        if maximum < 0:
            raise AcceptanceError(f"efficiency.{threshold_key} must be non-negative")
        average = total / case_count
        case_values = {
            case_id: _number(case_metrics.get(metric), f"operational.by_case.{case_id}.{metric}")
            for case_id, case_metrics in by_case.items()
            if isinstance(case_metrics, dict)
        }
        if len(case_values) != len(by_case):
            raise AcceptanceError("operational.by_case rows must be objects")
        worst_case_id, actual_maximum = max(case_values.items(), key=lambda item: item[1])
        per_case[metric] = average
        per_case[f"maximum_{metric}"] = actual_maximum
        if actual_maximum > maximum:
            raise AcceptanceError(
                f"efficiency {metric} for {worst_case_id} {actual_maximum:.6f} "
                f"exceeds {maximum:.6f}"
            )
    return per_case


def evaluate(
    manifest_path: Path,
    predictions_path: Path,
    results_path: Path,
    thresholds_path: Path,
    *,
    split: str,
    allow_offline: bool = False,
) -> dict[str, Any]:
    """Validate and score one frozen acceptance artifact."""
    thresholds = _load(thresholds_path, "thresholds")
    frozen = _verify_frozen_inputs(manifest_path, thresholds)
    manifest = _load(manifest_path, "manifest")
    predictions = _load(predictions_path, "predictions")
    results = _load(results_path, "results")
    _verify_shipping_contract(predictions, frozen["shipping_contract_sha256"])
    _verify_controls(predictions, thresholds)
    try:
        recomputed = score(
            manifest,
            predictions,
            split=split,
            verify_evidence=True,
            allow_offline=allow_offline,
        )
    except Exception as exc:
        raise AcceptanceError(f"core evidence verification failed: {exc}") from exc
    if results != recomputed:
        raise AcceptanceError("results file does not match a fresh core_metrics score")
    metrics = _verify_thresholds(recomputed, thresholds)
    metrics["efficiency_per_case"] = _verify_efficiency(recomputed, thresholds)
    if thresholds.get("required_controls", {}).get("shipping_validation_clean") is True:
        metrics["shipping_validation_clean"] = True
    metrics["frozen_inputs"] = frozen
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("results", type=Path)
    parser.add_argument("--thresholds", type=Path, required=True)
    parser.add_argument("--split", choices=("tune", "holdout", "holdback"), required=True)
    parser.add_argument(
        "--allow-offline",
        action="store_true",
        help="accept offline fixtures (tests only; never use for release evidence)",
    )
    args = parser.parse_args(argv)
    try:
        summary = evaluate(
            args.manifest,
            args.predictions,
            args.results,
            args.thresholds,
            split=args.split,
            allow_offline=args.allow_offline,
        )
    except AcceptanceError as exc:
        print(f"core acceptance: {exc}", file=sys.stderr)
        return 2
    with_skill = summary["with_skill"]
    paired = summary["paired"]
    print(
        "PASS core acceptance: precision={:.6f} recall={:.6f} repair={:.6f} "
        "preservation={:.6f} damage={:.6f} net={:.6f} noop={:.6f}".format(
            with_skill["detection_precision"],
            with_skill["detection_recall"],
            with_skill["repair_success"],
            with_skill["preservation"],
            with_skill["damage_rate"],
            with_skill["net_improvement"],
            with_skill["clean_noop_rate"],
        )
    )
    print(
        "paired: win_rate={:.6f} without_skill_wins={} positive_quality_lifts={}".format(
            paired["with_skill_win_rate"],
            paired["without_skill_wins"],
            summary["positive_quality_lifts"],
        )
    )
    efficiency = summary["efficiency_per_case"]
    print(
        "efficiency/case: calls={:.3f} uncached_input_tokens={:.3f} "
        "output_tokens={:.3f} elapsed_seconds={:.3f} max_elapsed_seconds={:.3f}".format(
            efficiency["model_calls"],
            efficiency["uncached_input_tokens"],
            efficiency["output_tokens"],
            efficiency["elapsed_seconds"],
            efficiency["maximum_elapsed_seconds"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
