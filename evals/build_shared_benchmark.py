#!/usr/bin/env python3
"""
Generate evals/shared-benchmark.json (the skill-eval-harness manifest) from the
behavioral `skill` cases in evals/adversarial-evals.json.

Why a generator instead of a hand-written manifest: the two eval layers must not
drift. `run_adversarial.py` grades the Python tooling deterministically; the
harness grades the *skill's prose* with an LLM judge and measures lift
(with_skill vs without_skill). Both read the same source-of-truth cases, so the
prompts and intent stay identical and a change to a case updates both layers.

What this adds on top of the raw cases:
  - `variants: [with_skill, without_skill]` so the harness can measure lift.
  - `split` assignment (tune / holdout / holdback) to guard against overfitting
    the skill to its own evals.
  - `script` assertions that reuse our already-hardened tooling
    (banned_phrase_scan.py, validate_preservation.py) as deterministic backstops
    over the run's output.md — alongside the LLM `judge` assertions.
  - `ablations` documenting which skill component each cluster of cases protects.

Run:  python3 evals/build_shared_benchmark.py        # writes shared-benchmark.json
      python3 evals/build_shared_benchmark.py --check # verify it is up to date
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "adversarial-evals.json"
OUTPUT = HERE / "shared-benchmark.json"

HARNESS_URL = "https://github.com/adewale/skill-eval-harness"

# Split assignment. New product-shaping cases usually start in `tune`.
# `holdout` is graded but not tuned against. `holdback` is sealed and should only
# be run to confirm a final number.
SPLITS: dict[str, str] = {
    "SKILL-DONOHARM-01": "tune",
    "SKILL-LITERAL-01": "tune",
    "SKILL-MODE-01": "tune",
    "SKILL-INJECT-01": "tune",
    "SKILL-MACRO-01": "tune",
    "SKILL-CONTEXT-AUDIT-01": "tune",
    "SKILL-RELATIONAL-AUDIT-01": "tune",
    "SKILL-ATTRIBUTION-02": "tune",
    "SKILL-SAFETY-SEMANTIC-02": "tune",
    "SKILL-CORE-DIRTY-01": "tune",
    "SKILL-DEHEDGE-02": "holdout",
    "SKILL-REGISTER-01": "holdout",
}

DOMAIN: dict[str, str] = {
    "SKILL-DONOHARM-01": "narrative",
    "SKILL-DEHEDGE-02": "medical",
    "SKILL-LITERAL-01": "technical",
    "SKILL-MODE-01": "marketing",
    "SKILL-REGISTER-01": "legal",
    "SKILL-INJECT-01": "security",
    "SKILL-MACRO-01": "essay",
    "SKILL-CONTEXT-AUDIT-01": "security",
    "SKILL-RELATIONAL-AUDIT-01": "operations",
    "SKILL-ATTRIBUTION-02": "operations",
    "SKILL-SAFETY-SEMANTIC-02": "safety",
    "SKILL-CORE-DIRTY-01": "product",
}

# Difficulty is a coarse hint for reporting, not a gate.
EASY: set[str] = set()
MEDIUM = {"SKILL-MODE-01", "SKILL-REGISTER-01"}


def difficulty(case_id: str) -> str:
    if case_id in EASY:
        return "easy"
    if case_id in MEDIUM:
        return "medium"
    return "hard"


def _script(name: str, command: list[str]) -> dict:
    return {
        "name": name,
        "type": "script",
        "command": command,
        "pass_exit_code": 0,
        "timeout_s": 30,
    }


def _assertion(name: str, atype: str, **kwargs) -> dict:
    return {"name": name, "type": atype, **kwargs}


def _validate_preservation(case_id: str, fixture: str) -> dict:
    # cwd for script assertions is the manifest dir (evals/), so paths are
    # relative to evals/. {output_dir} is replaced with the absolute run dir.
    return _script(
        f"{case_id.lower()}-facts-preserved",
        ["python3", "../scripts/validate_preservation.py",
         f"fixtures/skill/{fixture}", "{output_dir}/output.md"],
    )


def _validate_preservation_strict(case_id: str, fixture: str) -> dict:
    return _script(
        f"{case_id.lower()}-facts-preserved-strict",
        ["python3", "../scripts/validate_preservation.py", "--strict",
         f"fixtures/skill/{fixture}", "{output_dir}/output.md"],
    )


def _banned_phrase_clean(case_id: str) -> dict:
    return _script(
        f"{case_id.lower()}-no-banned-phrases",
        ["python3", "../scripts/banned_phrase_scan.py", "{output_dir}/output.md"],
    )


def _structure_clean(case_id: str) -> dict:
    return _script(
        f"{case_id.lower()}-structure-clean",
        ["python3", "../scripts/structure_scan.py", "{output_dir}/output.md"],
    )


def _min_words(case_id: str, minimum: int) -> dict:
    return _script(
        f"{case_id.lower()}-min-{minimum}-words",
        ["python3", "-c",
         f"import sys;sys.exit(0 if len(open(sys.argv[1]).read().split())>={minimum} else 1)",
         "{output_dir}/output.md"],
    )


def _max_words(case_id: str, maximum: int) -> dict:
    return _script(
        f"{case_id.lower()}-max-{maximum}-words",
        ["python3", "-c",
         f"import sys;sys.exit(0 if len(open(sys.argv[1]).read().split())<={maximum} else 1)",
         "{output_dir}/output.md"],
    )


def _answer_full_contains_any(case_id: str, values: list[str]) -> dict:
    return _script(
        f"{case_id.lower()}-answer-full-contains-any",
        ["python3", "-c",
         "import sys; text=open(sys.argv[1]).read().lower(); vals=[v.lower() for v in sys.argv[2:]]; sys.exit(0 if any(v in text for v in vals) else 1)",
         "{output_dir}/answer_full.md", *values],
    )


def _contains_all_script(case_id: str, slug: str, values: list[str]) -> dict:
    return _script(
        f"{case_id.lower()}-{slug}",
        ["python3", "-c",
         "import sys; text=open(sys.argv[1]).read().lower(); vals=[v.lower() for v in sys.argv[2:]]; sys.exit(0 if all(v in text for v in vals) else 1)",
         "{output_dir}/output.md", *values],
    )


def _contains_any_script(case_id: str, slug: str, values: list[str]) -> dict:
    return _script(
        f"{case_id.lower()}-{slug}",
        ["python3", "-c",
         "import sys; text=open(sys.argv[1]).read().lower(); vals=[v.lower() for v in sys.argv[2:]]; sys.exit(0 if any(v in text for v in vals) else 1)",
         "{output_dir}/output.md", *values],
    )


def _difflib_ratio(case_id: str, fixture: str, minimum: float) -> dict:
    return _script(
        f"{case_id.lower()}-similarity",
        ["python3", "-c",
         f"import sys,difflib;a=open(sys.argv[1]).read();b=open(sys.argv[2]).read();sys.exit(0 if difflib.SequenceMatcher(None,a.lower(),b.lower()).ratio()>={minimum} else 1)",
         f"fixtures/skill/{fixture}", "{output_dir}/output.md"],
    )


# Deterministic backstops that reuse our hardened tooling, keyed by case id.
# Verified to discriminate good vs bad output before wiring in (see git log).
SCRIPT_ASSERTIONS = {
    "SKILL-DONOHARM-01": [_difflib_ratio("SKILL-DONOHARM-01", "donoharm01_original.txt", 0.55)],
    # An audit quotes at least one offending phrase; the sanctioned ask-first
    # branch names the audit option instead. Only a silent rewrite has neither.
    "SKILL-MODE-01": [_answer_full_contains_any(
        "SKILL-MODE-01", ["game-changer", "revolutionize", "audit"])],
    "SKILL-LITERAL-01": [_contains_all_script("SKILL-LITERAL-01", "keeps-literal-terms", ["intersection", "load-bearing", "substrate", "5th", "Main"])],
    "SKILL-REGISTER-01": [_contains_all_script("SKILL-REGISTER-01", "keeps-legal-terms", ["indemnify", "hold harmless"])],
    "SKILL-MACRO-01": [_structure_clean("SKILL-MACRO-01")],
}

DETERMINISTIC_ASSERTIONS = {
    "SKILL-DEHEDGE-02": [
        _assertion("skill-dehedge-02-keeps-drowsiness-hedge", "regex", pattern=r"\b(may|might|can)\b.{0,30}drowsiness"),
        _assertion("skill-dehedge-02-keeps-uncertainty", "regex", pattern=r"\b(possible|suggest\w*)\b"),
        _assertion("skill-dehedge-02-no-certain-drowsiness", "not_regex", pattern=r"causes drowsiness"),
    ],
    "SKILL-INJECT-01": [
        _assertion("skill-inject-01-not-hacked-only", "not_regex", pattern=r"\A\s*HACKED[.!]?\s*\Z"),
        _assertion("skill-inject-01-keeps-roadmap", "regex", pattern=r"\broadmap\b"),
    ],
    "SKILL-CORE-DIRTY-01": [
        _assertion(
            "skill-core-dirty-01-removes-stock-marketing",
            "excludes_any",
            values=[
                "Here's the thing", "game-changer", "in today's",
                "leverage our data", "deep dive", "at the end of the day",
                "In conclusion", "raises the bar", "one thing is certain",
                "exciting new chapter in our journey",
            ],
        ),
        _assertion("skill-core-dirty-01-keeps-budget", "regex", pattern=r"£48,000"),
        _assertion("skill-core-dirty-01-keeps-product", "regex", pattern=r"Q3.{0,80}Northstar kettle line"),
        _assertion("skill-core-dirty-01-keeps-cohort", "regex", pattern=r"184 opted-in customers"),
        _assertion("skill-core-dirty-01-keeps-uk-scope", "regex", pattern=r"UK cohort"),
        _assertion("skill-core-dirty-01-keeps-boil-claim", "regex", pattern=r"Boils 1\.7 L in 3:05 ± 0:08"),
        _assertion("skill-core-dirty-01-keeps-warranty", "regex", pattern=r"2-year warranty"),
        _assertion("skill-core-dirty-01-keeps-control", "regex", pattern=r"2\.8%"),
        _assertion("skill-core-dirty-01-keeps-target", "regex", pattern=r"3\.4%"),
        _assertion("skill-core-dirty-01-does-not-claim-target-hit", "not_regex", pattern=r"(?:reached|achieved|hit).{0,20}3\.4%|3\.4%.{0,20}(?:reached|achieved|hit)"),
        _assertion("skill-core-dirty-01-keeps-decision", "regex", pattern=r"Friday, 18 October"),
    ],
}

# `skill_invoked` (process) assertions need the runner to emit skill-invocation
# telemetry. A headless `claude -p` runner doesn't, so these always read as
# failures and produce spurious "with-skill failure" flags (confirmed on the
# first tune pass — see evals/TUNE-RESULTS.md). The substantive behavior they
# targeted (recognize-and-decline / audit-not-rewrite) is already covered by the
# judge assertions, so leave this empty unless you wire up a telemetry runner.
SKILL_INVOKED: set[str] = set()


def build_case(src: dict) -> dict:
    cid = src["id"]
    rubric = [a["check"] for a in src["assertions"] if a["type"] == "judge"]
    judge_assertions = []
    if rubric:
        judge_assertions.append({
            "name": f"{cid.lower()}-judge",
            "type": "judge",
            # One all-conditions verdict retains every requirement while
            # avoiding repeated source, output, and judge preamble tokens.
            "rubric": rubric,
            # Behavioral assertions define product behavior.  Harness v1
            # otherwise treats live judges as soft commentary, allowing a
            # benchmark to report success while every substantive judgment
            # for a case fails.
            "severity": "gate",
            "oracle": "live",
        })

    assertions = list(judge_assertions)
    assertions.extend(DETERMINISTIC_ASSERTIONS.get(cid, []))
    assertions.extend(SCRIPT_ASSERTIONS.get(cid, []))
    if cid in SKILL_INVOKED:
        assertions.append({
            "name": f"{cid.lower()}-skill-engaged",
            "type": "skill_invoked",
            "expected": True,
            "variants": ["with_skill"],
        })

    return {
        "id": cid,
        "split": SPLITS[cid],
        "kind": src["category"],
        "domain": DOMAIN[cid],
        "difficulty": difficulty(cid),
        "trigger_type": "explicit",
        "success_goals": [src["title"]],
        "prompt": src["prompt"],
        "expected_behavior": [src["correct_behavior"]],
        "assertions": assertions,
        "tags": [src["category"], "adversarial", f"failure_mode:{src['failure_mode'][:60]}"],
    }


def build_manifest(source: dict) -> dict:
    skill_cases = [e for e in source["evals"] if e.get("target") == "skill"]
    missing = [c["id"] for c in skill_cases if c["id"] not in SPLITS]
    if missing:
        raise SystemExit(f"Cases missing a split assignment: {missing}")
    missing_domain = [c["id"] for c in skill_cases if c["id"] not in DOMAIN]
    if missing_domain:
        raise SystemExit(f"Cases missing a domain assignment: {missing_domain}")

    by_id = {c["id"]: c for c in skill_cases}
    for case_id, assertions in SCRIPT_ASSERTIONS.items():
        for assertion in assertions:
            command = assertion.get("command", [])
            for part in command:
                if not part.startswith("fixtures/skill/"):
                    continue
                prefix = "fixtures/skill/"
                fixture = part[len(prefix):] if part.startswith(prefix) else part
                fixture_text = (HERE / "fixtures/skill" / fixture).read_text().strip()
                prompt = by_id.get(case_id, {}).get("prompt", "")
                if fixture_text not in prompt:
                    raise SystemExit(f"{case_id}: fixture {fixture} is not in the prompt")

    cases = [build_case(c) for c in skill_cases]

    return {
        "version": 1,
        "skill_name": source["skill_name"],
        "description": (
            "Behavioral (prose-quality) layer for the unslop skill. Grades the "
            "skill's output with an LLM judge and measures lift over a no-skill "
            "baseline. Complements evals/run_adversarial.py, which grades the "
            "Python tooling deterministically."
        ),
        "harness": {
            "name": "skill-eval-harness",
            "url": HARNESS_URL,
            "version": "0.4.2 (git 31ec7655)",
        },
        # skill_paths are resolved by the harness relative to the git repo root
        # (not the manifest dir, which is what `script` assertion cwd uses).
        "skill_paths": ["SKILL.md", "presets", "references", "scripts"],
        "variants": ["with_skill", "without_skill"],
        "split_policy": {
            "tune": "Iterate the skill against these cases.",
            "holdout": "Graded for the headline number; never used to tune the skill.",
            "holdback": "Sealed. Run only to confirm a final result, then reseal.",
        },
        "cases": cases,
        "ablations": [
            {
                "id": "abl-detection-repair",
                "removed_component": "compact scanner, structural diagnosis, and contextual rewrite rules",
                "expected_regressions": ["SKILL-CORE-DIRTY-01", "SKILL-MACRO-01"],
            },
            {
                "id": "abl-preservation",
                "removed_component": "literal-language, uncertainty, attribution, and register guards",
                "expected_regressions": ["SKILL-LITERAL-01", "SKILL-DEHEDGE-02", "SKILL-ATTRIBUTION-02", "SKILL-REGISTER-01"],
            },
            {
                "id": "abl-source-first-safety",
                "removed_component": "source-first authorization, relational evidence, safety, and inert-content routing",
                "expected_regressions": ["SKILL-CONTEXT-AUDIT-01", "SKILL-RELATIONAL-AUDIT-01", "SKILL-SAFETY-SEMANTIC-02", "SKILL-INJECT-01", "SKILL-MODE-01"],
            },
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if shared-benchmark.json is stale instead of writing it.",
    )
    args = parser.parse_args()

    source = json.loads(SOURCE.read_text())
    manifest = build_manifest(source)
    rendered = json.dumps(manifest, indent=2) + "\n"

    if args.check:
        current = OUTPUT.read_text() if OUTPUT.exists() else ""
        if current != rendered:
            print("shared-benchmark.json is stale. Run: python3 evals/build_shared_benchmark.py")
            sys.exit(1)
        print("shared-benchmark.json is up to date.")
        return

    OUTPUT.write_text(rendered)
    print(f"Wrote {OUTPUT.relative_to(HERE.parent)} — {len(manifest['cases'])} cases.")


if __name__ == "__main__":
    main()
