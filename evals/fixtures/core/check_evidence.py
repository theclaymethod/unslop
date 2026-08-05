#!/usr/bin/env python3
"""Prove that core scoring is bound to raw runner evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evals"))

from core_runner import _retry_directives, _retry_prompt  # noqa: E402


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True)


def span(source: str, text: str, span_id: str, category: str | None = None) -> dict:
    start = source.index(text)
    row = {"id": span_id, "start": start, "end": start + len(text), "text": text}
    if category:
        row["category"] = category
    return row


def main() -> int:
    source = "Here's the thing: the API returns 200 on success."
    issue = span(source, "Here's the thing:", "issue-1", "throat_clearing")
    protected = span(source, "the API returns 200 on success.", "good-1")
    manifest = {
        "schema": "unslop-core-benchmark-v1",
        "cases": [{
            "id": "evidence-fixture",
            "split": "tune",
            "source": source,
            "issues": [issue],
            "protected_spans": [protected],
            "constraints": [{"id": "constraint-1", "mode": "preserve", "text": "Keep 200."}],
        }],
    }
    finding = {
        "start": issue["start"],
        "end": issue["end"],
        "text": issue["text"],
        "category": issue["category"],
        "rationale": "Generic opener.",
    }
    rewrite = "The API returns 200 on success."
    generations = {
        arm: {"findings": [finding], "rewrite": rewrite}
        for arm in ("with_skill", "without_skill")
    }
    candidate = {
        "repairs": {"issue-1": True},
        "protections": {"good-1": True},
        "constraints": {"constraint-1": True},
        "net_improved": True,
    }
    responses = {
        "generations": {"evidence-fixture": generations},
        "judges": {"evidence-fixture": {
            "candidates": {"candidate_a": candidate, "candidate_b": candidate},
            "winner": "tie",
        }},
    }

    with tempfile.TemporaryDirectory(prefix="unslop_core_evidence_") as raw:
        temp = Path(raw)
        manifest_path = temp / "manifest.json"
        responses_path = temp / "responses.json"
        valid_path = temp / "valid.json"
        forged_path = temp / "forged.json"
        retry_path = temp / "retry.json"
        correlated_rewrite_path = temp / "correlated-rewrite.json"
        correlated_findings_path = temp / "correlated-findings.json"
        tool_event_path = temp / "tool-event.json"
        stale_manifest_path = temp / "stale-manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        responses_path.write_text(json.dumps(responses), encoding="utf-8")
        generated = run([
            sys.executable,
            str(ROOT / "evals" / "core_runner.py"),
            str(manifest_path),
            "--split", "tune",
            "--responses", str(responses_path),
            "--out", str(valid_path),
        ])
        if generated.returncode:
            sys.stderr.write(generated.stderr)
            return generated.returncode

        score_command = [
            sys.executable,
            str(ROOT / "evals" / "core_metrics.py"),
            str(manifest_path),
            str(valid_path),
            "--split", "tune",
            "--allow-offline",
        ]
        valid = run(score_command)
        if valid.returncode:
            sys.stderr.write(valid.stderr)

        retry = json.loads(valid_path.read_text(encoding="utf-8"))
        retry_generation = retry["evidence"][0]["generation"]["with_skill"]
        first_attempt = copy.deepcopy(retry_generation)
        first_validation = copy.deepcopy(
            retry["evidence"][0]["validation"]["with_skill"]
        )
        first_validation["preservation"]["passed"] = False
        first_attempt["validation"] = first_validation
        final_validation = copy.deepcopy(
            retry["evidence"][0]["validation"]["with_skill"]
        )
        retry_prompt = _retry_prompt(
            retry_generation["prompt"],
            retry_generation["parsed"],
            _retry_directives(
                retry_generation["parsed"], first_validation,
                retry["evidence"][0]["source_diagnostics"]["genre"],
            ),
        )
        retry_generation["prompt"] = retry_prompt
        retry_generation["prompt_sha256"] = hashlib.sha256(
            retry_prompt.encode("utf-8")
        ).hexdigest()
        final_attempt = copy.deepcopy(retry_generation)
        final_attempt["validation"] = final_validation
        retry_generation["attempts"] = [first_attempt, final_attempt]
        retry["runs"][0]["provenance"]["generation_attempts"] = 2
        retry["runs"][0]["provenance"]["generation_prompt_sha256"] = (
            retry_generation["prompt_sha256"]
        )
        retry_path.write_text(json.dumps(retry), encoding="utf-8")
        retry_result = run(score_command[:3] + [str(retry_path)] + score_command[4:])

        forged = json.loads(valid_path.read_text(encoding="utf-8"))
        forged["runs"][0]["rewrite"] = source
        forged["runs"][0]["repairs"] = {"issue-1": True}
        forged["runs"][0]["protections"] = {"good-1": True}
        forged["runs"][0]["constraints"] = {"constraint-1": True}
        forged["runs"][0]["net_improved"] = True
        forged_path.write_text(json.dumps(forged), encoding="utf-8")
        forged_result = run(score_command[:3] + [str(forged_path)] + score_command[4:])

        correlated_rewrite = json.loads(valid_path.read_text(encoding="utf-8"))
        correlated_rewrite["runs"][0]["rewrite"] = source
        correlated_rewrite["evidence"][0]["generation"]["with_skill"]["parsed"][
            "rewrite"
        ] = source
        correlated_rewrite_path.write_text(json.dumps(correlated_rewrite), encoding="utf-8")
        correlated_rewrite_result = run(
            score_command[:3] + [str(correlated_rewrite_path)] + score_command[4:]
        )

        correlated_findings = json.loads(valid_path.read_text(encoding="utf-8"))
        fake_findings = [{**finding, "category": "forged-perfect-detection"}]
        correlated_findings["runs"][1]["findings"] = fake_findings
        correlated_findings["evidence"][0]["generation"]["without_skill"]["parsed"][
            "findings"
        ] = fake_findings
        correlated_findings_path.write_text(json.dumps(correlated_findings), encoding="utf-8")
        correlated_findings_result = run(
            score_command[:3] + [str(correlated_findings_path)] + score_command[4:]
        )

        tool_event = json.loads(valid_path.read_text(encoding="utf-8"))
        generation_event = tool_event["evidence"][0]["generation"]["with_skill"]
        injected_events = generation_event["invocation_events"] + (
            '\n{"type":"item.completed","item":{"type":"command_execution",'
            '"command":"cat SKILL.md"}}\n'
        )
        generation_event["invocation_events"] = injected_events
        generation_event["invocation_events_sha256"] = hashlib.sha256(
            injected_events.encode("utf-8")
        ).hexdigest()
        tool_event_path.write_text(json.dumps(tool_event), encoding="utf-8")
        tool_event_result = run(
            score_command[:3] + [str(tool_event_path)] + score_command[4:]
        )

        stale_manifest = copy.deepcopy(manifest)
        stale_manifest["cases"][0]["source"] += " "
        stale_manifest_path.write_text(json.dumps(stale_manifest), encoding="utf-8")
        stale_result = run(
            score_command[:2] + [str(stale_manifest_path), str(valid_path)] + score_command[4:]
        )

    valid_ok = valid.returncode == 0
    retry_ok = retry_result.returncode == 0
    forged_rejected = forged_result.returncode == 2
    correlated_rewrite_rejected = correlated_rewrite_result.returncode == 2
    correlated_findings_rejected = correlated_findings_result.returncode == 2
    tool_event_rejected = tool_event_result.returncode == 2
    stale_rejected = stale_result.returncode == 2
    print(f"valid_runner_artifact={'accepted' if valid_ok else 'rejected'}")
    print(f"retry_runner_artifact={'accepted' if retry_ok else 'rejected'}")
    print(
        "forged_artifact={} stale_artifact={}".format(
            "rejected" if forged_rejected else "accepted",
            "rejected" if stale_rejected else "accepted",
        )
    )
    print(
        "correlated_rewrite={} correlated_findings={}".format(
            "rejected" if correlated_rewrite_rejected else "accepted",
            "rejected" if correlated_findings_rejected else "accepted",
        )
    )
    print(f"tool_call_event={'rejected' if tool_event_rejected else 'accepted'}")
    return 0 if (
        valid_ok
        and retry_ok
        and forged_rejected
        and stale_rejected
        and correlated_rewrite_rejected
        and correlated_findings_rejected
        and tool_event_rejected
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
