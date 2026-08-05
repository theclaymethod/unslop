#!/usr/bin/env python3
"""Score the end-to-end UNSLOP product contract without hiding failure modes.

The gold manifest owns source spans and split membership. A prediction file owns
model findings plus independently adjudicated rewrite outcomes. This scorer is
deliberately model-free: live generation and judging happen elsewhere, while
this file turns their recorded evidence into reproducible metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

try:
    from .core_runner import (
        RunnerError,
        _attribution_preservation,
        _change_coverage,
        _generation_prompt,
        _judge_prompt,
        _retry_directives,
        _retry_prompt,
        _semantic_prompt,
        _validate_generation,
        _validation_blockers,
    )
except ImportError:
    from core_runner import (
        RunnerError,
        _attribution_preservation,
        _change_coverage,
        _generation_prompt,
        _judge_prompt,
        _retry_directives,
        _retry_prompt,
        _semantic_prompt,
        _validate_generation,
        _validation_blockers,
    )


METRIC_SCHEMA = "unslop-core-results-v1"
MANIFEST_SCHEMA = "unslop-core-benchmark-v1"
PREDICTION_SCHEMA = "unslop-core-predictions-v1"
REPO_ROOT = Path(__file__).resolve().parent.parent


class InputError(ValueError):
    pass


_FORBIDDEN_EVENT_TYPES = {
    "command_execution", "function_call", "mcp_tool_call", "tool_call",
    "web_search", "computer_use",
}


def _reject_tool_events(raw_events: str, label: str) -> None:
    """Reject live evidence showing any external action by a model arm."""
    for line_number, line in enumerate(raw_events.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InputError(f"{label}: malformed invocation event line {line_number}") from exc
        stack = [event]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                event_type = value.get("type")
                if isinstance(event_type, str) and event_type in _FORBIDDEN_EVENT_TYPES:
                    raise InputError(f"{label}: forbidden invocation event {event_type}")
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise InputError(f"{path} must contain a JSON object")
    return value


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _extract_json_object(raw: str) -> dict:
    if not isinstance(raw, str):
        raise InputError("raw model evidence must be text")
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(raw[index:])
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            return value
    raise InputError("raw model evidence contains no JSON object")


def _verify_hash(record: dict, field: str, hash_field: str, label: str) -> None:
    value = record.get(field)
    if not isinstance(value, str) or record.get(hash_field) != _sha256(value):
        raise InputError(f"{label}: invalid {field}/{hash_field} evidence")


def verify_prediction_evidence(
    manifest: dict,
    predictions: dict,
    *,
    split: str | None,
    allow_offline: bool,
) -> None:
    """Bind scored booleans to raw runner, generation, and blind-judge evidence."""
    root = predictions.get("provenance")
    if not isinstance(root, dict):
        raise InputError("prediction root provenance is required")
    if root.get("runner") != "evals/core_runner.py" or root.get("provider") != "codex":
        raise InputError("predictions were not produced by the core runner")
    if root.get("model") != "gpt-5.6-luna":
        raise InputError("generation model must be pinned to gpt-5.6-luna")
    if root.get("judge_model") != "gpt-5.6-sol":
        raise InputError("judge model must be pinned to independent gpt-5.6-sol")
    if root.get("offline_responses") is True and not allow_offline:
        raise InputError("offline response fixtures are not acceptance evidence")
    if root.get("offline_responses") not in {True, False}:
        raise InputError("offline response provenance must be boolean")
    if root.get("workflow") != "semantic_diagnose_rewrite_validate_retry":
        raise InputError("prediction workflow is not the shipping acceptance workflow")
    if (
        root.get("isolated_workspace") is not True
        or root.get("user_config_loaded") is not False
        or root.get("project_rules_loaded") is not False
    ):
        raise InputError("model calls were not isolated from repository and user rules")
    if split and predictions.get("split") != split:
        raise InputError("prediction split does not match requested split")

    shipping_contract = predictions.get("shipping_contract")
    if not isinstance(shipping_contract, dict):
        raise InputError("resolved shipping contract provenance is required")
    resolved_contract = shipping_contract.get("resolved_contract")
    if (
        not isinstance(resolved_contract, str)
        or shipping_contract.get("resolved_sha256") != _sha256(resolved_contract)
    ):
        raise InputError("resolved shipping contract hash is invalid")
    expected_components = {
        "SKILL.md",
        "references/commands/rewrite.md",
        "presets/crisp-human.md",
    }
    components = shipping_contract.get("components")
    if not isinstance(components, dict) or set(components) != expected_components:
        raise InputError("shipping contract components are incomplete")
    for name, component in components.items():
        if not isinstance(component, dict) or not isinstance(component.get("text"), str):
            raise InputError(f"shipping contract component {name} is malformed")
        if component.get("text_sha256") != _sha256(component["text"]):
            raise InputError(f"shipping contract component {name} text hash is invalid")
        try:
            current_source = (REPO_ROOT / name).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise InputError(f"cannot verify shipping component {name}: {exc}") from exc
        if component.get("source_sha256") != _sha256(current_source):
            raise InputError(f"shipping contract component {name} is stale")
    if root.get("shipping_contract_sha256") != shipping_contract["resolved_sha256"]:
        raise InputError("root shipping contract provenance mismatch")

    cases = validate_manifest(manifest)
    evidence_rows = predictions.get("evidence")
    if not isinstance(evidence_rows, list):
        raise InputError("canonical case evidence is required")
    evidence_by_case: dict[str, dict] = {}
    for evidence_row in evidence_rows:
        if not isinstance(evidence_row, dict):
            raise InputError("canonical case evidence rows must be objects")
        evidence_case_id = evidence_row.get("case_id")
        if not isinstance(evidence_case_id, str) or evidence_case_id in evidence_by_case:
            raise InputError("canonical case evidence ids must be unique")
        evidence_by_case[evidence_case_id] = evidence_row
    for run in predictions.get("runs", []):
        case_id, arm = run.get("case_id"), run.get("arm")
        if case_id not in cases or arm not in {"with_skill", "without_skill"}:
            raise InputError(f"invalid evidenced run {case_id!r}/{arm!r}")
        case = cases[case_id]
        if split and case["split"] != split:
            continue
        provenance = run.get("provenance")
        evidence = evidence_by_case.get(case_id)
        if not isinstance(provenance, dict) or not isinstance(evidence, dict):
            raise InputError(f"{case_id}/{arm}: provenance and canonical evidence are required")
        if provenance.get("model") != root["model"] or provenance.get("provider") != "codex":
            raise InputError(f"{case_id}/{arm}: model provenance mismatch")
        if provenance.get("judge_model") != root["judge_model"]:
            raise InputError(f"{case_id}/{arm}: judge model provenance mismatch")
        if provenance.get("workflow") != "semantic_diagnose_rewrite_validate_retry":
            raise InputError(f"{case_id}/{arm}: workflow provenance must be explicit")
        if provenance.get("shipping_contract_sha256") != shipping_contract["resolved_sha256"]:
            raise InputError(f"{case_id}/{arm}: shipping contract provenance mismatch")

        generation_map = evidence.get("generation")
        semantic = evidence.get("semantic_diagnosis")
        judge = evidence.get("judge")
        generation = generation_map.get(arm) if isinstance(generation_map, dict) else None
        if not isinstance(generation, dict) or not isinstance(judge, dict) or not isinstance(semantic, dict):
            raise InputError(f"{case_id}/{arm}: semantic, generation, and judge evidence are required")
        _verify_hash(semantic, "prompt", "prompt_sha256", f"{case_id} semantic diagnosis")
        _verify_hash(semantic, "raw_response", "response_sha256", f"{case_id} semantic diagnosis")
        _verify_hash(
            semantic,
            "invocation_events",
            "invocation_events_sha256",
            f"{case_id} semantic invocation",
        )
        if semantic.get("prompt") != _semantic_prompt(case):
            raise InputError(f"{case_id}: semantic diagnosis prompt is stale")
        semantic_canonical = _validate_generation(
            _extract_json_object(semantic["raw_response"]), case["source"]
        )
        if semantic.get("parsed") != semantic_canonical:
            raise InputError(f"{case_id}: semantic diagnosis differs from raw response")
        if semantic_canonical.get("rewrite") != case["source"]:
            raise InputError(f"{case_id}: semantic diagnosis edited the source")
        if not allow_offline and not semantic["invocation_events"].strip():
            raise InputError(f"{case_id}: live semantic invocation events are missing")
        _reject_tool_events(semantic["invocation_events"], f"{case_id} semantic diagnosis")
        _verify_hash(generation, "prompt", "prompt_sha256", f"{case_id}/{arm} generation")
        _verify_hash(generation, "raw_response", "response_sha256", f"{case_id}/{arm} generation")
        _verify_hash(
            generation,
            "invocation_events",
            "invocation_events_sha256",
            f"{case_id}/{arm} invocation",
        )
        if not allow_offline and not generation["invocation_events"].strip():
            raise InputError(f"{case_id}/{arm}: live invocation events are missing")
        _reject_tool_events(generation["invocation_events"], f"{case_id}/{arm} generation")
        if provenance.get("generation_prompt_sha256") != generation["prompt_sha256"]:
            raise InputError(f"{case_id}/{arm}: stale generation prompt provenance")
        if provenance.get("generation_response_sha256") != generation["response_sha256"]:
            raise InputError(f"{case_id}/{arm}: stale generation response provenance")
        if case["source"] not in generation["prompt"]:
            raise InputError(f"{case_id}/{arm}: generation prompt is not bound to source")
        if arm == "with_skill":
            if resolved_contract not in generation["prompt"]:
                raise InputError(f"{case_id}/{arm}: prompt omits resolved shipping contract")
        elif resolved_contract in generation["prompt"]:
            raise InputError(f"{case_id}/{arm}: baseline prompt leaks shipping contract")
        raw_generation = _extract_json_object(generation["raw_response"])
        if raw_generation != generation.get("model_parsed"):
            raise InputError(f"{case_id}/{arm}: parsed generation differs from raw response")
        try:
            canonical_generation = _validate_generation(raw_generation, case["source"])
        except RunnerError as exc:
            raise InputError(f"{case_id}/{arm}: raw generation is invalid: {exc}") from exc
        parsed_generation = generation.get("parsed")
        if parsed_generation != canonical_generation:
            raise InputError(f"{case_id}/{arm}: normalized generation differs from raw response")
        if run.get("findings") != parsed_generation.get("findings"):
            raise InputError(f"{case_id}/{arm}: scored findings differ from generation evidence")
        if run.get("rewrite") != parsed_generation.get("rewrite"):
            raise InputError(f"{case_id}/{arm}: scored rewrite differs from generation evidence")
        source_diagnostics = evidence.get("source_diagnostics")
        validation_map = evidence.get("validation")
        validation = validation_map.get(arm) if isinstance(validation_map, dict) else None
        required_diagnostics = {
            "banned_phrase", "structure", "silhouette", "readability", "constraints"
        }
        required_validation = {
            "preservation", "banned_phrase", "structure", "silhouette", "readability", "diff",
            "change_coverage", "attribution_preservation",
        }
        if not isinstance(source_diagnostics, dict) or not required_diagnostics <= set(source_diagnostics):
            raise InputError(f"{case_id}/{arm}: source diagnostics are incomplete")
        if source_diagnostics.get("source_sha256") != _sha256(case["source"]):
            raise InputError(f"{case_id}/{arm}: source diagnostics are stale")
        initial_generation_prompt = _generation_prompt(
            case=case,
            arm=arm,
            scanner_findings=(
                source_diagnostics.get("banned_phrase", {}).get("findings", [])
                if arm == "with_skill"
                else None
            ),
            semantic_findings=(
                semantic_canonical.get("findings", []) if arm == "with_skill" else None
            ),
            source_diagnostics=source_diagnostics if arm == "with_skill" else None,
            shipping_contract=shipping_contract,
        )
        expected_generation_prompt = initial_generation_prompt
        attempts = generation.get("attempts")
        if attempts is not None:
            if not isinstance(attempts, list) or len(attempts) < 2:
                raise InputError(f"{case_id}/{arm}: retry attempts are malformed")
            if provenance.get("generation_attempts") != len(attempts):
                raise InputError(f"{case_id}/{arm}: retry attempt count is stale")
            for attempt_index, attempt in enumerate(attempts):
                label = f"{case_id}/{arm} attempt {attempt_index + 1}"
                if not isinstance(attempt, dict):
                    raise InputError(f"{label}: evidence is malformed")
                if attempt.get("prompt") != expected_generation_prompt:
                    raise InputError(f"{label}: prompt is stale")
                _verify_hash(attempt, "prompt", "prompt_sha256", label)
                _verify_hash(attempt, "raw_response", "response_sha256", label)
                _verify_hash(
                    attempt, "invocation_events", "invocation_events_sha256", label
                )
                attempt_raw = _extract_json_object(attempt["raw_response"])
                if attempt_raw != attempt.get("model_parsed"):
                    raise InputError(f"{label}: parsed generation differs from raw response")
                attempt_generation = _validate_generation(attempt_raw, case["source"])
                if attempt.get("parsed") != attempt_generation:
                    raise InputError(f"{label}: normalized generation differs from raw response")
                attempt_validation = attempt.get("validation")
                if not isinstance(attempt_validation, dict):
                    raise InputError(f"{label}: validation is missing")
                if attempt_index < len(attempts) - 1:
                    directives = _retry_directives(
                        attempt_generation,
                        attempt_validation,
                        source_diagnostics.get("genre", "prose"),
                    )
                    if not directives:
                        raise InputError(f"{label}: retry has no shipping blocker")
                    expected_generation_prompt = _retry_prompt(
                        initial_generation_prompt, attempt_generation, directives
                    )
                elif _validation_blockers(attempt_validation):
                    raise InputError(f"{label}: final retry still fails shipping validation")
            final_attempt = attempts[-1]
            for key in (
                "prompt", "prompt_sha256", "raw_response", "response_sha256",
                "invocation_events", "invocation_events_sha256", "model_parsed", "parsed",
            ):
                if generation.get(key) != final_attempt.get(key):
                    raise InputError(f"{case_id}/{arm}: final retry evidence is inconsistent")
        elif provenance.get("generation_attempts") != 1:
            raise InputError(f"{case_id}/{arm}: generation attempt count is stale")
        if generation.get("prompt") != expected_generation_prompt:
            raise InputError(f"{case_id}/{arm}: generation prompt is stale")
        if not isinstance(validation, dict) or not required_validation <= set(validation):
            raise InputError(f"{case_id}/{arm}: post-rewrite validation is incomplete")
        validation_scan = validation.get("banned_phrase")
        if (
            not isinstance(validation_scan, dict)
            or validation_scan.get("source_sha256") != _sha256(run["rewrite"])
        ):
            raise InputError(f"{case_id}/{arm}: validation is not bound to scored rewrite")
        if validation.get("workflow") != "shipping_gate":
            raise InputError(f"{case_id}/{arm}: validation workflow is ambiguous")
        canonical_coverage = _change_coverage(
            case["source"], run["rewrite"], run["findings"]
        )
        if validation.get("change_coverage") != canonical_coverage:
            raise InputError(f"{case_id}/{arm}: change coverage differs from scored rewrite")
        canonical_attribution = _attribution_preservation(case["source"], run["rewrite"])
        if validation.get("attribution_preservation") != canonical_attribution:
            raise InputError(f"{case_id}/{arm}: attribution preservation differs from scored rewrite")
        if arm == "with_skill" and _validation_blockers(validation):
            raise InputError(f"{case_id}/{arm}: shipping-blocking validation failure was scored")

        _verify_hash(judge, "prompt", "prompt_sha256", f"{case_id}/{arm} judge")
        _verify_hash(judge, "raw_response", "response_sha256", f"{case_id}/{arm} judge")
        _verify_hash(
            judge,
            "invocation_events",
            "invocation_events_sha256",
            f"{case_id}/{arm} judge invocation",
        )
        if not allow_offline and not judge["invocation_events"].strip():
            raise InputError(f"{case_id}/{arm}: live judge invocation events are missing")
        _reject_tool_events(judge["invocation_events"], f"{case_id}/{arm} judge")
        if provenance.get("judge_prompt_sha256") != judge["prompt_sha256"]:
            raise InputError(f"{case_id}/{arm}: stale judge prompt provenance")
        if provenance.get("judge_response_sha256") != judge["response_sha256"]:
            raise InputError(f"{case_id}/{arm}: stale judge response provenance")
        raw_judge = _extract_json_object(judge["raw_response"])
        if raw_judge != judge.get("parsed"):
            raise InputError(f"{case_id}/{arm}: parsed judge differs from raw response")
        blind_map = judge.get("blind_map")
        if not isinstance(blind_map, dict) or set(blind_map.values()) != {"with_skill", "without_skill"}:
            raise InputError(f"{case_id}/{arm}: invalid blind-arm map")
        labels = [label for label, mapped_arm in blind_map.items() if mapped_arm == arm]
        if len(labels) != 1:
            raise InputError(f"{case_id}/{arm}: arm is not uniquely blinded")
        canonical_generations: dict[str, dict] = {}
        for evidence_arm in ("with_skill", "without_skill"):
            arm_evidence = generation_map.get(evidence_arm)
            if not isinstance(arm_evidence, dict):
                raise InputError(f"{case_id}: missing {evidence_arm} generation evidence")
            arm_raw = _extract_json_object(arm_evidence.get("raw_response"))
            try:
                canonical_generations[evidence_arm] = _validate_generation(
                    arm_raw, case["source"]
                )
            except RunnerError as exc:
                raise InputError(
                    f"{case_id}/{evidence_arm}: raw generation is invalid: {exc}"
                ) from exc
        expected_judge_prompt = _judge_prompt(case, canonical_generations, blind_map)
        if judge["prompt"] != expected_judge_prompt:
            raise InputError(f"{case_id}/{arm}: judge prompt is not bound to raw rewrites")
        candidate = raw_judge.get("candidates", {}).get(labels[0])
        if not isinstance(candidate, dict):
            raise InputError(f"{case_id}/{arm}: judge candidate evidence is missing")
        for key in ("repairs", "protections", "constraints", "net_improved"):
            if run.get(key) != candidate.get(key):
                raise InputError(f"{case_id}/{arm}: scored {key} differs from judge evidence")
        winner = raw_judge.get("winner")
        if winner not in {"candidate_a", "candidate_b", "tie"}:
            raise InputError(f"{case_id}/{arm}: invalid blind judge winner")
        winner_arm = blind_map.get(winner) if winner != "tie" else None
        if run.get("beats_without_skill") is not (arm == winner_arm):
            raise InputError(f"{case_id}/{arm}: pairwise winner differs from judge evidence")
        lower_judge_prompt = judge["prompt"].lower()
        if any(marker in lower_judge_prompt for marker in ("with_skill", "without_skill", "unslop")):
            raise InputError(f"{case_id}/{arm}: judge prompt leaks treatment identity")

        if arm == "with_skill":
            scanner = source_diagnostics.get("banned_phrase")
            if not isinstance(scanner, dict):
                raise InputError(f"{case_id}/{arm}: scanner evidence is required")
            source_hash = _sha256(case["source"])
            if scanner.get("source_sha256") != source_hash or provenance.get("source_sha256") != source_hash:
                raise InputError(f"{case_id}/{arm}: scanner evidence is stale for source")
            if provenance.get("scanner_source_sha256") != scanner.get("scanner_source_sha256"):
                raise InputError(f"{case_id}/{arm}: scanner implementation hash mismatch")


def _checked_spans(case: dict, key: str) -> list[dict]:
    source = case.get("source")
    spans = case.get(key, [])
    if not isinstance(source, str) or not isinstance(spans, list):
        raise InputError(f"case {case.get('id')}: source must be text and {key} must be a list")
    seen: set[str] = set()
    for span in spans:
        if not isinstance(span, dict):
            raise InputError(f"case {case.get('id')}: malformed {key} row")
        span_id = span.get("id")
        start, end, text = span.get("start"), span.get("end"), span.get("text")
        if not isinstance(span_id, str) or not span_id or span_id in seen:
            raise InputError(f"case {case.get('id')}: {key} ids must be unique non-empty strings")
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(source):
            raise InputError(f"case {case.get('id')}: invalid offsets for {span_id}")
        if source[start:end] != text:
            raise InputError(f"case {case.get('id')}: text/offset mismatch for {span_id}")
        seen.add(span_id)
    return spans


def validate_manifest(manifest: dict) -> dict[str, dict]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise InputError(f"manifest schema must be {MANIFEST_SCHEMA}")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise InputError("manifest cases must be a non-empty list")
    indexed: dict[str, dict] = {}
    for case in cases:
        if not isinstance(case, dict):
            raise InputError("every case must be an object")
        case_id, split = case.get("id"), case.get("split")
        if not isinstance(case_id, str) or not case_id or case_id in indexed:
            raise InputError("case ids must be unique non-empty strings")
        if split not in {"tune", "holdout", "holdback"}:
            raise InputError(f"case {case_id}: invalid split {split!r}")
        _checked_spans(case, "issues")
        _checked_spans(case, "protected_spans")
        constraints = case.get("constraints", [])
        if not isinstance(constraints, list) or any(
            not isinstance(row, dict) or not isinstance(row.get("id"), str)
            for row in constraints
        ):
            raise InputError(f"case {case_id}: constraints must have ids")
        normalized_constraints = []
        constraint_ids: set[str] = set()
        for row in constraints:
            constraint_id = row["id"]
            description = row.get("description", row.get("text"))
            if (
                not constraint_id
                or constraint_id in constraint_ids
                or not isinstance(description, str)
                or not description
            ):
                raise InputError(
                    f"case {case_id}: constraints need unique ids and descriptions"
                )
            normalized = dict(row)
            normalized["description"] = description
            normalized_constraints.append(normalized)
            constraint_ids.add(constraint_id)
        normalized_case = dict(case)
        normalized_case["constraints"] = normalized_constraints
        indexed[case_id] = normalized_case
    return indexed


def _overlap_ratio(left: dict, right: dict) -> float:
    overlap = max(0, min(left["end"], right["end"]) - max(left["start"], right["start"]))
    union = max(left["end"], right["end"]) - min(left["start"], right["start"])
    return overlap / union if union else 0.0


def match_findings(findings: list[dict], issues: list[dict], source_length: int) -> tuple[int, int, int]:
    """Return true positives, false positives, and false negatives.

    A prediction must have at least 0.5 intersection-over-union with one gold
    span. Category labels are
    descriptive rather than identity keys: a neutral editor may call the same
    phrase a cliche while UNSLOP calls it jargon. Each gold issue can match
    once, so duplicate or shotgun findings count as false positives.
    """
    unmatched = set(range(len(issues)))
    true_positives = 0
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if (
            not isinstance(finding.get("start"), int)
            or not isinstance(finding.get("end"), int)
            or not 0 <= finding["start"] < finding["end"] <= source_length
        ):
            continue
        candidates = []
        for index in unmatched:
            issue = issues[index]
            ratio = _overlap_ratio(finding, issue)
            if ratio >= 0.5:
                candidates.append((ratio, index))
        if candidates:
            _, winner = max(candidates)
            unmatched.remove(winner)
            true_positives += 1
    return true_positives, len(findings) - true_positives, len(unmatched)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _optional_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _metric_counts() -> dict[str, int]:
    return {
        "tp": 0,
        "fp": 0,
        "fn": 0,
        "repairs_ok": 0,
        "repairs_total": 0,
        "preserved_ok": 0,
        "preserved_total": 0,
        "protected_ok": 0,
        "protected_total": 0,
        "improved_ok": 0,
        "improved_total": 0,
        "noop_ok": 0,
        "noop_total": 0,
    }


def _finalize(counts: dict[str, int]) -> dict:
    precision = _ratio(counts["tp"], counts["tp"] + counts["fp"])
    recall = _ratio(counts["tp"], counts["tp"] + counts["fn"])
    preservation = _ratio(counts["preserved_ok"], counts["preserved_total"])
    protected = _ratio(counts["protected_ok"], counts["protected_total"])
    return {
        "detection_precision": round(precision, 6),
        "detection_recall": round(recall, 6),
        "repair_success": round(_ratio(counts["repairs_ok"], counts["repairs_total"]), 6),
        "preservation": round(preservation, 6),
        "damage_rate": round(1.0 - protected, 6),
        "net_improvement": (
            round(value, 6)
            if (value := _optional_ratio(counts["improved_ok"], counts["improved_total"]))
            is not None
            else None
        ),
        "clean_noop_rate": (
            round(value, 6)
            if (value := _optional_ratio(counts["noop_ok"], counts["noop_total"]))
            is not None
            else None
        ),
        "counts": counts,
    }


def _accumulate_run(
    bucket: dict[str, int],
    case: dict,
    run: dict,
    *,
    tp: int,
    fp: int,
    fn: int,
) -> None:
    bucket["tp"] += tp
    bucket["fp"] += fp
    bucket["fn"] += fn
    repairs = run["repairs"]
    protections = run["protections"]
    constraints = run["constraints"]
    for issue in case.get("issues", []):
        bucket["repairs_total"] += 1
        bucket["repairs_ok"] += repairs.get(issue["id"]) is True
    for protected in case.get("protected_spans", []):
        bucket["protected_total"] += 1
        bucket["protected_ok"] += protections.get(protected["id"]) is True
    for constraint in case.get("constraints", []):
        bucket["preserved_total"] += 1
        bucket["preserved_ok"] += constraints.get(constraint["id"]) is True
    if case.get("issues"):
        bucket["improved_total"] += 1
        bucket["improved_ok"] += run["net_improved"] is True
    else:
        bucket["noop_total"] += 1
        bucket["noop_ok"] += run["rewrite"] == case["source"]


def score(
    manifest: dict,
    predictions: dict,
    *,
    split: str | None = None,
    verify_evidence: bool = True,
    allow_offline: bool = False,
) -> dict:
    cases = validate_manifest(manifest)
    if predictions.get("schema") != PREDICTION_SCHEMA:
        raise InputError(f"prediction schema must be {PREDICTION_SCHEMA}")
    if verify_evidence:
        verify_prediction_evidence(
            manifest,
            predictions,
            split=split,
            allow_offline=allow_offline,
        )
    runs = predictions.get("runs")
    if not isinstance(runs, list):
        raise InputError("prediction runs must be a list")

    required_arms = manifest.get("required_arms", ["with_skill", "without_skill"])
    if (
        not isinstance(required_arms, list)
        or not required_arms
        or any(not isinstance(arm, str) or not arm for arm in required_arms)
    ):
        raise InputError("manifest required_arms must be a non-empty string list")
    grouped: dict[tuple[str, str], dict[str, int]] = defaultdict(_metric_counts)
    case_grouped: dict[tuple[str, str], dict[str, int]] = defaultdict(_metric_counts)
    paired_flags: dict[str, dict[str, bool]] = defaultdict(dict)
    seen: set[tuple[str, str]] = set()
    deterministic_overrides: list[dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, dict):
            raise InputError("every prediction run must be an object")
        case_id, arm = run.get("case_id"), run.get("arm")
        if case_id not in cases or not isinstance(arm, str) or not arm:
            raise InputError(f"unknown case or arm: {case_id!r}/{arm!r}")
        case = cases[case_id]
        if split and case["split"] != split:
            continue
        run_key = (case_id, arm)
        if run_key in seen:
            raise InputError(f"duplicate run {case_id}/{arm}")
        seen.add(run_key)

        if not isinstance(run.get("rewrite"), str) or not run["rewrite"].strip():
            raise InputError(f"{case_id}/{arm}: rewrite must be non-empty text")
        provenance = run.get("provenance")
        if not isinstance(provenance, dict) or not provenance.get("model"):
            raise InputError(f"{case_id}/{arm}: model provenance is required")

        findings = run.get("findings", [])
        if not isinstance(findings, list):
            raise InputError(f"{case_id}/{arm}: findings must be a list")
        tp, fp, fn = match_findings(findings, case.get("issues", []), len(case["source"]))

        repairs = run.get("repairs", {})
        protections = run.get("protections", {})
        constraints = run.get("constraints", {})
        if not all(isinstance(value, dict) for value in (repairs, protections, constraints)):
            raise InputError(f"{case_id}/{arm}: adjudications must be id-to-boolean objects")

        if not isinstance(run.get("net_improved"), bool):
            raise InputError(f"{case_id}/{arm}: net_improved must be boolean")
        scored_run = dict(run)
        scored_run["protections"] = dict(protections)
        exact_damage = False
        for protected in case.get("protected_spans", []):
            exact_policy = protected.get("enforcement") == "exact_span"
            if (
                exact_policy
                and protected["text"] not in run["rewrite"]
                and scored_run["protections"].get(protected["id"]) is True
            ):
                scored_run["protections"][protected["id"]] = False
                exact_damage = True
                deterministic_overrides.append({
                    "case_id": case_id,
                    "arm": arm,
                    "field": f"protections.{protected['id']}",
                    "judge_value": True,
                    "scored_value": False,
                    "reason": "exact protected span is absent from rewrite",
                })
        if exact_damage and scored_run["net_improved"] is True:
            scored_run["net_improved"] = False
            deterministic_overrides.append({
                "case_id": case_id,
                "arm": arm,
                "field": "net_improved",
                "judge_value": True,
                "scored_value": False,
                "reason": "exact protected-span damage forbids net improvement",
            })
        _accumulate_run(grouped[(case["split"], arm)], case, scored_run, tp=tp, fp=fp, fn=fn)
        _accumulate_run(case_grouped[(case_id, arm)], case, scored_run, tp=tp, fp=fp, fn=fn)
        if "beats_without_skill" in run:
            if not isinstance(run["beats_without_skill"], bool):
                raise InputError(f"{case_id}/{arm}: beats_without_skill must be boolean")
            paired_flags[case_id][arm] = run["beats_without_skill"]

    expected = {
        (case_id, arm)
        for case_id, case in cases.items()
        if split is None or case["split"] == split
        for arm in required_arms
    }
    missing = sorted(expected - seen)
    unexpected_arms = sorted(key for key in seen if key[1] not in required_arms)
    if missing:
        raise InputError("missing required runs: " + ", ".join(f"{case}/{arm}" for case, arm in missing))
    if unexpected_arms:
        raise InputError(
            "runs use undeclared arms: "
            + ", ".join(f"{case}/{arm}" for case, arm in unexpected_arms)
        )

    by_split: dict[str, dict[str, dict]] = defaultdict(dict)
    by_arm_counts: dict[str, dict[str, int]] = defaultdict(_metric_counts)
    for (split_name, arm), counts in sorted(grouped.items()):
        by_split[split_name][arm] = _finalize(counts)
        aggregate = by_arm_counts[arm]
        for key, value in counts.items():
            aggregate[key] += value
    by_arm = {arm: _finalize(counts) for arm, counts in sorted(by_arm_counts.items())}
    by_case: dict[str, dict[str, dict]] = defaultdict(dict)
    for (case_id, arm), counts in sorted(case_grouped.items()):
        by_case[case_id][arm] = _finalize(counts)
    lift = None
    if "with_skill" in by_arm and "without_skill" in by_arm:
        lift = {}
        for metric in (
                "detection_precision",
                "detection_recall",
                "repair_success",
                "preservation",
                "damage_rate",
                "net_improvement",
                "clean_noop_rate",
        ):
            left = by_arm["with_skill"][metric]
            right = by_arm["without_skill"][metric]
            lift[metric] = round(left - right, 6) if left is not None and right is not None else None
    paired = None
    complete_pair_flags = {
        case_id: flags
        for case_id, flags in paired_flags.items()
        if all(arm in flags for arm in ("with_skill", "without_skill"))
    }
    if complete_pair_flags:
        with_wins = 0
        without_wins = 0
        ties = 0
        for case_id, flags in complete_pair_flags.items():
            if flags["with_skill"] and flags["without_skill"]:
                raise InputError(f"{case_id}: both arms cannot beat without_skill")
            if flags["with_skill"]:
                with_wins += 1
            elif flags["without_skill"]:
                without_wins += 1
            else:
                ties += 1
        compared = len(complete_pair_flags)
        paired = {
            "cases": compared,
            "with_skill_wins": with_wins,
            "without_skill_wins": without_wins,
            "ties": ties,
            "with_skill_win_rate": round(with_wins / compared, 6),
        }
    return {
        "schema": METRIC_SCHEMA,
        "split_filter": split,
        "by_split": dict(by_split),
        "by_case": dict(by_case),
        "by_arm": by_arm,
        "with_skill_minus_without_skill": lift,
        "paired_comparison": paired,
        "deterministic_overrides": deterministic_overrides,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--out", type=Path, help="write scored JSON here (default: stdout)")
    parser.add_argument("--split", choices=("tune", "holdout", "holdback"))
    parser.add_argument("--arm", help="also print a compact summary for this arm")
    parser.add_argument(
        "--allow-offline",
        action="store_true",
        help="accept runner-produced offline fixtures (tests only; never acceptance evidence)",
    )
    args = parser.parse_args(argv)
    try:
        result = score(
            _load(args.manifest),
            _load(args.predictions),
            split=args.split,
            allow_offline=args.allow_offline,
        )
    except InputError as exc:
        print(f"core_metrics: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(f"core_metrics: cannot write {args.out}: {exc}", file=sys.stderr)
            return 2
    else:
        print(rendered, end="")
    if args.arm:
        metrics = result["by_arm"].get(args.arm)
        if metrics is None:
            print(f"core_metrics: arm {args.arm!r} has no scored runs", file=sys.stderr)
            return 2
        print(
            f"detection_precision={metrics['detection_precision']:.6f} "
            f"detection_recall={metrics['detection_recall']:.6f}"
        )
        print(
            f"repair_success={metrics['repair_success']:.6f} "
            f"preservation={metrics['preservation']:.6f} "
            f"damage_rate={metrics['damage_rate']:.6f}"
        )
        print(f"net_improvement={metrics['net_improvement']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
