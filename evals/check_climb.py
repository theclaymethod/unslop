#!/usr/bin/env python3
"""Deterministic checks for the macro-structure climb (CLIMB-* rows).

Each subcommand drives the real evals/run_structure_climb.py loop against a
committed climb fixture through the MOCK generator (--generate-cmd points at
evals/fixtures/climb/mock_generate.py), so the whole suite is LLM-free and
offline. It asserts the loop's honest terminal states and the directive
builder's location-naming, and returns 0 on the expected behavior, 1 otherwise.

  --converge      loop climbs to clean; violations fall monotonically, exit 0
  --capped        loop never cleans; honest capped terminal, nonzero exit
  --control       single pass (max-rounds 1) stays dirty -- the loop is load-bearing
  --preservation  a round that eats a fact aborts, naming the missing constraint
  --directives    directives name WHERE and WHAT for a known fixture
  --coverage      every macro flag both scanners can emit maps to a directive
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from _check_support import ROOT

FIX = ROOT / "evals" / "fixtures" / "climb"
PROMPT = FIX / "task_prompt.txt"
MOCK = FIX / "mock_generate.py"

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "evals"))
import run_structure_climb as climb  # noqa: E402


def run_climb(scenario, out, max_rounds=4):
    cmd = [
        "python3", "evals/run_structure_climb.py",
        "--prompt-file", str(PROMPT),
        "--out", str(out),
        "--generate-cmd", f"python3 {MOCK} --scenario {scenario}",
        "--max-rounds", str(max_rounds),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=120)
    return proc


def load_report(out):
    return json.loads((Path(out) / "report.json").read_text())


def check_converge():
    with tempfile.TemporaryDirectory() as td:
        proc = run_climb("converge", td)
        r = load_report(td)
        traj = r["violation_trajectory"]
        monotonic = all(b <= a for a, b in zip(traj, traj[1:]))
        ok = (proc.returncode == climb.EXIT_CONVERGED
              and r["terminal_state"] == "converged"
              and r["converged"] is True
              and r["final_violations"] == 0
              and r["initial_violations"] > 0
              and monotonic
              # every non-final round preserved facts against the round-0 anchor
              and all(rd["preservation"]["passed"] for rd in r["rounds"][1:]))
        print(json.dumps({"exit": proc.returncode, "terminal": r["terminal_state"],
                          "trajectory": traj, "monotonic": monotonic}, sort_keys=True))
        return 0 if ok else 1


def check_capped():
    with tempfile.TemporaryDirectory() as td:
        proc = run_climb("capped", td, max_rounds=4)
        r = load_report(td)
        ok = (proc.returncode == climb.EXIT_CAPPED
              and r["terminal_state"] == "capped"
              and r["converged"] is False
              and r["rounds_used"] == 4
              and r["final_violations"] > 0)
        print(json.dumps({"exit": proc.returncode, "terminal": r["terminal_state"],
                          "final_violations": r["final_violations"],
                          "trajectory": r["violation_trajectory"]}, sort_keys=True))
        return 0 if ok else 1


def check_control():
    """A single pass (max-rounds 1) on the SAME scenario the loop converges on
    stays dirty: proof the loop, not the generator, is what recovers macro."""
    with tempfile.TemporaryDirectory() as td:
        single = run_climb("converge", td + "/one", max_rounds=1)
        r1 = load_report(td + "/one")
        looped = run_climb("converge", td + "/loop", max_rounds=4)
        r4 = load_report(td + "/loop")
        ok = (single.returncode == climb.EXIT_CAPPED
              and r1["terminal_state"] == "capped"
              and r1["final_violations"] > 0
              and looped.returncode == climb.EXIT_CONVERGED
              and r4["converged"] is True)
        print(json.dumps({"single_pass_exit": single.returncode,
                          "single_pass_violations": r1["final_violations"],
                          "looped_exit": looped.returncode,
                          "looped_converged": r4["converged"]}, sort_keys=True))
        return 0 if ok else 1


def check_preservation():
    with tempfile.TemporaryDirectory() as td:
        proc = run_climb("preservation", td)
        r = load_report(td)
        last = r["rounds"][-1]
        missing = [m["value"] for m in last["preservation"]["missing"]] if last["preservation"] else []
        ok = (proc.returncode == climb.EXIT_PRESERVATION
              and r["terminal_state"] == "preservation_violation"
              and r["converged"] is False
              and last["preservation"] is not None
              and last["preservation"]["passed"] is False
              and missing)
        print(json.dumps({"exit": proc.returncode, "terminal": r["terminal_state"],
                          "missing": missing}, sort_keys=True))
        return 0 if ok else 1


def check_directives():
    """Directives must NAME the offending location, not echo a generic tip."""
    with tempfile.TemporaryDirectory() as td:
        run_climb("converge", td)
        r = load_report(td)
        dirs = {d["metric"]: d["directive"] for d in r["rounds"][0]["directives"]}
        checks = {
            # coda directive names the final paragraph and the stock opener
            "conclusion_coda": ("final paragraph" in dirs.get("conclusion_coda", "").lower()
                                and "Ultimately," in dirs.get("conclusion_coda", "")),
            # connective directive names specific paragraph numbers + the words
            "connective_paragraph_openers": (
                "paragraph 2" in dirs.get("connective_paragraph_openers", "")
                and "Moreover" in dirs.get("connective_paragraph_openers", "")),
            # callback directive names the recapped opening vocabulary
            "callback_content": ('"bookshelf"' in dirs.get("callback_content", "")
                                 and "recap loop" in dirs.get("callback_content", "")),
            # scaffold directive names the cue words on the body paragraphs
            "scaffold_opener_share": "Furthermore" in dirs.get("scaffold_opener_share", ""),
        }
        keys_ok = all({"source", "metric", "directive"} <= set(d)
                      for d in r["rounds"][0]["directives"])
        ok = keys_ok and all(checks.values())
        print(json.dumps({"named": checks, "keys_ok": keys_ok}, sort_keys=True))
        return 0 if ok else 1


# Flag metrics each scanner can emit (kept in lockstep with the scanner source:
# structure_scan.scan()'s flag() calls and silhouette_scan's SUGGESTIONS keys).
STRUCTURE_FLAG_METRICS = {
    "sentence_burstiness", "conclusion_coda", "bold_colon_listicle",
    "one_line_staccato", "connective_paragraph_openers", "every_template_openers",
    "signpost_density", "opener_repetition", "participial_closer_share",
}
SILHOUETTE_FLAG_METRICS = {
    "scaffold_opener_share", "role_entropy_bits", "heading_preview",
    "preview_fulfillment", "callback_content",
}


def check_coverage():
    """Every macro flag both scanners can emit must map to a directive builder,
    and the live converge fixture must realize a 1:1 flag->directive coverage."""
    import silhouette_scan  # noqa: E402
    # Registry covers every documented scanner flag metric.
    struct_missing = STRUCTURE_FLAG_METRICS - set(climb.STRUCTURE_DIRECTIVES)
    silh_missing = SILHOUETTE_FLAG_METRICS - set(climb.SILHOUETTE_DIRECTIVES)
    # Guard against the scanner growing a new metric this map never learned about.
    silh_source = set(silhouette_scan.SUGGESTIONS)
    silh_drift = silh_source - set(climb.SILHOUETTE_DIRECTIVES)

    # Live 1:1 coverage on the richest dirty fixture.
    with tempfile.TemporaryDirectory() as td:
        run_climb("converge", td)
        r = load_report(td)
        rd0 = r["rounds"][0]
        n_flags = len(rd0["structure_flags"]) + len(rd0["silhouette_flags"])
        n_dirs = len(rd0["directives"])
        realized_ok = n_flags > 0 and n_dirs == n_flags

    ok = not struct_missing and not silh_missing and not silh_drift and realized_ok
    print(json.dumps({
        "structure_unmapped": sorted(struct_missing),
        "silhouette_unmapped": sorted(silh_missing),
        "silhouette_scanner_drift": sorted(silh_drift),
        "converge_flags": n_flags, "converge_directives": n_dirs,
    }, sort_keys=True))
    return 0 if ok else 1


CHECKS = {
    "converge": check_converge,
    "capped": check_capped,
    "control": check_control,
    "preservation": check_preservation,
    "directives": check_directives,
    "coverage": check_coverage,
}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in CHECKS:
        parser.add_argument(f"--{name}", action="store_true")
    args = parser.parse_args(argv)
    for name, fn in CHECKS.items():
        if getattr(args, name):
            return fn()
    parser.error("choose a check")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
