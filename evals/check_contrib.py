#!/usr/bin/env python3
"""Deterministic eval helper for the contribution scaffolder."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from _check_support import ROOT, run  # noqa: E402
from _contract_batch import run_contract  # noqa: E402

sys.path.insert(0, str(ROOT))
from scripts import contribute  # noqa: E402

FIXTURES = ROOT / "evals" / "fixtures" / "contrib"
BUNDLE = ROOT / ".unslop" / "contrib" / "durable-bridge"
CAP_BUNDLE = ROOT / ".unslop" / "contrib" / "let-that-sink-in"


def reset_bundle() -> None:
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    if CAP_BUNDLE.exists():
        shutil.rmtree(CAP_BUNDLE)


def snapshot_bundles() -> dict[Path, dict[Path, bytes] | None]:
    """Capture pre-existing contribution bundles so tests cannot delete them."""
    snapshots: dict[Path, dict[Path, bytes] | None] = {}
    for bundle in (BUNDLE, CAP_BUNDLE):
        snapshots[bundle] = (
            {
                path.relative_to(bundle): path.read_bytes()
                for path in bundle.rglob("*")
                if path.is_file()
            }
            if bundle.exists()
            else None
        )
    return snapshots


def restore_bundles(snapshots: dict[Path, dict[Path, bytes] | None]) -> None:
    reset_bundle()
    for bundle, files in snapshots.items():
        if files is None:
            continue
        bundle.mkdir(parents=True, exist_ok=True)
        for relative, content in files.items():
            destination = bundle / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)


def assert_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        print(f"{label} mismatch", file=sys.stderr)
        print("actual:", actual, file=sys.stderr)
        print("expected:", expected, file=sys.stderr)
        raise SystemExit(1)


def scaffold() -> subprocess.CompletedProcess[str]:
    reset_bundle()
    return run(
        [
            "python3",
            "scripts/contribute.py",
            "scaffold",
            "--snippet",
            "evals/fixtures/contrib/uncaught-snippet.txt",
            "--tell",
            "durable bridge",
            "--category",
            "significance_inflation",
            "--pattern-name",
            "durable-bridge",
            "--date",
            "2026-07-06",
        ]
    )


def case_precheck_covered() -> None:
    proc = run(["python3", "scripts/contribute.py", "precheck", "evals/fixtures/contrib/already-caught.txt"])
    if proc.returncode != 3:
        print(proc.stdout + proc.stderr)
        raise SystemExit(1)
    data = json.loads(proc.stdout)
    if data["status"] != "already_covered" or not data["findings"]:
        raise SystemExit(1)
    print("CONTRIB-01 ok")


def case_precheck_clean() -> None:
    proc = run(["python3", "scripts/contribute.py", "precheck", "evals/fixtures/contrib/uncaught-snippet.txt"])
    if proc.returncode != 0:
        print(proc.stdout + proc.stderr)
        raise SystemExit(1)
    data = json.loads(proc.stdout)
    assert_equal(data["status"], "clean", "status")
    assert_equal(data["words"], 29, "words")
    findings = contribute.scanner_findings(
        (FIXTURES / "uncaught-snippet.txt").read_text(encoding="utf-8")
    )
    assert_equal(findings, [], "both scanner findings")
    print("CONTRIB-02 ok")


def case_scaffold() -> None:
    proc = scaffold()
    if proc.returncode != 0:
        print(proc.stdout + proc.stderr)
        raise SystemExit(1)
    actual_row = json.loads((BUNDLE / "row_fn.json").read_text(encoding="utf-8"))
    expected_row = json.loads((FIXTURES / "expected-row-fn.json").read_text(encoding="utf-8"))
    assert_equal(actual_row, expected_row, "row_fn")
    assert_equal(
        set(actual_row),
        {"id", "target", "category", "stdin", "assertions"},
        "compact scanner contract shape",
    )
    assert_equal(
        contribute.GATE_COMMANDS,
        [["python3", "evals/check.py", "--full"]],
        "canonical contribution gate",
    )
    internals = (ROOT / "references" / "contribute.md").read_text(encoding="utf-8")
    if "evals/fixtures/contracts/scanner-examples.json" not in internals:
        raise SystemExit("contribution docs do not name the scanner contract table")
    if "exact_total" not in internals:
        raise SystemExit("contribution docs do not explain the table count update")
    if "git add evals/adversarial-evals.json" in internals:
        raise SystemExit("contribution docs still stage the legacy scanner destination")
    actual_manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    expected_manifest = json.loads((FIXTURES / "expected-manifest.json").read_text(encoding="utf-8"))
    assert_equal(actual_manifest, expected_manifest, "manifest")
    snippet = (FIXTURES / "redacted-snippet.txt").read_text(encoding="utf-8")
    assert_equal(actual_row["stdin"], snippet, "specimen")
    print("CONTRIB-03 ok")


def case_redaction_tell() -> None:
    reset_bundle()
    proc = run(
        [
            "python3",
            "scripts/contribute.py",
            "scaffold",
            "--snippet",
            "evals/fixtures/contrib/tell-redaction-snippet.txt",
            "--tell",
            "durable bridge",
            "--category",
            "significance_inflation",
            "--pattern-name",
            "durable-bridge",
            "--redact",
            "durable bridge=sturdy bridge",
            "--date",
            "2026-07-06",
        ]
    )
    if proc.returncode != 4:
        print(proc.stdout + proc.stderr)
        raise SystemExit(1)
    print("CONTRIB-04 ok")


def fill_report() -> None:
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    manifest["source_genre"] = "technical rollout note"
    manifest["rationale"] = (
        "`Durable bridge` inflates a migration detail into a vague promise. "
        "It sounds reassuring without naming the compatibility behavior, failure mode, or owner."
    )
    manifest["pattern_added"] = "`durable bridge`"
    manifest["severity"] = "soft"
    manifest["gating_rationale"] = "flag metaphorical migration praise, protect literal construction"
    (BUNDLE / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = (BUNDLE / "report.md").read_text(encoding="utf-8")
    report = report.replace(
        "TODO: explain why this phrase is a reusable AI-writing tell in 2-4 sentences.",
        manifest["rationale"],
    )
    report = report.replace("TODO: source genre", "technical rollout note")
    report = report.replace("Pattern added: TODO: regex or phrase for `durable bridge`", "Pattern added: `durable bridge`")
    report = report.replace("Severity: TODO: hard or soft", "Severity: soft")
    report = report.replace(
        "Gating rationale: TODO: explain literal-use boundary",
        "Gating rationale: flag metaphorical migration praise, protect literal construction",
    )
    report = report.replace("TODO: paste gate tails from verify.", (FIXTURES / "sample-gate-results.md").read_text(encoding="utf-8").rstrip())
    (BUNDLE / "report.md").write_text(report, encoding="utf-8")


def case_verify_red_and_todo() -> None:
    scaffold()
    proc = run(["python3", "scripts/contribute.py", "verify", "--bundle", str(BUNDLE), "--no-gates"])
    if proc.returncode == 0 or "TODO" not in proc.stdout + proc.stderr:
        print(proc.stdout + proc.stderr)
        raise SystemExit(1)
    fill_report()
    proc = run(["python3", "scripts/contribute.py", "verify", "--bundle", str(BUNDLE), "--no-gates"])
    if proc.returncode != 0 or "red-first: ok" not in proc.stdout:
        print(proc.stdout + proc.stderr)
        raise SystemExit(1)
    print("CONTRIB-05 ok")


def case_report_golden() -> None:
    scaffold()
    fill_report()
    proc = run(["python3", "scripts/contribute.py", "report", "--bundle", str(BUNDLE)])
    if proc.returncode != 0:
        print(proc.stdout + proc.stderr)
        raise SystemExit(1)
    expected = (ROOT / "evals" / "golden" / "contrib_report.md").read_text(encoding="utf-8").rstrip()
    assert_equal(proc.stdout.rstrip(), expected, "report")
    print("CONTRIB-06 ok")


def case_determinism() -> None:
    scaffold()
    first = (BUNDLE / "row_fn.json").read_text(encoding="utf-8") + (BUNDLE / "manifest.json").read_text(encoding="utf-8")
    scaffold()
    second = (BUNDLE / "row_fn.json").read_text(encoding="utf-8") + (BUNDLE / "manifest.json").read_text(encoding="utf-8")
    assert_equal(second, first, "determinism")
    print("CONTRIB-07 ok")


def case_missing_bundle() -> None:
    proc = run(["python3", "scripts/contribute.py", "report", "--bundle", ".unslop/contrib/does-not-exist"])
    if proc.returncode != 2:
        print(proc.stdout + proc.stderr)
        raise SystemExit(1)
    print("CONTRIB-08 ok")


def case_capitalized_tell_assertion() -> None:
    reset_bundle()
    proc = run(
        [
            "python3",
            "scripts/contribute.py",
            "scaffold",
            "--snippet",
            "evals/fixtures/contrib/capitalized-tell.txt",
            "--tell",
            "Let that sink in",
            "--category",
            "emphasis_crutch",
            "--pattern-name",
            "let-that-sink-in",
            "--date",
            "2026-07-06",
        ]
    )
    if proc.returncode != 0:
        print(proc.stdout + proc.stderr)
        raise SystemExit(1)
    row = json.loads((CAP_BUNDLE / "row_fn.json").read_text(encoding="utf-8"))
    assert_equal(row["assertions"][1]["value"], "let that sink in", "lowercased assertion")
    report = (CAP_BUNDLE / "report.md").read_text(encoding="utf-8")
    for before, after in (
        ("TODO: source genre", "release note"),
        (
            "TODO: explain why this phrase is a reusable AI-writing tell in 2-4 sentences.",
            "`Let that sink in` is a stock emphasis command that talks down to the reader instead of adding evidence.",
        ),
        ("Pattern added: TODO: regex or phrase for `Let that sink in`", "Pattern added: `let that sink in`"),
        ("Severity: TODO: hard or soft", "Severity: hard"),
        ("Gating rationale: TODO: explain literal-use boundary", "Gating rationale: exact stock command"),
        ("TODO: paste gate tails from verify.", "manual no-gates verification"),
    ):
        report = report.replace(before, after)
    (CAP_BUNDLE / "report.md").write_text(report, encoding="utf-8")
    proc = run(["python3", "scripts/contribute.py", "verify", "--bundle", str(CAP_BUNDLE), "--no-gates"])
    if proc.returncode != 0 or "red-first: already green" not in proc.stdout:
        print(proc.stdout + proc.stderr)
        raise SystemExit(1)
    print("CONTRIB-09 ok")


def case_structure_precheck() -> None:
    proc = run(["python3", "scripts/contribute.py", "precheck", "evals/fixtures/contrib/structure-only.txt"])
    if proc.returncode != 3:
        print(proc.stdout + proc.stderr)
        raise SystemExit(1)
    data = json.loads(proc.stdout)
    metrics = [finding["category"] for finding in data["findings"]]
    if "connective_paragraph_openers" not in metrics:
        print(proc.stdout + proc.stderr)
        raise SystemExit(1)
    print("CONTRIB-10 ok")


CASES = {
    "CONTRIB-01": case_precheck_covered,
    "CONTRIB-02": case_precheck_clean,
    "CONTRIB-03": case_scaffold,
    "CONTRIB-04": case_redaction_tell,
    "CONTRIB-05": case_verify_red_and_todo,
    "CONTRIB-06": case_report_golden,
    "CONTRIB-07": case_determinism,
    "CONTRIB-08": case_missing_bundle,
    "CONTRIB-09": case_capitalized_tell_assertion,
    "CONTRIB-10": case_structure_precheck,
}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", nargs="?", choices=sorted(CASES))
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    if args.all:
        snapshots = snapshot_bundles()
        result = run_contract("contrib", CASES)
        restore_bundles(snapshots)
        restored = snapshot_bundles() == snapshots
        print(f"contrib bundles restored: {str(restored).lower()}")
        return result if restored else 1
    if args.case is None:
        parser.error("choose a case or --all")
    CASES[args.case]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
