#!/usr/bin/env python3
"""Offline contract test for the end-to-end core benchmark runner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evals"))

from core_runner import (  # noqa: E402
    _attribution_preservation,
    _validate_generation,
    _validation_blockers,
)


def _span(source: str, text: str, span_id: str, category: str | None = None) -> dict:
    start = source.index(text)
    row = {"id": span_id, "start": start, "end": start + len(text), "text": text}
    if category:
        row["category"] = category
    return row


def _run(command: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, env=env)


def main() -> int:
    source = "Here's the thing: the API returns 200 on success, while Section 4 remains unchanged."
    issue = _span(source, "Here's the thing:", "issue-1", "throat_clearing")
    protected = _span(source, "the API returns 200 on success", "good-1")
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
            "rewrite": "The API returns 200 on success, while Section 4 remains unchanged.",
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
            and run.get("provenance", {}).get("generation_prompt_sha256")
            and run.get("provenance", {}).get("judge_prompt_sha256")
            for run in predictions["runs"]
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
            == {"SKILL.md", "references/commands/rewrite.md", "presets/crisp-human.md"}
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
            "CONTEXTUAL AUDIT PRIORITY" in with_skill_prompt
            and "copy every sentence without a finding byte-for-byte" in with_skill_prompt
            and "CONTEXTUAL AUDIT PRIORITY" not in baseline_prompt
            and with_skill_prompt.index("SOURCE START")
            < with_skill_prompt.index("SOURCE DIAGNOSTICS")
        )
        semantic_blind_pass = (
            "SCANNER-BLIND SEMANTIC FINDINGS" in with_skill_prompt
            and "SCANNER-BLIND SEMANTIC FINDINGS" not in baseline_prompt
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
        empty_findings_noop = _validate_generation(
            {"findings": [], "rewrite": "A needless stylistic edit."}, source
        )["rewrite"] == source

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

    print("arms={} runs={}".format(",".join(arms), len(predictions["runs"])))
    print("raw_evidence={} provenance={}".format(str(bool(evidence_ok)).lower(), str(bool(provenance_ok)).lower()))
    print("judge_blind={}".format(str(bool(judge_blind)).lower()))
    print("normalized_offsets={}".format(str(bool(normalized_offsets)).lower()))
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
        "soft_silhouette_advisory={}".format(
            str(bool(soft_silhouette_advisory)).lower()
        )
    )
    print("empty_findings_noop={}".format(str(bool(empty_findings_noop)).lower()))
    print("canonical_evidence={}".format(str(bool(canonical_evidence)).lower()))
    print("holdback_sealed={}".format(str(bool(holdback_sealed)).lower()))
    return 0 if (
        evidence_ok
        and provenance_ok
        and judge_blind
        and normalized_offsets
        and judge_model == "gpt-5.6-sol"
        and not judge_has_findings
        and judge_has_gold_semantics
        and shipping_contract
        and post_validation
        and source_diagnostics
        and contextual_audit_prompt
        and change_coverage
        and semantic_blind_pass
        and isolated_calls
        and blocking_validation
        and soft_burstiness_advisory
        and preservation_warning_advisory
        and attribution_polarity_guard
        and soft_silhouette_advisory
        and empty_findings_noop
        and canonical_evidence
        and holdback_sealed
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
