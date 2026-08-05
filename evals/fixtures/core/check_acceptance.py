#!/usr/bin/env python3
"""Exercise the frozen core acceptance gate with valid and forged inputs."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evals"))

from core_acceptance import (  # noqa: E402
    AcceptanceError,
    _verify_efficiency,
    main as core_acceptance_main,
)
from core_metrics import main as core_metrics_main  # noqa: E402
from core_runner import (  # noqa: E402
    VALIDATION_STACK_PATHS,
    _blind_map,
    _shipping_contract,
    _validation_stack_sha256,
    main as core_runner_main,
)


def _span(source: str, text: str, span_id: str, category: str) -> dict:
    start = source.index(text)
    return {
        "id": span_id,
        "start": start,
        "end": start + len(text),
        "text": text,
        "category": category,
        "rationale": "Generic opener delays the technical fact.",
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    entrypoints = {
        str(ROOT / "evals" / "core_runner.py"): core_runner_main,
        str(ROOT / "evals" / "core_metrics.py"): core_metrics_main,
        str(ROOT / "evals" / "core_acceptance.py"): core_acceptance_main,
    }
    entrypoint = entrypoints.get(command[1]) if len(command) > 1 else None
    if entrypoint is None:
        return subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        returncode = entrypoint(command[2:])
    return subprocess.CompletedProcess(
        command, returncode, stdout.getvalue(), stderr.getvalue()
    )


def main() -> int:
    try:
        _verify_efficiency(
            {
                "operational": {
                    "with_skill_runs": 2,
                    "model_calls": 15,
                    "uncached_input_tokens": 150,
                    "output_tokens": 15,
                    "elapsed_seconds": 3.0,
                    "by_case": {
                        "case-a": {
                            "model_calls": 14,
                            "uncached_input_tokens": 140,
                            "output_tokens": 14,
                            "elapsed_seconds": 2.5,
                        },
                        "case-b": {
                            "model_calls": 1,
                            "uncached_input_tokens": 10,
                            "output_tokens": 1,
                            "elapsed_seconds": 0.5,
                        },
                    },
                }
            },
            {
                "efficiency": {
                    "maximum_model_calls_per_case": 10,
                    "maximum_uncached_input_tokens_per_case": 100,
                    "maximum_output_tokens_per_case": 10,
                    "maximum_elapsed_seconds_per_case": 2.0,
                }
            },
        )
        individual_case_budget_rejected = False
    except AcceptanceError:
        individual_case_budget_rejected = True
    try:
        _verify_efficiency(
            {
                "operational": {
                    "with_skill_runs": 2,
                    "model_calls": 2,
                    "uncached_input_tokens": 20,
                    "output_tokens": 2,
                    "elapsed_seconds": 3.0,
                    "by_case": {
                        "case-a": {
                            "model_calls": 1,
                            "uncached_input_tokens": 10,
                            "output_tokens": 1,
                            "elapsed_seconds": 2.5,
                        },
                        "case-b": {
                            "model_calls": 1,
                            "uncached_input_tokens": 10,
                            "output_tokens": 1,
                            "elapsed_seconds": 0.5,
                        },
                    },
                }
            },
            {
                "efficiency": {
                    "maximum_model_calls_per_case": 1,
                    "maximum_uncached_input_tokens_per_case": 10,
                    "maximum_output_tokens_per_case": 1,
                    "maximum_elapsed_seconds_per_case": 2.0,
                }
            },
        )
        individual_elapsed_budget_rejected = False
    except AcceptanceError:
        individual_elapsed_budget_rejected = True
    source = "Here's the thing: the API returns 200 on success."
    # Include the minimum boundary word required to remove the opener while
    # preserving exact edit authorization: the rewrite must capitalize "the".
    issue = _span(source, "Here's the thing: the", "issue-1", "throat_clearing")
    protected = _span(source, "API returns 200 on success.", "good-1", "good_prose")
    protected.pop("category")
    protected["policy"] = "Preserve the API status fact and wording."
    case = {
        "id": "acceptance-fixture",
        "split": "holdout",
        "genre": "technical",
        "register": "technical",
        "source": source,
        "provenance": {"kind": "unit_fixture"},
        "issues": [issue],
        "protected_spans": [protected],
        "constraints": [{"id": "constraint-1", "description": "Keep 200."}],
    }
    clean_case = {
        "id": "acceptance-clean",
        "split": "holdout",
        "genre": "technical",
        "register": "technical",
        "source": "The API returns 204 when the queue is empty.",
        "provenance": {"kind": "unit_fixture"},
        "issues": [],
        "protected_spans": [],
        "constraints": [],
    }
    finding = {
        "start": issue["start"],
        "end": issue["end"],
        "text": issue["text"],
        "category": issue["category"],
        "rationale": issue["rationale"],
    }
    with_skill = {
        "findings": [finding],
        "rewrite": "The API returns 200 on success.",
    }
    without_skill = {"findings": [], "rewrite": source}
    blind_map = _blind_map(case["id"], randomize=False)
    winner = next(label for label, arm in blind_map.items() if arm == "with_skill")
    loser = next(label for label, arm in blind_map.items() if arm == "without_skill")
    candidate = {
        "repairs": {"issue-1": True},
        "protections": {"good-1": True},
        "constraints": {"constraint-1": True},
        "net_improved": True,
    }
    baseline_candidate = {
        "repairs": {"issue-1": False},
        "protections": {"good-1": True},
        "constraints": {"constraint-1": True},
        "net_improved": False,
    }
    responses = {
        "generations": {
            case["id"]: {"with_skill": with_skill, "without_skill": without_skill},
            clean_case["id"]: {
                "with_skill": {"findings": [], "rewrite": clean_case["source"]},
                "without_skill": {"findings": [], "rewrite": clean_case["source"]},
            },
        },
        "judges": {
            case["id"]: {
                "candidates": {winner: candidate, loser: baseline_candidate},
                "winner": winner,
            },
            clean_case["id"]: {
                "candidates": {
                    "candidate_a": {
                        "repairs": {},
                        "protections": {},
                        "constraints": {},
                        "net_improved": False,
                    },
                    "candidate_b": {
                        "repairs": {},
                        "protections": {},
                        "constraints": {},
                        "net_improved": False,
                    },
                },
                "winner": "tie",
            },
        },
    }

    with tempfile.TemporaryDirectory(prefix="unslop_core_acceptance_") as raw:
        temp = Path(raw)
        manifest_path = temp / "core-holdout-v7.json"
        responses_path = temp / "responses.json"
        predictions_path = temp / "predictions.json"
        results_path = temp / "results.json"
        thresholds_path = temp / "thresholds.json"
        protocol_path = temp / "CORE-V7-PROTOCOL.md"
        protocol_path.write_text("# Frozen acceptance protocol\n", encoding="utf-8")
        manifest_path.write_text(
            json.dumps(
                {
                    "schema": "unslop-core-benchmark-v1",
                    "required_arms": ["with_skill", "without_skill"],
                    "cases": [case, clean_case],
                }
            ),
            encoding="utf-8",
        )
        responses_path.write_text(json.dumps(responses), encoding="utf-8")
        generated = _run(
            [
                sys.executable,
                str(ROOT / "evals" / "core_runner.py"),
                str(manifest_path),
                "--split",
                "holdout",
                "--responses",
                str(responses_path),
                "--out",
                str(predictions_path),
            ]
        )
        if generated.returncode:
            sys.stderr.write(generated.stderr)
            return generated.returncode
        scored = _run(
            [
                sys.executable,
                str(ROOT / "evals" / "core_metrics.py"),
                str(manifest_path),
                str(predictions_path),
                "--split",
                "holdout",
                "--allow-offline",
                "--out",
                str(results_path),
            ]
        )
        if scored.returncode:
            sys.stderr.write(scored.stderr)
            return scored.returncode

        contract = _shipping_contract()
        thresholds = {
            "schema": "unslop-core-thresholds-v1",
            "frozen_inputs": {
                "public_holdout_v7_sha256": _sha256(manifest_path),
                "shipping_contract_sha256": contract["resolved_sha256"],
                "core_runner_sha256": _sha256(ROOT / "evals" / "core_runner.py"),
                "core_metrics_sha256": _sha256(ROOT / "evals" / "core_metrics.py"),
                "core_acceptance_sha256": _sha256(
                    ROOT / "evals" / "core_acceptance.py"
                ),
                "protocol_path": str(protocol_path),
                "protocol_sha256": _sha256(protocol_path),
                "model_adapter_source_sha256": _sha256(
                    ROOT / "evals" / "model_generate.py"
                ),
                "validation_stack_sha256": _validation_stack_sha256(),
                "scanner_sha256": _sha256(ROOT / "scripts" / "banned_phrase_scan.py"),
            },
            "with_skill": {
                "minimum_detection_precision": 0.9,
                "minimum_detection_recall": 0.9,
                "minimum_raw_detection_precision": 0.0,
                "minimum_raw_detection_recall": 0.0,
                "minimum_repair_success": 0.9,
                "minimum_preservation": 1.0,
                "maximum_damage_rate": 0.0,
                "maximum_safe_fallback_rate": 0.0,
                "minimum_net_improvement": 0.8,
                "minimum_clean_noop_rate": 1.0,
            },
            "comparison": {
                "minimum_paired_win_rate": 0.5,
                "maximum_without_skill_wins": 0,
                "minimum_positive_quality_lifts": 1,
                "quality_lifts": [
                    "detection_precision",
                    "detection_recall",
                    "repair_success",
                    "preservation",
                    "damage_rate_inverse",
                    "net_improvement",
                    "clean_noop_rate",
                ],
            },
            "efficiency": {
                "maximum_model_calls_per_case": 10,
                "maximum_uncached_input_tokens_per_case": 50000,
                "maximum_output_tokens_per_case": 10000,
                "maximum_elapsed_seconds_per_case": 300,
            },
            "required_controls": {
                "generation_model_both_arms": "gpt-5.6-luna",
                "independent_blinded_judge": "gpt-5.6-sol",
                "isolated_model_workspaces": True,
                "paired_comparison": "raw_luna_vs_luna_plus_unslop",
            },
        }
        thresholds_path.write_text(json.dumps(thresholds), encoding="utf-8")
        gate_command = [
            sys.executable,
            str(ROOT / "evals" / "core_acceptance.py"),
            str(manifest_path),
            str(predictions_path),
            str(results_path),
            "--thresholds",
            str(thresholds_path),
            "--split",
            "holdout",
            "--allow-offline",
        ]
        valid = _run(gate_command)
        if valid.returncode:
            sys.stderr.write(valid.stderr)

        hash_mutations_rejected = True
        for frozen_key in (
            key for key in thresholds["frozen_inputs"] if key.endswith("_sha256")
        ):
            mutated = copy.deepcopy(thresholds)
            mutated["frozen_inputs"][frozen_key] = "0" * 64
            thresholds_path.write_text(json.dumps(mutated), encoding="utf-8")
            hash_mutations_rejected = hash_mutations_rejected and _run(
                gate_command
            ).returncode == 2

        controls = json.loads(predictions_path.read_text(encoding="utf-8"))
        controls["provenance"]["model"] = "claude"
        predictions_path.write_text(json.dumps(controls), encoding="utf-8")
        thresholds_path.write_text(json.dumps(thresholds), encoding="utf-8")
        control_mutation = _run(gate_command)

        controls["provenance"]["model"] = "gpt-5.6-luna"
        controls["provenance"]["comparison_design"] = "unpaired"
        predictions_path.write_text(json.dumps(controls), encoding="utf-8")
        paired_design_mutation = _run(gate_command)

        controls["provenance"]["comparison_design"] = (
            "paired_same_luna_raw_vs_luna_plus_unslop"
        )
        predictions_path.write_text(json.dumps(controls), encoding="utf-8")
        inefficient = copy.deepcopy(thresholds)
        inefficient["efficiency"]["maximum_model_calls_per_case"] = -1
        thresholds_path.write_text(json.dumps(inefficient), encoding="utf-8")
        efficiency_mutation = _run(gate_command)

        raw_detection = copy.deepcopy(thresholds)
        raw_detection["with_skill"]["minimum_raw_detection_recall"] = 1.0
        thresholds_path.write_text(json.dumps(raw_detection), encoding="utf-8")
        raw_detection_mutation = _run(gate_command)

        stack_root = temp / "validation-stack"
        for relative in VALIDATION_STACK_PATHS:
            source_path = ROOT / relative
            destination = stack_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source_path.read_bytes())
        stack_before = _validation_stack_sha256(stack_root)
        drift_target = stack_root / VALIDATION_STACK_PATHS[0]
        drift_target.write_bytes(drift_target.read_bytes() + b"\n# fixture drift\n")
        validation_stack_drift_rejected = (
            stack_before != _validation_stack_sha256(stack_root)
        )

    valid_ok = valid.returncode == 0
    controls_rejected = control_mutation.returncode == 2
    paired_design_rejected = paired_design_mutation.returncode == 2
    efficiency_rejected = efficiency_mutation.returncode == 2
    raw_detection_rejected = raw_detection_mutation.returncode == 2
    print(f"valid_acceptance={'accepted' if valid_ok else 'rejected'}")
    print(
        "mutated_frozen_hash={}".format(
            "rejected" if hash_mutations_rejected else "accepted"
        )
    )
    print(f"mutated_model_control={'rejected' if controls_rejected else 'accepted'}")
    print(
        "mutated_paired_design={}".format(
            "rejected" if paired_design_rejected else "accepted"
        )
    )
    print("model_adapter_frozen=true")
    print(
        "validation_stack_drift={}".format(
            "rejected" if validation_stack_drift_rejected else "accepted"
        )
    )
    print(
        "efficiency_budget={}".format(
            "rejected" if efficiency_rejected else "accepted"
        )
    )
    print(
        "individual_case_budget={}".format(
            "rejected" if individual_case_budget_rejected else "accepted"
        )
    )
    print(
        "individual_elapsed_budget={}".format(
            "rejected" if individual_elapsed_budget_rejected else "accepted"
        )
    )
    print(
        "raw_detection_gate={}".format(
            "rejected" if raw_detection_rejected else "accepted"
        )
    )
    return 0 if (
        valid_ok
        and hash_mutations_rejected
        and controls_rejected
        and paired_design_rejected
        and validation_stack_drift_rejected
        and efficiency_rejected
        and individual_case_budget_rejected
        and individual_elapsed_budget_rejected
        and raw_detection_rejected
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
