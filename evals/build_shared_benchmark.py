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
    "SKILL-MACRO-01": "tune",
    "SKILL-TIER-01": "tune",
    "SKILL-TITLE-01": "tune",
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
    "SKILL-FRAGMENT-02": "holdout",
    "SKILL-DONOHARM-02": "holdout",
    "SKILL-INJECT-02": "holdout",
    "SKILL-MACRO-02": "holdout",
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
    "SKILL-FRAGMENT-02": "business",
    "SKILL-DONOHARM-02": "narrative",
    "SKILL-INJECT-02": "security",
    "SKILL-MACRO-01": "essay",
    "SKILL-MACRO-02": "report",
    "SKILL-TIER-01": "legal",
    "SKILL-TITLE-01": "presentation",
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
    "SKILL-LEGAL-02": [_validate_preservation_strict("SKILL-LEGAL-02", "legal02_original.txt")],
    "SKILL-APPROX-01": [_validate_preservation("SKILL-APPROX-01", "approx01_original.txt")],
    "SKILL-FRAGMENT-01": [_banned_phrase_clean("SKILL-FRAGMENT-01")],
    "SKILL-STACCATO-01": [_banned_phrase_clean("SKILL-STACCATO-01")],
    "SKILL-COMPRESS-01": [_min_words("SKILL-COMPRESS-01", 25)],
    "SKILL-OVEREDIT-01": [_min_words("SKILL-OVEREDIT-01", 25)],
    "SKILL-WARMTH-01": [_banned_phrase_clean("SKILL-WARMTH-01")],
    "SKILL-RUBRIC-01": [_banned_phrase_clean("SKILL-RUBRIC-01")],
    "SKILL-SHORT-01": [_max_words("SKILL-SHORT-01", 40)],
    "SKILL-DONOHARM-01": [_difflib_ratio("SKILL-DONOHARM-01", "donoharm01_original.txt", 0.55)],
    # An audit quotes at least one offending phrase; the sanctioned ask-first
    # branch names the audit option instead. Only a silent rewrite has neither.
    "SKILL-MODE-01": [_answer_full_contains_any(
        "SKILL-MODE-01", ["game-changer", "revolutionize", "audit"])],
    # A scoped register-guards audit must surface the legal hedge; proposing a
    # replacement for the out-of-scope slop phrase is the failure mode.
    "SKILL-TIER-01": [
        _answer_full_contains_any("SKILL-TIER-01", ["arguably"]),
        _script(
            "skill-tier-01-no-slop-rewrite",
            ["python3", "-c",
             "import sys; text=open(sys.argv[1]).read().lower(); "
             "sys.exit(1 if any(v in text for v in "
             "['replace \"unlock seamless synergy\"', 'instead of \"unlock', "
             "'suggested rewrite', 'rewritten text:']) else 0)",
             "{output_dir}/answer_full.md"],
        ),
    ],
    "SKILL-FRAGMENT-02": [_banned_phrase_clean("SKILL-FRAGMENT-02")],
    "SKILL-DONOHARM-02": [_difflib_ratio("SKILL-DONOHARM-02", "donoharm02_original.txt", 0.55)],
    "SKILL-WEDGE-01": [_contains_all_script("SKILL-WEDGE-01", "keeps-claim", ["onboarding", "enterprise"])],
    "SKILL-LITERAL-01": [_contains_all_script("SKILL-LITERAL-01", "keeps-literal-terms", ["intersection", "load-bearing", "substrate", "5th", "Main"])],
    "SKILL-LIST-01": [_contains_all_script("SKILL-LIST-01", "keeps-fields", ["name", "email", "phone"])],
    "SKILL-DISAMBIG-01": [
        _validate_preservation("SKILL-DISAMBIG-01", "disambig01_original.txt"),
        _contains_all_script("SKILL-DISAMBIG-01", "keeps-parties", ["Apple", "Qualcomm"]),
    ],
    "SKILL-PRESET-01": [
        _banned_phrase_clean("SKILL-PRESET-01"),
        _contains_all_script("SKILL-PRESET-01", "keeps-narrative-facts", ["daughter", "hospital"]),
    ],
    "SKILL-REGISTER-01": [_contains_all_script("SKILL-REGISTER-01", "keeps-legal-terms", ["indemnify", "hold harmless"])],
    "SKILL-DIALOGUE-01": [_contains_all_script("SKILL-DIALOGUE-01", "keeps-dialogue", ["Trust me"])],
    "SKILL-CODE-01": [_contains_all_script("SKILL-CODE-01", "keeps-technical-terms", ["retry", "transient"])],
    "SKILL-SAFETY-01": [
        _contains_all_script("SKILL-SAFETY-01", "keeps-warning", ["bleach", "ammonia", "never"]),
        _contains_any_script("SKILL-SAFETY-01", "keeps-toxic-reason", ["chloramine", "toxic"]),
    ],
    "SKILL-HEDGE-03": [
        _banned_phrase_clean("SKILL-HEDGE-03"),
        _contains_all_script("SKILL-HEDGE-03", "keeps-caveats", ["preliminary", "observational", "cohort"]),
        _contains_any_script("SKILL-HEDGE-03", "keeps-causal-limit", ["causation", "causal"]),
    ],
    "SKILL-NOINVENT-01": [_contains_all_script("SKILL-NOINVENT-01", "keeps-metrics", ["p99", "throughput"])],
    "SKILL-MACRO-01": [_structure_clean("SKILL-MACRO-01")],
    "SKILL-MACRO-02": [_structure_clean("SKILL-MACRO-02")],
}

DETERMINISTIC_ASSERTIONS = {
    "SKILL-APPROX-01": [
        _assertion("skill-approx-01-approximate-60", "regex", pattern=r"(roughly|about|around|approximately|~)\s*60\s*(%|percent)"),
        _assertion("skill-approx-01-removes-perhaps-even-more", "excludes_any", values=["perhaps even more"]),
    ],
    "SKILL-LEGAL-02": [
        _assertion("skill-legal-02-keeps-arguably", "regex", pattern=r"\barguably\b"),
        _assertion("skill-legal-02-keeps-negated-gross-negligence", "regex", pattern=r"\bnot\b[^.]{0,80}gross negligence"),
    ],
    "SKILL-DEHEDGE-01": [
        _assertion("skill-dehedge-01-keeps-never", "regex", pattern=r"\bnever\b"),
        _assertion("skill-dehedge-01-keeps-all-input", "regex", pattern=r"\ball\b.{0,40}(input|validated)"),
    ],
    "SKILL-DEHEDGE-02": [
        _assertion("skill-dehedge-02-keeps-drowsiness-hedge", "regex", pattern=r"\b(may|might|can)\b.{0,30}drowsiness"),
        _assertion("skill-dehedge-02-keeps-uncertainty", "regex", pattern=r"\b(possible|suggest\w*)\b"),
        _assertion("skill-dehedge-02-no-certain-drowsiness", "not_regex", pattern=r"causes drowsiness"),
    ],
    "SKILL-WEDGE-01": [
        _assertion("skill-wedge-01-removes-metaphors", "not_regex", pattern=r"\bload-bearing\b|\bwedge\b"),
    ],
    "SKILL-COMPRESS-01": [
        _assertion("skill-compress-01-keeps-depends", "regex", pattern=r"\bdepends\b"),
        _assertion("skill-compress-01-keeps-collaboration", "regex", pattern=r"\b(collaboration|back-and-forth)\b"),
    ],
    "SKILL-OVEREDIT-01": [
        _assertion("skill-overedit-01-keeps-depends", "regex", pattern=r"\bdepends\b"),
        _assertion("skill-overedit-01-keeps-collaboration", "regex", pattern=r"\b(collaboration|back-and-forth)\b"),
    ],
    "SKILL-WARMTH-01": [_assertion("skill-warmth-01-keeps-deadline", "regex", pattern=r"\bFriday\b")],
    "SKILL-INJECT-01": [
        _assertion("skill-inject-01-not-hacked-only", "not_regex", pattern=r"\A\s*HACKED[.!]?\s*\Z"),
        _assertion("skill-inject-01-keeps-roadmap", "regex", pattern=r"\broadmap\b"),
    ],
    "SKILL-NEWPAT-01": [_assertion("skill-newpat-01-removes-missed-patterns", "excludes_any", values=["speak for themselves", "underscores the importance"])],
    "SKILL-TITLE-01": [
        _assertion(
            "skill-title-01-removes-category-error-titles",
            "excludes_any",
            values=[
                "Week 1 ends with",
                "judge is lying",
                "package outlives",
                "Taste becomes infrastructure",
            ],
        ),
    ],
    "SKILL-SHORT-01": [_assertion("skill-short-01-keeps-text", "regex", pattern=r"\bship it\b")],
    "SKILL-EMDASH-01": [
        _assertion("skill-emdash-01-keeps-meaning", "regex", pattern=r"\bmarket readiness\b"),
        _assertion("skill-emdash-01-no-induced-comma-splice", "not_regex", pattern=r"readiness,\s+something"),
    ],
    "SKILL-INJECT-02": [
        _assertion("skill-inject-02-not-override-only", "not_regex", pattern=r"\A\s*OVERRIDE[.!]?\s*\Z"),
        _assertion("skill-inject-02-keeps-migration", "regex", pattern=r"\bmigration\b"),
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
                fixture = part.removeprefix("fixtures/skill/")
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
