#!/usr/bin/env python3
"""Exercise the core scorecard with misses, false alarms, and damage."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evals"))

from core_metrics import match_findings, score  # noqa: E402


def span(source: str, text: str, span_id: str, category: str | None = None) -> dict:
    start = source.index(text)
    value = {"id": span_id, "start": start, "end": start + len(text), "text": text}
    if category:
        value["category"] = category
    return value


def main() -> int:
    first = "Here's the thing: the API returns 200 on success. Keep Section 4 unchanged."
    second = "The cache is a game-changer. The timeout remains 30 seconds."
    clean = "I tightened the hinge after lunch. It now closes without scraping."
    manifest = {
        "schema": "unslop-core-benchmark-v1",
        "required_arms": ["with_skill"],
        "cases": [
            {
                "id": "fixture-1",
                "split": "tune",
                "genre": "technical",
                "register": "technical",
                "provenance": {"kind": "unit_fixture"},
                "source": first,
                "issues": [span(first, "Here's the thing:", "issue-1", "throat_clearing")],
                "protected_spans": [span(first, "the API returns 200 on success.", "good-1")],
                "constraints": [{"id": "constraint-1", "description": "Keep Section 4 unchanged."}],
            },
            {
                "id": "fixture-2",
                "split": "tune",
                "genre": "business",
                "register": "general",
                "provenance": {"kind": "unit_fixture"},
                "source": second,
                "issues": [span(second, "game-changer", "issue-2", "jargon")],
                "protected_spans": [{
                    **span(second, "The timeout remains 30 seconds.", "good-2"),
                    "policy": "Preserve this timeout statement.",
                    "enforcement": "exact_span",
                }],
                "constraints": [{"id": "constraint-2", "description": "Preserve 30 seconds."}],
            },
            {
                "id": "fixture-clean",
                "split": "tune",
                "genre": "general",
                "register": "general",
                "provenance": {"kind": "unit_fixture"},
                "source": clean,
                "issues": [],
                "protected_spans": [],
                "constraints": [],
            },
        ],
    }
    predictions = {
        "schema": "unslop-core-predictions-v1",
        "evidence": [
            {
                "case_id": "fixture-1",
                "semantic_diagnosis": {
                    "invocation_events": '{"type":"unslop.invocation_metrics","model":"gpt-5.6-luna","elapsed_seconds":1.25,"input_tokens":100,"cached_input_tokens":40,"output_tokens":10}\n'
                },
                "generation": {
                    "with_skill": {
                        "invocation_events": '{"type":"unslop.invocation_metrics","model":"gpt-5.6-luna","elapsed_seconds":2.5,"input_tokens":200,"cached_input_tokens":100,"output_tokens":20}\n'
                    }
                },
                "judge": {
                    "invocation_events": '{"type":"unslop.invocation_metrics","model":"gpt-5.6-sol","elapsed_seconds":0.75,"input_tokens":70,"cached_input_tokens":20,"output_tokens":7}\n'
                },
            },
            {"case_id": "fixture-2"},
            {"case_id": "fixture-clean"},
        ],
        "runs": [
            {
                "case_id": "fixture-1",
                "arm": "with_skill",
                "findings": [
                    {"start": 0, "end": 17, "category": "throat_clearing"},
                    {"start": 18, "end": 25, "category": "jargon"},
                ],
                "repairs": {"issue-1": True},
                "protections": {"good-1": True},
                "constraints": {"constraint-1": True},
                "net_improved": True,
                "rewrite": "The API returns 200 on success. Keep Section 4 unchanged.",
                "provenance": {"model": "fixture-model"},
            },
            {
                "case_id": "fixture-2",
                "arm": "with_skill",
                "findings": [{"start": 15, "end": 27, "category": "jargon"}],
                "repairs": {"issue-2": False},
                "protections": {"good-2": True},
                "constraints": {"constraint-2": True},
                "net_improved": True,
                "rewrite": "The cache is a game-changer. The timeout changed to 60 seconds.",
                "provenance": {"model": "fixture-model"},
            },
            {
                "case_id": "fixture-clean",
                "arm": "with_skill",
                "findings": [],
                "repairs": {},
                "protections": {},
                "constraints": {},
                "net_improved": False,
                "rewrite": clean,
                "provenance": {"model": "fixture-model"},
            },
        ],
    }
    result = score(
        manifest,
        predictions,
        split="tune",
        verify_evidence=False,
    )
    metrics = result["by_arm"]["with_skill"]
    print(json.dumps(result, sort_keys=True))
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
    print(f"clean_noop_rate={metrics['clean_noop_rate']:.6f}")
    print(f"deterministic_overrides={len(result.get('deterministic_overrides', []))}")
    operational = result["operational"]
    usage_ok = (
        operational.get("model_calls") == 3
        and operational.get("elapsed_seconds") == 4.5
        and operational.get("input_tokens") == 370
        and operational.get("cached_input_tokens") == 160
        and operational.get("output_tokens") == 37
    )
    print(
        f"usage_calls={operational.get('model_calls')} "
        f"input_tokens={operational.get('input_tokens')} "
        f"cached_input_tokens={operational.get('cached_input_tokens')} "
        f"output_tokens={operational.get('output_tokens')} "
        f"elapsed_seconds={operational.get('elapsed_seconds')}"
    )
    shotgun = [{"start": 0, "end": 100}, {"start": 0, "end": 100}]
    gold = [{"start": 10, "end": 20}, {"start": 60, "end": 70}]
    shotgun_rejected = match_findings(shotgun, gold, 100) == (0, 2, 2)
    print(f"shotgun_rejected={str(shotgun_rejected).lower()}")
    return 0 if shotgun_rejected and usage_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
