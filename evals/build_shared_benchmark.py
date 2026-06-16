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
    # tune — iterate against these
    "SKILL-FRAGMENT-01": "tune",
    "SKILL-HEDGE-03": "tune",
    "SKILL-LEGAL-02": "tune",
    "SKILL-STACCATO-01": "tune",
    "SKILL-NOINVENT-01": "tune",
    "SKILL-DEHEDGE-01": "tune",
    "SKILL-LITERAL-01": "tune",
    "SKILL-MODE-01": "tune",
    "SKILL-PRESET-01": "tune",
    "SKILL-RUBRIC-01": "tune",
    "SKILL-INJECT-01": "tune",
    "SKILL-NEWPAT-01": "tune",
    "SKILL-WEDGE-01": "tune",
    "SKILL-DONOHARM-01": "tune",
    "SKILL-WARMTH-01": "tune",
    # holdout — measure, do not tune
    "SKILL-DEHEDGE-02": "holdout",
    "SKILL-LIST-01": "holdout",
    "SKILL-DISAMBIG-01": "holdout",
    "SKILL-APPROX-01": "holdout",
    "SKILL-COMPRESS-01": "holdout",
    "SKILL-REGISTER-01": "holdout",
    "SKILL-DIALOGUE-01": "holdout",
    "SKILL-EMDASH-01": "holdout",
    # holdback — sealed
    "SKILL-SAFETY-01": "holdback",
    "SKILL-SHORT-01": "holdback",
    "SKILL-CODE-01": "holdback",
    "SKILL-OVEREDIT-01": "holdback",
}

DOMAIN: dict[str, str] = {
    "SKILL-DONOHARM-01": "narrative",
    "SKILL-DEHEDGE-01": "security",
    "SKILL-DEHEDGE-02": "medical",
    "SKILL-LITERAL-01": "technical",
    "SKILL-LIST-01": "product",
    "SKILL-DISAMBIG-01": "news",
    "SKILL-APPROX-01": "product",
    "SKILL-MODE-01": "marketing",
    "SKILL-PRESET-01": "narrative",
    "SKILL-REGISTER-01": "legal",
    "SKILL-RUBRIC-01": "business",
    "SKILL-COMPRESS-01": "argument",
    "SKILL-DIALOGUE-01": "fiction",
    "SKILL-CODE-01": "technical",
    "SKILL-SAFETY-01": "safety",
    "SKILL-SHORT-01": "misc",
    "SKILL-INJECT-01": "security",
    "SKILL-NEWPAT-01": "business",
    "SKILL-WEDGE-01": "product",
    "SKILL-FRAGMENT-01": "business",
    "SKILL-HEDGE-03": "scientific",
    "SKILL-LEGAL-02": "legal",
    "SKILL-STACCATO-01": "business",
    "SKILL-WARMTH-01": "email",
    "SKILL-NOINVENT-01": "technical",
    "SKILL-OVEREDIT-01": "argument",
    "SKILL-EMDASH-01": "business",
}

# Difficulty is a coarse hint for reporting, not a gate.
EASY = {"SKILL-SHORT-01"}
MEDIUM = {
    "SKILL-MODE-01", "SKILL-PRESET-01", "SKILL-DIALOGUE-01", "SKILL-CODE-01",
    "SKILL-SAFETY-01", "SKILL-WARMTH-01", "SKILL-REGISTER-01", "SKILL-LIST-01",
}


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


def _validate_preservation(case_id: str, fixture: str) -> dict:
    # cwd for script assertions is the manifest dir (evals/), so paths are
    # relative to evals/. {output_dir} is replaced with the absolute run dir.
    return _script(
        f"{case_id.lower()}-facts-preserved",
        ["python3", "../scripts/validate_preservation.py",
         f"fixtures/skill/{fixture}", "{output_dir}/output.md"],
    )


def _banned_phrase_clean(case_id: str) -> dict:
    return _script(
        f"{case_id.lower()}-no-banned-phrases",
        ["python3", "../scripts/banned_phrase_scan.py", "{output_dir}/output.md"],
    )


# Deterministic backstops that reuse our hardened tooling, keyed by case id.
# Verified to discriminate good vs bad output before wiring in (see git log).
SCRIPT_ASSERTIONS = {
    "SKILL-LEGAL-02": [_validate_preservation("SKILL-LEGAL-02", "legal02_original.txt")],
    "SKILL-APPROX-01": [_validate_preservation("SKILL-APPROX-01", "approx01_original.txt")],
    "SKILL-DISAMBIG-01": [_validate_preservation("SKILL-DISAMBIG-01", "disambig01_original.txt")],
    "SKILL-FRAGMENT-01": [_banned_phrase_clean("SKILL-FRAGMENT-01")],
    "SKILL-STACCATO-01": [_banned_phrase_clean("SKILL-STACCATO-01")],
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
    judge_assertions = [
        {
            "name": f"{cid.lower()}-judge-{i + 1}",
            "type": "judge",
            "rubric": [a["check"]],
        }
        for i, a in enumerate(src["assertions"])
        if a["type"] == "judge"
    ]

    assertions = list(judge_assertions)
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
                "id": "abl-antislop-guard",
                "removed_component": "anti_slop_register patterns in scripts/banned_phrase_scan.py and the anti-slop guard in SKILL.md",
                "expected_regressions": ["SKILL-FRAGMENT-01", "SKILL-STACCATO-01"],
            },
            {
                "id": "abl-fact-validation",
                "removed_component": "constraint checks in scripts/validate_preservation.py",
                "expected_regressions": ["SKILL-LEGAL-02", "SKILL-APPROX-01", "SKILL-DISAMBIG-01"],
            },
            {
                "id": "abl-presets",
                "removed_component": "presets/ (story / warm / register presets)",
                "expected_regressions": ["SKILL-PRESET-01", "SKILL-WARMTH-01", "SKILL-REGISTER-01"],
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
