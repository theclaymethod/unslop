#!/usr/bin/env python3
"""Offline contract test for the end-to-end core benchmark runner."""

from __future__ import annotations

import json
import io
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evals"))

from core_runner import (  # noqa: E402
    RunnerError,
    _attribution_preservation,
    _change_coverage,
    _generation_prompt,
    _finding_sentence_spans,
    _merge_case_results,
    main as core_runner_main,
    _needs_with_skill_generation,
    _semantic_judgment_prompt,
    _semantic_resolution,
    _semantic_prompt,
    _shipping_contract,
    _validate_generation,
    _validate_semantic_judgment,
    _validation_blockers,
)
from core_metrics import main as core_metrics_main  # noqa: E402


def _span(source: str, text: str, span_id: str, category: str | None = None) -> dict:
    start = source.index(text)
    row = {"id": span_id, "start": start, "end": start + len(text), "text": text}
    if category:
        row["category"] = category
    return row


def _run(command: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    entrypoints = {
        str(ROOT / "evals" / "core_runner.py"): core_runner_main,
        str(ROOT / "evals" / "core_metrics.py"): core_metrics_main,
    }
    entrypoint = entrypoints.get(command[1]) if len(command) > 1 else None
    if entrypoint is None:
        return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, env=env)
    stdout = io.StringIO()
    stderr = io.StringIO()
    old_confirm = os.environ.get("UNSLOP_CONFIRM_HOLDBACK")
    if env is not None:
        if "UNSLOP_CONFIRM_HOLDBACK" in env:
            os.environ["UNSLOP_CONFIRM_HOLDBACK"] = env["UNSLOP_CONFIRM_HOLDBACK"]
        else:
            os.environ.pop("UNSLOP_CONFIRM_HOLDBACK", None)
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            returncode = entrypoint(command[2:])
    finally:
        if old_confirm is None:
            os.environ.pop("UNSLOP_CONFIRM_HOLDBACK", None)
        else:
            os.environ["UNSLOP_CONFIRM_HOLDBACK"] = old_confirm
    return subprocess.CompletedProcess(
        command, returncode, stdout.getvalue(), stderr.getvalue()
    )


def main() -> int:
    safety_source = (
        "The certificate permits 60 C for two hours. "
        "Run the material at 75 C for four hours. "
        "If it fails, repeat the 75 C cycle."
    )
    initial_unsafe = _span(
        safety_source,
        "Run the material at 75 C for four hours.",
        "unsafe-initial",
        "unsafe_action",
    )
    repeat_unsafe = _span(
        safety_source,
        "If it fails, repeat the 75 C cycle.",
        "unsafe-repeat",
        "unsafe_action",
    )
    required_safety_findings = [initial_unsafe, repeat_unsafe]
    partial_safety_rewrite = safety_source.replace(
        "If it fails, repeat the 75 C cycle.",
        "Do not repeat the unapproved 75 C cycle.",
    )
    complete_safety_rewrite = (
        "The certificate permits 60 C for two hours. "
        "Do not run the material at the unapproved 75 C for four hours. "
        "Do not repeat the unapproved 75 C cycle."
    )
    semantic_resolution_gate = (
        _semantic_resolution(
            safety_source,
            partial_safety_rewrite,
            required_safety_findings,
            required_safety_findings,
        )["passed"]
        is False
        and _semantic_resolution(
            safety_source,
            complete_safety_rewrite,
            required_safety_findings,
            required_safety_findings,
        )["passed"]
        is True
        and _semantic_resolution(
            safety_source,
            complete_safety_rewrite,
            required_safety_findings,
            [repeat_unsafe],
        )["passed"]
        is False
    )
    adjacent_resolution_source = (
        "Submission is due on 10 September. Keep this unrelated sentence."
    )
    adjacent_resolution_finding = _span(
        adjacent_resolution_source,
        "10 September",
        "adjacent-resolution",
        "schedule_inconsistency",
    )
    adjacent_resolution_finding["rationale"] = "The deadline conflicts with 20 September."
    adjacent_edit_not_resolution = (
        _semantic_resolution(
            adjacent_resolution_source,
            "Submission is due on 10 September. Retain this unrelated sentence.",
            [adjacent_resolution_finding],
            [adjacent_resolution_finding],
        )["passed"]
        is False
        and _semantic_resolution(
            adjacent_resolution_source,
            "Submission is due on 10 September! Retain this unrelated sentence.",
            [adjacent_resolution_finding],
            [adjacent_resolution_finding],
        )["passed"]
        is False
    )
    exact_target_source = "Alice schedules inspection for 10 September."
    exact_target_finding = _span(
        exact_target_source, "10 September", "exact-target", "contradiction"
    )
    exact_target_finding["rationale"] = "The date conflicts with the record."
    same_sentence_actor_swap_blocked = _change_coverage(
        exact_target_source,
        "Bob schedules inspection for 20 September.",
        [exact_target_finding],
    )["passed"] is False
    same_sentence_evidence_source = (
        "Alice recorded 20 September, but the table lists 10 September."
    )
    same_sentence_edit = _span(
        same_sentence_evidence_source,
        "10 September",
        "same-sentence-target",
        "contradiction",
    )
    same_sentence_evidence = _span(
        same_sentence_evidence_source, "Alice recorded 20 September", "evidence"
    )
    same_sentence_edit["rationale"] = "The table conflicts with Alice's record."
    same_sentence_edit["evidence_spans"] = [
        {key: same_sentence_evidence[key] for key in ("start", "end", "text")}
    ]
    same_sentence_evidence_mutation_blocked = _change_coverage(
        same_sentence_evidence_source,
        "Bob recorded 21 September, but the table lists 20 September.",
        [same_sentence_edit],
    )["passed"] is False
    evidence_as_second_finding = {
        "start": same_sentence_evidence["start"],
        "end": same_sentence_evidence["end"],
        "text": same_sentence_evidence["text"],
        "category": "clarity",
        "rationale": "Attempt to make another finding's evidence writable.",
    }
    try:
        _validate_generation(
            {
                "findings": [same_sentence_edit, evidence_as_second_finding],
                "rewrite": same_sentence_evidence_source,
            },
            same_sentence_evidence_source,
        )
        cross_finding_evidence_overlap_rejected = False
    except RunnerError:
        cross_finding_evidence_overlap_rejected = True
    semantic_judgment_prompt = _semantic_judgment_prompt(
        safety_source, required_safety_findings, complete_safety_rewrite
    )
    semantic_judgment_gate = (
        _validate_semantic_judgment(
            {
                "resolutions": {"semantic-1": False, "semantic-2": True},
                "passed": False,
                "rationale": "The first action remains affirmative.",
            },
            required_safety_findings,
        )["passed"]
        is False
        and _validate_semantic_judgment(
            {
                "resolutions": {"semantic-1": True, "semantic-2": True},
                "passed": True,
                "rationale": "Both actions are explicitly rejected.",
            },
            required_safety_findings,
        )["passed"]
        is True
        and "unrelated negation" in semantic_judgment_prompt
        and "double negative" in semantic_judgment_prompt
        and "duplicate affirmative action" in semantic_judgment_prompt
        and "attributed record is not an operative duplicate" in semantic_judgment_prompt
        and "adjacent evidence sentence" in semantic_judgment_prompt
        and "dropping a responsible actor" in semantic_judgment_prompt
    )
    paragraph_source = "Keep this sentence.\n\nRemove this coda."
    paragraph_finding = _span(
        paragraph_source, "Remove this coda.", "paragraph-coda", "empty_abstraction"
    )
    paragraph_delete_coverage = _change_coverage(
        paragraph_source, "Keep this sentence.", [paragraph_finding]
    ).get("passed") is True
    adjacent_source = "Keep this sentence.\nDELETE\nRemove this coda."
    adjacent_text_still_blocked = _change_coverage(
        adjacent_source,
        "Keep this sentence.",
        [_span(
            adjacent_source,
            "Remove this coda.",
            "paragraph-coda",
            "empty_abstraction",
        )],
    ).get("passed") is False
    sentence_boundary_source = "The report is complete. The certificate is pending."
    sentence_boundary_finding = _span(
        sentence_boundary_source, "complete", "status-conflict", "contradiction"
    )
    post_sentence_insertion_blocked = _change_coverage(
        sentence_boundary_source,
        "The report is complete. That status conflicts with the pending certificate. "
        "The certificate is pending.",
        [sentence_boundary_finding],
    ).get("passed") is False
    relational_evidence_stays_protected = _change_coverage(
        sentence_boundary_source,
        "The report is complete, but the certificate remains pending.",
        [sentence_boundary_finding],
    ).get("passed") is False
    actor_source = (
        "The report is complete. Review remains pending by the city inspector."
    )
    actor_finding = _span(
        actor_source, "complete", "actor-conflict", "contradiction"
    )
    relational_actor_preservation = (
        _change_coverage(
            actor_source,
            "The report is not complete. Review remains pending.",
            [actor_finding],
        )["passed"]
        is False
        and _change_coverage(
            actor_source,
            "The report is not complete. Review remains pending by the city inspector.",
            [actor_finding],
        )["passed"]
        is True
    )
    indented_code_source = "Remove this coda.\n\n    keep_as_code()"
    indented_code_still_blocked = _change_coverage(
        indented_code_source,
        "keep_as_code()",
        [_span(
            indented_code_source,
            "Remove this coda.",
            "paragraph-coda",
            "empty_abstraction",
        )],
    ).get("passed") is False
    list_continuation_source = "Remove this coda.\n\n  continued list item"
    list_continuation_still_blocked = _change_coverage(
        list_continuation_source,
        "continued list item",
        [_span(
            list_continuation_source,
            "Remove this coda.",
            "paragraph-coda",
            "empty_abstraction",
        )],
    ).get("passed") is False
    source = "Here's the thing: the report says the API returns 200 on success, while Section 4 remains unchanged."
    issue = _span(source, "Here's the thing: the", "issue-1", "throat_clearing")
    protected = _span(source, "report says the API returns 200 on success", "good-1")
    issue["rationale"] = "The generic opener delays the technical fact."
    protected["kind"] = "good_prose"
    protected["policy"] = "Preserve the API status fact and wording."
    case = {
        "id": "runner-fixture",
        "split": "tune",
        "genre": "technical",
        "register": "technical",
        "source": source,
        "provenance": {"kind": "unit_fixture"},
        "issues": [issue],
        "protected_spans": [protected],
        "constraints": [{"id": "constraint-1", "description": "Section 4 remains unchanged."}],
    }
    semantic_prompt = _semantic_prompt(case)
    repeated_source = "The draft is clear. The draft is not final."
    try:
        _validate_generation(
            {
                "findings": [{
                    "start": repeated_source.rfind("The draft") - 1,
                    "end": repeated_source.rfind("The draft") + len("The draft") - 1,
                    "text": "The draft",
                    "category": "clarity",
                    "rationale": "The second occurrence is the finding.",
                }],
                "rewrite": repeated_source,
            },
            repeated_source,
        )
        repeated_offset_rejected = False
    except RunnerError:
        repeated_offset_rejected = True
    decimal_source = (
        "The approved part is BR-204. "
        "The installation line names BR-240 and records 10.0 mm at the face. "
        "Keep this sentence."
    )
    decimal_finding = _span(decimal_source, "BR-240", "decimal-boundary")
    decimal_sentence_span = _finding_sentence_spans(
        decimal_source, [decimal_finding]
    )[0]
    decimal_sentence_coverage = (
        decimal_source[decimal_sentence_span[0]:decimal_sentence_span[1]]
        == " The installation line names BR-240 and records 10.0 mm at the face."
        and _change_coverage(
            decimal_source,
            decimal_source.replace(
                "BR-240 and records 10.0 mm at the face",
                "BR-204 and records 10.0 mm at the face",
            ),
            [decimal_finding],
        )["passed"]
    )
    broad_date_source = (
        "The sequence schedules submission on 20 September. "
        "The table sets the deadline at 10 September."
    )
    date_edit = _span(
        broad_date_source, "10 September", "date-conflict", "schedule_inconsistency"
    )
    date_edit["rationale"] = "The deadline conflicts with the earlier schedule."
    first_date = _span(broad_date_source, "20 September", "date-evidence")
    date_edit["evidence_spans"] = [
        {key: first_date[key] for key in ("start", "end", "text")}
    ]
    separated_relational_evidence = (
        _validate_generation(
            {"findings": [date_edit], "rewrite": broad_date_source},
            broad_date_source,
        )["findings"][0]["evidence_spans"] == date_edit["evidence_spans"]
    )
    broad_date_finding = _span(
        broad_date_source,
        "20 September. The table sets the deadline at 10 September",
        "date-conflict",
        "contradiction",
    )
    broad_date_finding["rationale"] = "The two dates directly conflict."
    try:
        _validate_generation(
            {"findings": [broad_date_finding], "rewrite": broad_date_source},
            broad_date_source,
        )
        cross_sentence_edit_span_rejected = False
    except RunnerError:
        cross_sentence_edit_span_rejected = True
    resolved_contract = _shipping_contract()["resolved_contract"]
    precision_first_contract = (
        "Never use the current date" in semantic_prompt
        and "or lacks stated support" not in semantic_prompt
        and "A scanner match alone never authorizes an edit" in _generation_prompt(
            case,
            "with_skill",
            scanner_findings=[issue],
            semantic_findings=[],
            source_diagnostics={},
        )
        and "Inspect headings and closing calls to action" in _generation_prompt(
            case,
            "with_skill",
            scanner_findings=[],
            semantic_findings=[],
            source_diagnostics={},
        )
        and "number's role and unit" in semantic_prompt
        and "Inspect headings and closing calls to action" in semantic_prompt
        and "category-changing slogan" in semantic_prompt
        and "A bounded offer" in semantic_prompt
        and "Compare categorical predictions" in semantic_prompt
        and "ordinary promotional metaphor" in semantic_prompt
        and "Preserve a concrete closing call to action" in semantic_prompt
        and "closing generic platitude" in semantic_prompt
        and "agenda item repeats the document title" in semantic_prompt
        and "one span covering both" in semantic_prompt
        and "Put the other side" in semantic_prompt
        and "Never make both sentences writable" in semantic_prompt
        and "SOURCE-AUDIT FINDINGS are confirmed" in _generation_prompt(
            case,
            "with_skill",
            scanner_findings=[issue],
            semantic_findings=[issue],
            source_diagnostics={},
        )
        and "natural in-place replacement" in _generation_prompt(
            case,
            "with_skill",
            scanner_findings=[issue],
            semantic_findings=[issue],
            source_diagnostics={},
        )
        and "minimum adjacent boundary word" in _generation_prompt(
            case,
            "with_skill",
            scanner_findings=[issue],
            semantic_findings=[issue],
            source_diagnostics={},
        )
        and "Do not append editorial instructions" in _generation_prompt(
            case,
            "with_skill",
            scanner_findings=[issue],
            semantic_findings=[issue],
            source_diagnostics={},
        )
        and "name the concrete referent" in _generation_prompt(
            case,
            "with_skill",
            scanner_findings=[issue],
            semantic_findings=[issue],
            source_diagnostics={},
        )
        and "before that sentence's" in _generation_prompt(
            case,
            "with_skill",
            scanner_findings=[issue],
            semantic_findings=[issue],
            source_diagnostics={},
        )
        and "categorical completion or approval" in semantic_prompt
        and "claim against later" in semantic_prompt
        and "`scheduled`, or `outstanding`" in semantic_prompt
        and len(resolved_contract.split()) <= 650
    )
    generations = {
        "with_skill": {
            "findings": [
                {
                    "start": issue["start"],
                    "end": issue["end"],
                    "text": issue["text"],
                    "category": "throat_clearing",
                    "rationale": "Generic opener.",
                }
            ],
            "rewrite": "The report says the API returns 200 on success, while Section 4 remains unchanged.",
        },
        "without_skill": {
            "findings": [
                {
                    # Models frequently get character arithmetic wrong even
                    # when they copy an unambiguous source phrase exactly.
                    # The runner must normalize that evidence rather than
                    # discard an otherwise auditable live trial.
                    "start": 999,
                    "end": 1000,
                    "text": issue["text"],
                    "category": "generic opener",
                    "rationale": "Formulaic opening.",
                }
            ],
            "rewrite": source,
        },
    }
    judge = {
        "candidates": {
            "candidate_a": {
                "repairs": {"issue-1": True},
                "protections": {"good-1": True},
                "constraints": {"constraint-1": True},
                "net_improved": True,
            },
            "candidate_b": {
                "repairs": {"issue-1": False},
                "protections": {"good-1": True},
                "constraints": {"constraint-1": True},
                "net_improved": False,
            },
        },
        "winner": "candidate_a",
    }

    with tempfile.TemporaryDirectory(prefix="unslop_core_runner_") as raw:
        temp = Path(raw)
        manifest_path = temp / "manifest.json"
        responses_path = temp / "responses.json"
        predictions_path = temp / "predictions.json"
        manifest_path.write_text(
            json.dumps({"schema": "unslop-core-benchmark-v1", "cases": [case]}),
            encoding="utf-8",
        )
        responses_path.write_text(
            json.dumps(
                {
                    "generations": {case["id"]: generations},
                    "judges": {case["id"]: judge},
                }
            ),
            encoding="utf-8",
        )
        command = [
            sys.executable,
            str(ROOT / "evals" / "core_runner.py"),
            str(manifest_path),
            "--split",
            "tune",
            "--responses",
            str(responses_path),
            "--out",
            str(predictions_path),
        ]
        proc = _run(command)
        if proc.returncode:
            sys.stderr.write(proc.stderr)
            return proc.returncode
        predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
        arms = sorted(run["arm"] for run in predictions["runs"])
        case_evidence = predictions.get("evidence", [])
        canonical_evidence = (
            len(case_evidence) == 1
            and all("evidence" not in run for run in predictions["runs"])
            and "shipping_contract" not in predictions.get("provenance", {})
            and "shipping_contract" not in case_evidence[0]
            and "scanner" not in case_evidence[0]
            and all(
                "shipping_contract" not in generation
                for generation in case_evidence[0].get("generation", {}).values()
            )
        )
        evidence_ok = all(
            case_evidence[0].get("generation", {}).get(arm, {}).get("raw_response")
            and case_evidence[0].get("judge", {}).get("raw_response")
            for arm in ("with_skill", "without_skill")
        )
        provenance_ok = all(
            run.get("provenance", {}).get("model") == "gpt-5.6-luna"
            and run.get("provenance", {}).get("provider") == "fixture"
            and run.get("provenance", {}).get("generation_prompt_sha256")
            and run.get("provenance", {}).get("judge_prompt_sha256")
            for run in predictions["runs"]
        ) and predictions.get("provenance", {}).get("provider") == "fixture"
        root_provenance = predictions.get("provenance", {})
        reproducible_provenance = (
            isinstance(root_provenance.get("generated_at_utc"), str)
            and root_provenance.get("manifest_sha256")
            and root_provenance.get("runner_source_sha256")
            and root_provenance.get("model_adapter_source_sha256")
            and root_provenance.get("codex_cli_version")
            and root_provenance.get("generation_timeout_seconds") == 180
        )
        paired_luna_design = (
            root_provenance.get("comparison_design")
            == "paired_same_luna_raw_vs_luna_plus_unslop"
            and root_provenance.get("arm_labels")
            == {
                "with_skill": "luna_plus_unslop",
                "without_skill": "raw_luna",
            }
        )
        baseline = next(run for run in predictions["runs"] if run["arm"] == "without_skill")
        normalized_offsets = baseline["findings"] == [
            {
                "start": issue["start"],
                "end": issue["end"],
                "text": issue["text"],
                "category": "generic opener",
                "rationale": "Formulaic opening.",
            }
        ]
        judge_prompts = {case_evidence[0]["judge"]["prompt"]}
        judge_blind = len(judge_prompts) == 1 and all(
            marker not in next(iter(judge_prompts)).lower()
            for marker in ("with_skill", "without_skill", "unslop")
        )
        judge_has_findings = any('"findings"' in prompt for prompt in judge_prompts)
        judge_has_gold_semantics = all(
            marker in next(iter(judge_prompts))
            for marker in ('"rationale"', '"policy"', "hard factual or safety issue")
        )
        judge_model = predictions.get("provenance", {}).get("judge_model")
        contract = predictions.get("shipping_contract", {})
        shipping_contract = bool(
            contract.get("resolved_sha256")
            and set(contract.get("components", {}))
            == {"references/core-contract.md"}
            and set(contract.get("behavior_sources", {}))
            == {
                "SKILL.md",
                "references/commands/rewrite.md",
                "presets/crisp-human.md",
            }
        )
        required_validation = {
            "preservation", "banned_phrase", "structure", "silhouette", "readability", "diff",
            "change_coverage", "attribution_preservation",
        }
        post_validation = all(
            required_validation <= set(case_evidence[0].get("validation", {}).get(arm, {}))
            for arm in ("with_skill", "without_skill")
        )
        change_coverage = (
            case_evidence[0]["validation"]["with_skill"]
            .get("change_coverage", {})
            .get("passed")
            is True
        )
        with_skill_prompt = case_evidence[0]["generation"]["with_skill"]["prompt"]
        baseline_prompt = case_evidence[0]["generation"]["without_skill"]["prompt"]
        source_diagnostics = (
            "SOURCE DIAGNOSTICS" in with_skill_prompt
            and '"structure"' in with_skill_prompt
            and '"silhouette"' in with_skill_prompt
            and '"readability"' in with_skill_prompt
            and '"constraints"' in with_skill_prompt
            and "SOURCE DIAGNOSTICS" not in baseline_prompt
        )
        contextual_audit_prompt = (
            "merge protocol" in with_skill_prompt.lower()
            and "a scanner match alone never authorizes an edit" in with_skill_prompt.lower()
            and "copy every sentence without a finding byte-for-byte" in with_skill_prompt.lower()
            and "MERGE PROTOCOL" not in baseline_prompt
            and with_skill_prompt.index("SOURCE START")
            < with_skill_prompt.index("SOURCE DIAGNOSTICS")
        )
        semantic_blind_pass = (
            "SCANNER-BLIND SOURCE-AUDIT FINDINGS" in with_skill_prompt
            and "SCANNER-BLIND SOURCE-AUDIT FINDINGS" not in baseline_prompt
            and predictions.get("provenance", {}).get("workflow")
            == "semantic_diagnose_rewrite_validate_retry"
        )
        isolated_calls = (
            predictions.get("provenance", {}).get("isolated_workspace") is True
            and predictions.get("provenance", {}).get("user_config_loaded") is False
            and predictions.get("provenance", {}).get("project_rules_loaded") is False
        )
        blocking_validation = bool(
            _validation_blockers(
                {
                    "preservation": {"passed": True, "warnings": []},
                    "banned_phrase": {"raw_result": []},
                    "structure": {"flags": [{"metric": "conclusion_coda"}]},
                    "silhouette": {"penalty": 0.0, "flags": []},
                    "readability": {"flags": []},
                    "change_coverage": {"passed": True},
                }
            )
        )
        soft_burstiness_advisory = not _validation_blockers(
            {
                "preservation": {"passed": True, "warnings": []},
                "banned_phrase": {"raw_result": []},
                "structure": {"flags": [{"metric": "sentence_burstiness"}]},
                "silhouette": {"penalty": 0.0, "flags": []},
                "readability": {"flags": []},
                "change_coverage": {"passed": True},
            }
        )
        preservation_warning_advisory = not _validation_blockers(
            {
                "preservation": {
                    "passed": True,
                    "warnings": ["Negation count dropped 2->1. Verify meaning."],
                },
                "banned_phrase": {"raw_result": []},
                "structure": {"flags": []},
                "silhouette": {"penalty": 0.0, "flags": []},
                "readability": {"flags": []},
                "change_coverage": {"passed": True},
            }
        )
        attribution_polarity_guard = (
            not _attribution_preservation(
                "The commander said every household received the order.",
                "The commander said not every household received the order.",
            )["passed"]
            and _attribution_preservation(
                "The commander said every household received the order.",
                "The commander said every household received the order. "
                "The radio log leaves 19 addresses unconfirmed.",
            )["passed"]
        )
        recommendation_attribution_guard = (
            not _attribution_preservation(
                "The certificate permits 60 C for two hours. "
                "The draft recommends running at 75 C for four hours.",
                "The certificate permits 60 C for two hours. "
                "Do not run at 75 C for four hours.",
            )["passed"]
            and _attribution_preservation(
                "The certificate permits 60 C for two hours. "
                "The draft recommends running at 75 C for four hours.",
                "The certificate permits 60 C for two hours. "
                "The draft recommends running at 75 C for four hours. "
                "Do not run at 75 C for four hours.",
            )["passed"]
            and _attribution_preservation(
                "With that said, the draft recommends repeating the cycle.",
                "The draft recommends repeating the cycle. "
                "Do not repeat the cycle.",
            )["passed"]
            and _attribution_preservation(
                "That sentence is untested, yet the draft recommends "
                "repeating the cycle.",
                "The draft recommends repeating the cycle. "
                "Do not repeat the cycle.",
            )["passed"]
        )
        attribution_actor_and_verb_guard = (
            not _attribution_preservation(
                "The commander said every household received the order.",
                "The commander did not say every household received the order.",
            )["passed"]
            and not _attribution_preservation(
                "The commander said every household received the order.",
                "The critic said every household received the order.",
            )["passed"]
            and not _attribution_preservation(
                "The commander said every household received the order.",
                "No one said every household received the order.",
            )["passed"]
            and not _attribution_preservation(
                "The commander, speaking by radio, said every household "
                "received the order.",
                "The critic said every household received the order.",
            )["passed"]
            and _attribution_preservation(
                "With that said, the controller directs traffic to port 8443.",
                "The controller routes traffic to port 8443.",
            )["passed"]
            and _attribution_preservation(
                "The gateway can route reads to v2, but writes must use v4.",
                "The gateway can route reads to v2, but writes must use v4.",
            )["passed"]
        )
        soft_silhouette_advisory = not _validation_blockers(
            {
                "preservation": {"passed": True, "warnings": []},
                "banned_phrase": {"raw_result": []},
                "structure": {"flags": []},
                "silhouette": {
                    "penalty": 2.668,
                    "flags": [
                        {
                            "metric": "preview_fulfillment",
                            "severity": "soft",
                        }
                    ],
                },
                "readability": {"flags": []},
                "change_coverage": {"passed": True},
            }
        )
        soft_silhouette_with_advisory_burstiness = not _validation_blockers(
            {
                "preservation": {"passed": True, "warnings": []},
                "attribution_preservation": {"passed": True},
                "banned_phrase": {"raw_result": []},
                "structure": {"flags": [{"metric": "sentence_burstiness"}]},
                "silhouette": {
                    "penalty": 1.0,
                    "flags": [
                        {"metric": "silhouette_penalty", "severity": "soft"}
                    ],
                },
                "readability": {"flags": []},
                "change_coverage": {"passed": True},
            }
        )
        reviewed_noop_advisory = (
            not _validation_blockers(
                {
                    "reviewed_noop": True,
                    "preservation": {"passed": True, "warnings": []},
                    "attribution_preservation": {"passed": True},
                    "change_coverage": {"passed": True},
                    "banned_phrase": {
                        "raw_result": [
                            {"severity": "hard", "category": "jargon", "phrase": "candidate"}
                        ]
                    },
                    "structure": {"flags": [{"metric": "sentence_burstiness"}]},
                    "silhouette": {
                        "penalty": 2.0,
                        "flags": [{"metric": "preview_fulfillment", "severity": "soft"}],
                    },
                    "readability": {"flags": []},
                }
            )
            and bool(
                _validation_blockers(
                    {
                        "reviewed_noop": False,
                        "preservation": {"passed": True, "warnings": []},
                        "attribution_preservation": {"passed": True},
                        "change_coverage": {"passed": True},
                        "banned_phrase": {
                            "raw_result": [
                                {"severity": "hard", "category": "jargon", "phrase": "candidate"}
                            ]
                        },
                        "structure": {"flags": []},
                        "silhouette": {"penalty": 0.0, "flags": []},
                        "readability": {"flags": []},
                    }
                )
            )
        )
        empty_findings_noop = _validate_generation(
            {"findings": [], "rewrite": "A needless stylistic edit."}, source
        )["rewrite"] == source
        clean_short_circuit = (
            not _needs_with_skill_generation(
                {"findings": [], "raw_result": []},
                [],
                {
                    "structure": {"flags": []},
                    "silhouette": {
                        "penalty": 1.2,
                        "flags": [{"metric": "preview_fulfillment", "severity": "soft"}],
                    },
                    "readability": {"flags": []},
                },
            )
            and _needs_with_skill_generation(
                {"findings": [], "raw_result": []},
                [{"start": 0, "end": 4, "text": "Test"}],
                {
                    "structure": {"flags": []},
                    "silhouette": {"penalty": 0.0, "flags": []},
                    "readability": {"flags": []},
                },
            )
            and _needs_with_skill_generation(
                {"findings": [], "raw_result": []},
                [],
                {
                    "structure": {"flags": [{"metric": "conclusion_coda"}]},
                    "silhouette": {"penalty": 0.0, "flags": []},
                    "readability": {"flags": []},
                },
            )
        )

        clean_source = "The steel bracket remained 6 mm from the hinge after the final inspection."
        clean_protected = _span(clean_source, "6 mm", "clean-good-1")
        clean_protected["policy"] = "Preserve the measured clearance exactly."
        clean_case = {
            "id": "runner-clean-fixture",
            "split": "tune",
            "genre": "technical",
            "register": "technical",
            "source": clean_source,
            "provenance": {"kind": "unit_fixture"},
            "issues": [],
            "protected_spans": [clean_protected],
            "constraints": [],
        }
        clean_judge = {
            "candidates": {
                label: {
                    "repairs": {},
                    "protections": {"clean-good-1": True},
                    "constraints": {},
                    "net_improved": False,
                }
                for label in ("candidate_a", "candidate_b")
            },
            "winner": "tie",
        }
        clean_manifest_path = temp / "clean-manifest.json"
        clean_responses_path = temp / "clean-responses.json"
        clean_predictions_path = temp / "clean-predictions.json"
        clean_manifest_path.write_text(
            json.dumps({"schema": "unslop-core-benchmark-v1", "cases": [clean_case]}),
            encoding="utf-8",
        )
        # Deliberately omit the with_skill generation. A clean diagnostic must
        # bypass the rewrite model rather than consuming this fixture response.
        clean_responses_path.write_text(
            json.dumps(
                {
                    "generations": {
                        clean_case["id"]: {
                            "without_skill": {"findings": [], "rewrite": clean_source}
                        }
                    },
                    "judges": {clean_case["id"]: clean_judge},
                }
            ),
            encoding="utf-8",
        )
        clean_proc = _run(
            [
                sys.executable,
                str(ROOT / "evals" / "core_runner.py"),
                str(clean_manifest_path),
                "--split",
                "tune",
                "--responses",
                str(clean_responses_path),
                "--out",
                str(clean_predictions_path),
            ]
        )
        clean_short_circuit = clean_short_circuit and clean_proc.returncode == 0
        if clean_proc.returncode == 0:
            clean_predictions = json.loads(clean_predictions_path.read_text(encoding="utf-8"))
            clean_run = next(
                row for row in clean_predictions["runs"] if row["arm"] == "with_skill"
            )
            clean_short_circuit = clean_short_circuit and (
                clean_run["rewrite"] == clean_source
                and clean_run["findings"] == []
                and clean_run["provenance"].get("generation_attempts") == 0
                and clean_run["provenance"].get("clean_short_circuit") is True
            )

        score_proc = _run(
            [
                sys.executable,
                str(ROOT / "evals" / "core_metrics.py"),
                str(manifest_path),
                str(predictions_path),
                "--split",
                "tune",
                "--allow-offline",
            ]
        )
        if score_proc.returncode:
            sys.stderr.write(score_proc.stderr)
            return score_proc.returncode

        holdback_case = dict(case)
        holdback_case["split"] = "holdback"
        manifest_path.write_text(
            json.dumps({"schema": "unslop-core-benchmark-v1", "cases": [holdback_case]}),
            encoding="utf-8",
        )
        sealed_env = dict(os.environ)
        sealed_env.pop("UNSLOP_CONFIRM_HOLDBACK", None)
        sealed = _run(
            [
                sys.executable,
                str(ROOT / "evals" / "core_runner.py"),
                str(manifest_path),
                "--split",
                "holdback",
                "--responses",
                str(responses_path),
            ],
            env=sealed_env,
        )
        holdback_sealed = sealed.returncode == 2 and "refusing to open holdback" in sealed.stderr

        second = json.loads(json.dumps(predictions))
        second["runs"] = [dict(run, case_id="runner-fixture-2") for run in second["runs"]]
        second["evidence"][0]["case_id"] = "runner-fixture-2"
        merged = _merge_case_results(
            [predictions, second], ["runner-fixture", "runner-fixture-2"], 2
        )
        parallel_case_merge = (
            [row["case_id"] for row in merged["evidence"]]
            == ["runner-fixture", "runner-fixture-2"]
            and len(merged["runs"]) == 4
            and merged["provenance"].get("case_workers") == 2
        )

    print("arms={} runs={}".format(",".join(arms), len(predictions["runs"])))
    print(
        "precision_first_contract={}".format(
            str(bool(precision_first_contract)).lower()
        )
    )
    print("raw_evidence={} provenance={}".format(str(bool(evidence_ok)).lower(), str(bool(provenance_ok)).lower()))
    print(
        "reproducible_provenance={}".format(
            str(bool(reproducible_provenance)).lower()
        )
    )
    print("paired_luna_design={}".format(str(bool(paired_luna_design)).lower()))
    print("judge_blind={}".format(str(bool(judge_blind)).lower()))
    print("normalized_offsets={}".format(str(bool(normalized_offsets)).lower()))
    print("repeated_offset_rejected={}".format(str(bool(repeated_offset_rejected)).lower()))
    print("decimal_sentence_coverage={}".format(str(bool(decimal_sentence_coverage)).lower()))
    print("separated_relational_evidence={}".format(str(bool(separated_relational_evidence)).lower()))
    print("cross_sentence_edit_span_rejected={}".format(str(bool(cross_sentence_edit_span_rejected)).lower()))
    print(
        "judge_model={} judge_has_findings={}".format(
            judge_model, str(bool(judge_has_findings)).lower()
        )
    )
    print("judge_has_gold_semantics={}".format(str(bool(judge_has_gold_semantics)).lower()))
    print(
        "shipping_contract={} post_validation={}".format(
            str(bool(shipping_contract)).lower(), str(bool(post_validation)).lower()
        )
    )
    print("source_diagnostics={}".format(str(bool(source_diagnostics)).lower()))
    print("contextual_audit_prompt={}".format(str(bool(contextual_audit_prompt)).lower()))
    print("change_coverage={}".format(str(bool(change_coverage)).lower()))
    print(
        "semantic_resolution_gate={}".format(
            str(bool(semantic_resolution_gate and adjacent_edit_not_resolution)).lower()
        )
    )
    print(
        "exact_edit_target={}".format(
            str(bool(
                same_sentence_actor_swap_blocked
                and same_sentence_evidence_mutation_blocked
                and cross_finding_evidence_overlap_rejected
            )).lower()
        )
    )
    print(
        "semantic_judgment_gate={}".format(
            str(bool(semantic_judgment_gate)).lower()
        )
    )
    print("paragraph_delete_coverage={}".format(
        str(bool(
            paragraph_delete_coverage
            and post_sentence_insertion_blocked
            and relational_evidence_stays_protected
            and relational_actor_preservation
            and adjacent_text_still_blocked
            and indented_code_still_blocked
            and list_continuation_still_blocked
        )).lower()
    ))
    print("semantic_blind_pass={}".format(str(bool(semantic_blind_pass)).lower()))
    print("isolated_calls={}".format(str(bool(isolated_calls)).lower()))
    print("blocking_validation={}".format(str(bool(blocking_validation)).lower()))
    print(
        "soft_burstiness_advisory={}".format(
            str(bool(soft_burstiness_advisory)).lower()
        )
    )
    print(
        "preservation_warning_advisory={}".format(
            str(bool(preservation_warning_advisory)).lower()
        )
    )
    print(
        "attribution_polarity_guard={}".format(
            str(bool(attribution_polarity_guard)).lower()
        )
    )
    print(
        "recommendation_attribution_guard={}".format(
            str(bool(recommendation_attribution_guard)).lower()
        )
    )
    print(
        "attribution_actor_and_verb_guard={}".format(
            str(bool(attribution_actor_and_verb_guard)).lower()
        )
    )
    print(
        "soft_silhouette_advisory={}".format(
            str(bool(soft_silhouette_advisory)).lower()
        )
    )
    print(
        "reviewed_noop_advisory={}".format(
            str(bool(reviewed_noop_advisory)).lower()
        )
    )
    print(
        "soft_silhouette_with_advisory_burstiness={}".format(
            str(bool(soft_silhouette_with_advisory_burstiness)).lower()
        )
    )
    print("empty_findings_noop={}".format(str(bool(empty_findings_noop)).lower()))
    print("clean_short_circuit={}".format(str(bool(clean_short_circuit)).lower()))
    print("canonical_evidence={}".format(str(bool(canonical_evidence)).lower()))
    print("holdback_sealed={}".format(str(bool(holdback_sealed)).lower()))
    print("parallel_case_merge={}".format(str(bool(parallel_case_merge)).lower()))
    return 0 if (
        evidence_ok
        and precision_first_contract
        and provenance_ok
        and reproducible_provenance
        and paired_luna_design
        and judge_blind
        and normalized_offsets
        and repeated_offset_rejected
        and decimal_sentence_coverage
        and separated_relational_evidence
        and cross_sentence_edit_span_rejected
        and judge_model == "gpt-5.6-sol"
        and not judge_has_findings
        and judge_has_gold_semantics
        and shipping_contract
        and post_validation
        and source_diagnostics
        and contextual_audit_prompt
        and change_coverage
        and semantic_resolution_gate
        and adjacent_edit_not_resolution
        and same_sentence_actor_swap_blocked
        and same_sentence_evidence_mutation_blocked
        and cross_finding_evidence_overlap_rejected
        and semantic_judgment_gate
        and paragraph_delete_coverage
        and post_sentence_insertion_blocked
        and relational_evidence_stays_protected
        and relational_actor_preservation
        and adjacent_text_still_blocked
        and indented_code_still_blocked
        and list_continuation_still_blocked
        and semantic_blind_pass
        and isolated_calls
        and blocking_validation
        and soft_burstiness_advisory
        and preservation_warning_advisory
        and attribution_polarity_guard
        and recommendation_attribution_guard
        and attribution_actor_and_verb_guard
        and soft_silhouette_advisory
        and soft_silhouette_with_advisory_burstiness
        and reviewed_noop_advisory
        and empty_findings_noop
        and clean_short_circuit
        and canonical_evidence
        and holdback_sealed
        and parallel_case_merge
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
