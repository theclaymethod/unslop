#!/usr/bin/env python3
"""Exercise the frozen core acceptance gate with valid and forged inputs."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evals"))

from core_runner import _blind_map, _shipping_contract  # noqa: E402


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
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True)


def main() -> int:
    source = "Here's the thing: the API returns 200 on success."
    issue = _span(source, "Here's the thing:", "issue-1", "throat_clearing")
    protected = _span(source, "the API returns 200 on success.", "good-1", "good_prose")
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
                "scanner_sha256": _sha256(ROOT / "scripts" / "banned_phrase_scan.py"),
            },
            "with_skill": {
                "minimum_detection_precision": 0.9,
                "minimum_detection_recall": 0.9,
                "minimum_repair_success": 0.9,
                "minimum_preservation": 1.0,
                "maximum_damage_rate": 0.0,
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
            "required_controls": {
                "generation_model_both_arms": "gpt-5.6-luna",
                "independent_blinded_judge": "gpt-5.6-sol",
                "isolated_model_workspaces": True,
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
        for frozen_key in thresholds["frozen_inputs"]:
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

    valid_ok = valid.returncode == 0
    controls_rejected = control_mutation.returncode == 2
    print(f"valid_acceptance={'accepted' if valid_ok else 'rejected'}")
    print(
        "mutated_frozen_hash={}".format(
            "rejected" if hash_mutations_rejected else "accepted"
        )
    )
    print(f"mutated_model_control={'rejected' if controls_rejected else 'accepted'}")
    return 0 if valid_ok and hash_mutations_rejected and controls_rejected else 1


if __name__ == "__main__":
    raise SystemExit(main())
