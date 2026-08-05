#!/usr/bin/env python3
"""Reproduce the bounded GEPA search for UNSLOP's repository check profile.

Run without installing GEPA permanently:

    UNSLOP_BASE_PATH="$PATH" uv run --with gepa==0.1.4 \
      python evals/optimize_check_profile.py --output evals/gepa-check-profile.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

from _check_support import ROOT


GEPA_VERSION = "0.1.4"
MAX_CANDIDATE_PROPOSALS = 2
MAX_METRIC_CALLS = 10
ARTIFACT = Path("evals/gepa-check-profile.json")
REQUIRED = {"canonical-full"}
PROFILES = {
    "existing-ci": {
        "phases": [
            "canonical-full", "maintenance-repeat", "scanner-repeat",
            "preservation-repeat", "complexity-repeat", "shared-repeat",
            "leakage-repeat",
        ],
        "behavioral_cache_mode": "off",
    },
    "missing-leakage": {
        "phases": ["product-maintenance-only"],
        "behavioral_cache_mode": "read-write",
    },
    "canonical": {
        "phases": ["canonical-full"],
        "behavioral_cache_mode": "read-write",
    },
}
TUNE_GENERATION_CASES = 12
TUNE_JUDGE_ASSERTIONS = 12


def behavioral_model_calls(profile_name: str) -> int:
    """Return calls for one tune iteration under the candidate cache policy."""
    mode = PROFILES[profile_name]["behavioral_cache_mode"]
    if mode == "off":
        return 2 * (TUNE_GENERATION_CASES + TUNE_JUDGE_ASSERTIONS)
    if mode == "read-write":
        # A warmed baseline reuses without_skill generation and judge work.
        return TUNE_GENERATION_CASES + TUNE_JUDGE_ASSERTIONS
    raise ValueError(f"unknown behavioral cache mode: {mode}")


def _commands(*commands: list[str]) -> list[list[str]]:
    return list(commands)


PHASES = {
    "canonical-full": _commands(["python3", "evals/check.py", "--full"]),
    "product-maintenance-only": _commands(
        ["python3", "evals/check.py"],
        ["python3", "evals/check.py", "--maintenance"],
    ),
    "maintenance-repeat": _commands(["python3", "evals/check.py", "--maintenance"]),
    "scanner-repeat": _commands(["python3", "evals/check_scanner_contract.py"]),
    "preservation-repeat": _commands(["python3", "evals/check_preservation_contract.py"]),
    "complexity-repeat": _commands(["python3", "evals/check_complexity_budget.py"]),
    "shared-repeat": _commands(["python3", "evals/build_shared_benchmark.py", "--check"]),
    "leakage-repeat": _commands(
        ["skill-benchmark", "validate", "evals/shared-benchmark.json", "--strict-leakage"]
    ),
}


def artifact_valid(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    config = data.get("config", {})
    attempts = data.get("attempts")
    accepted = data.get("accepted_candidates")
    aggregates = data.get("aggregate_scores")
    if not (
        data.get("schema") == 1
        and data.get("gepa_version") == GEPA_VERSION
        and config.get("profiles") == PROFILES
        and config.get("phase_commands") == PHASES
        and config.get("tune_generation_cases") == TUNE_GENERATION_CASES
        and config.get("tune_judge_assertions") == TUNE_JUDGE_ASSERTIONS
        and config.get("max_candidate_proposals") == MAX_CANDIDATE_PROPOSALS
        and config.get("max_metric_calls") == MAX_METRIC_CALLS
        and isinstance(data.get("total_metric_calls"), int)
        and 0 < data["total_metric_calls"] <= MAX_METRIC_CALLS
        and isinstance(attempts, list)
        and {item.get("profile") for item in attempts if isinstance(item, dict)}
        == set(PROFILES)
        and isinstance(accepted, list)
        and isinstance(aggregates, list)
        and isinstance(data.get("objective_scores"), list)
        and len(data["objective_scores"]) == len(accepted)
        and len(accepted) == len(aggregates) > 0
        and all(name in PROFILES for name in accepted)
        and all(isinstance(score, (int, float)) for score in aggregates)
    ):
        return False
    score_keys = {
        "correctness", "runtime", "model_calls", "command_tokens", "simplicity"
    }
    for attempt in attempts:
        scores = attempt.get("scores")
        if not (
            isinstance(attempt.get("correct"), bool)
            and isinstance(scores, dict)
            and set(scores) == score_keys
            and all(isinstance(score, (int, float)) and score >= 0 for score in scores.values())
        ):
            return False
        if attempt["correct"]:
            samples = attempt.get("samples")
            if not (
                isinstance(samples, list)
                and samples
                and all(isinstance(sample, (int, float)) and sample > 0 for sample in samples)
                and attempt.get("seconds") == statistics.median(samples)
                and attempt.get("failures") == []
                and attempt["scores"]["correctness"] == 1.0
                and attempt.get("phases")
                == len(PROFILES[attempt["profile"]]["phases"])
                and attempt.get("model_calls")
                == behavioral_model_calls(attempt["profile"])
            ):
                return False
        else:
            if attempt["scores"]["correctness"] != 0.0:
                return False
            if attempt["profile"] == "missing-leakage" and not (
                attempt.get("missing") == ["canonical-full"]
                and all(score == 0.0 for score in attempt["scores"].values())
            ):
                return False
    for index, objective in enumerate(data["objective_scores"]):
        if not (
            isinstance(objective, dict)
            and set(objective) == score_keys
            and all(isinstance(score, (int, float)) for score in objective.values())
            and math.isclose(aggregates[index], sum(objective.values()))
            and any(
                item.get("profile") == accepted[index]
                and item.get("correct")
                and item.get("scores") == objective
                for item in attempts
            )
        ):
            return False
    best_index = max(range(len(aggregates)), key=aggregates.__getitem__)
    return (
        data.get("selected") == accepted[best_index]
        and any(
            item.get("profile") == data["selected"] and item.get("correct")
            for item in attempts
        )
    )


def manifest() -> dict:
    return {
        "gepa_version": GEPA_VERSION,
        "candidate_count": len(PROFILES),
        "max_candidate_proposals": MAX_CANDIDATE_PROPOSALS,
        "max_metric_calls": MAX_METRIC_CALLS,
        "required": sorted(REQUIRED),
        "profiles": PROFILES,
        "phase_commands": PHASES,
        "tune_generation_cases": TUNE_GENERATION_CASES,
        "tune_judge_assertions": TUNE_JUDGE_ASSERTIONS,
        "artifact": str(ARTIFACT),
        "artifact_valid": (
            os.environ.get("UNSLOP_GEPA_REGENERATING") == "1"
            or artifact_valid(ROOT / ARTIFACT)
        ),
    }


def run_search(output: Path, samples: int) -> None:
    from gepa.optimize_anything import EngineConfig, GEPAConfig, ReflectionConfig, optimize_anything

    attempts: list[dict] = []
    baseline: dict[str, float] = {}
    base_path = os.environ.get("UNSLOP_BASE_PATH", os.environ["PATH"])
    env = dict(os.environ, PATH=base_path, UNSLOP_GEPA_REGENERATING="1")

    def evaluate(profile_name: str):
        phase_ids = PROFILES[profile_name]["phases"]
        missing = sorted(REQUIRED - set(phase_ids))
        if missing:
            info = {"profile": profile_name, "correct": False, "missing": missing,
                    "scores": {"correctness": 0.0, "runtime": 0.0, "model_calls": 0.0,
                               "command_tokens": 0.0, "simplicity": 0.0}}
            attempts.append(info)
            return 0.0, info

        durations = []
        failures = []
        for _ in range(samples):
            started = time.perf_counter()
            current = []
            correct = True
            for phase_id in phase_ids:
                for command in PHASES[phase_id]:
                    proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
                    current.append({"phase": phase_id, "command": command, "returncode": proc.returncode})
                    if proc.returncode:
                        correct = False
                        break
                if not correct:
                    break
            durations.append(time.perf_counter() - started)
            failures = [item for item in current if item["returncode"]]
            if not correct:
                break

        runtime = statistics.median(durations)
        command_tokens = sum(len(command) for phase_id in phase_ids for command in PHASES[phase_id])
        if profile_name == "existing-ci":
            baseline.update(
                runtime=runtime,
                model_calls=behavioral_model_calls(profile_name),
                command_tokens=command_tokens,
                phases=len(phase_ids),
            )
        correctness = 0.0 if failures else 1.0
        scores = {
            "correctness": correctness,
            "runtime": baseline.get("runtime", runtime) / runtime,
            "model_calls": baseline.get(
                "model_calls", behavioral_model_calls(profile_name)
            ) / behavioral_model_calls(profile_name),
            "command_tokens": baseline.get("command_tokens", command_tokens) / command_tokens,
            "simplicity": baseline.get("phases", len(phase_ids)) / len(phase_ids),
        }
        aggregate = sum(scores.values()) if correctness else 0.0
        info = {"profile": profile_name, "correct": bool(correctness), "seconds": runtime,
                "samples": durations, "phases": len(phase_ids),
                "model_calls": behavioral_model_calls(profile_name),
                "command_tokens": command_tokens,
                "failures": failures, "scores": scores}
        attempts.append(info)
        return aggregate, info

    queue = ["missing-leakage", "canonical"]

    def propose(candidate, reflective_dataset, components_to_update):
        del candidate, reflective_dataset
        return {components_to_update[0]: queue.pop(0)}

    config = GEPAConfig(
        engine=EngineConfig(seed=0, parallel=False, display_progress_bar=False,
                            max_candidate_proposals=MAX_CANDIDATE_PROPOSALS,
                            max_metric_calls=MAX_METRIC_CALLS),
        reflection=ReflectionConfig(custom_candidate_proposer=propose, reflection_lm=None),
    )
    result = optimize_anything(
        "existing-ci",
        evaluator=evaluate,
        objective="Preserve all hard gates while minimizing runtime, model calls, command tokens, and phases.",
        config=config,
    )
    best_index = max(range(len(result.val_aggregate_scores)), key=result.val_aggregate_scores.__getitem__)
    selected = result.candidates[best_index]["current_candidate"]
    config_record = manifest()
    # The artifact is validated immediately after the atomic search result is
    # written. Recording true here avoids making the artifact's provenance
    # depend on whatever older artifact happened to exist before regeneration.
    config_record["artifact_valid"] = True
    config_record["samples"] = samples
    payload = {
        "schema": 1,
        "gepa_version": GEPA_VERSION,
        "config": config_record,
        "attempts": attempts,
        "accepted_candidates": [item["current_candidate"] for item in result.candidates],
        "aggregate_scores": result.val_aggregate_scores,
        "objective_scores": result.val_aggregate_subscores,
        "selected": selected,
        "total_metric_calls": result.total_metric_calls,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not artifact_valid(output):
        raise RuntimeError(f"generated artifact failed validation: {output}")
    print(f"selected={selected} artifact={output}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--samples", type=int, default=1)
    args = parser.parse_args(argv)
    if args.list:
        print(json.dumps(manifest(), indent=2, sort_keys=True))
        return 0 if manifest()["artifact_valid"] else 1
    if not args.output:
        parser.error("provide --list or --output PATH")
    if args.samples < 1:
        parser.error("--samples must be at least 1")
    run_search(args.output, args.samples)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
