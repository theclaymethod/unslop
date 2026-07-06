#!/usr/bin/env python3
"""Deterministic checks for the teach/mimic feature (MIMIC-* and CARD-* rows).

Each subcommand drives the real CLIs (voice_profile.py, voice_card.py,
run_mimic_refine.py, mimic_stats.py) against committed fixtures and returns 0
on the expected behavior, 1 otherwise. The mimic rows run the refine loop in
dry-run (``--candidates-dir``) mode so the whole suite is LLM-free.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "evals" / "fixtures" / "mimic"
SAMPLES = FIX / "samples"
DIV_SAMPLES = FIX / "div_samples"
SMALL = FIX / "small_samples"
DRAFT = FIX / "draft.md"
CANDS = FIX / "candidates"
STATS = FIX / "stats"
NO_NUMBERS = FIX / "card_corpora" / "no_numbers"


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)


def refine(scenario, out, seed, iterations, samples=SAMPLES, extra=None):
    cmd = [
        "python3", "evals/run_mimic_refine.py",
        "--samples", str(samples), "--draft", str(DRAFT),
        "--out", str(out), "--seed", str(seed),
        "--iterations", str(iterations),
        "--candidates-dir", str(CANDS / scenario),
    ] + (extra or [])
    proc = run(cmd)
    return proc


def load_report(out):
    return json.loads((Path(out) / "report.json").read_text())


# ----------------------------- MIMIC checks -----------------------------

def check_acceptance():
    with tempfile.TemporaryDirectory() as td:
        proc = refine("accept", td, 1, 3)
        if proc.returncode != 0:
            print(proc.stderr)
            return 1
        r = load_report(td)
        accepted_after_first = any(i["accepted"] for i in r["iterations"][1:])
        ok = (r["best_candidate"] == "cand01.md" and accepted_after_first
              and r["iterations"][2]["accepted"])
        print(json.dumps({"best_score": r["best_score"],
                          "accepted": [i["accepted"] for i in r["iterations"]],
                          "stop_reason": r["stop_reason"]}, sort_keys=True))
        return 0 if ok else 1


def check_patience():
    with tempfile.TemporaryDirectory() as td:
        proc = refine("patience", td, 1, 3, extra=["--patience", "2"])
        if proc.returncode != 0:
            print(proc.stderr)
            return 1
        r = load_report(td)
        print(json.dumps({"stop_reason": r["stop_reason"],
                          "reward_hacking_warning": r["reward_hacking_warning"]},
                         sort_keys=True))
        return 0 if r["stop_reason"] == "patience" and not r["reward_hacking_warning"] else 1


def check_stuffed_attack():
    """A marker-stuffed candidate that clears every hard gate must still lose to
    honest prose under the GI-bearing composite (F1 regression). cand01 is honest,
    cand02 is the punctuation/repetition-stuffed attack that games a raw weighted
    distance but not the full composite."""
    with tempfile.TemporaryDirectory() as td:
        proc = refine("stuffed", td, 1, 1)
        if proc.returncode != 0:
            print(proc.stderr)
            return 1
        r = load_report(td)
        cands = {c["name"]: c for c in r["iterations"][0]["candidates"]}
        honest = cands.get("cand01.md", {})
        stuffed = cands.get("cand02.md", {})
        both_passed = honest.get("passed") and stuffed.get("passed")
        honest_dev = honest.get("dev_score")
        stuffed_dev = stuffed.get("dev_score")
        ok = (both_passed
              and r["best_candidate"] == "cand01.md"
              and honest_dev is not None and stuffed_dev is not None
              and stuffed_dev > honest_dev)
        print(json.dumps({
            "best_candidate": r["best_candidate"],
            "honest_passed_gates": honest.get("passed"),
            "stuffed_passed_gates": stuffed.get("passed"),
            "honest_composite": honest_dev,
            "stuffed_composite": stuffed_dev,
            "margin": (round(stuffed_dev - honest_dev, 6)
                       if honest_dev is not None and stuffed_dev is not None else None),
        }, sort_keys=True))
        return 0 if ok else 1


def check_live_path():
    """The LIVE generation path (F3): a mock generator invoked via --generate-cmd
    drives the same gate/score/accept pipeline as the dry-run, producing the same
    report shape and honoring acceptance."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        dry = td / "dry"
        live = td / "live"
        p_dry = refine("accept", dry, 1, 3)
        cmd = [
            "python3", "evals/run_mimic_refine.py",
            "--samples", str(SAMPLES), "--draft", str(DRAFT),
            "--out", str(live), "--seed", "1", "--iterations", "3", "--beam", "2",
            "--generate-cmd", "python3 evals/fixtures/mimic/mock_generator.py",
        ]
        p_live = run(cmd)
        if p_dry.returncode != 0 or p_live.returncode != 0:
            print(p_dry.stderr, p_live.stderr)
            return 1
        rd = load_report(dry)
        rl = load_report(live)
        shape_keys = {"iterations", "best_candidate", "best_score", "stop_reason",
                      "reward_hacking_warning", "directives", "split"}
        shape_ok = shape_keys <= set(rl)
        beam_ok = len(rl["iterations"][0]["candidates"]) == 2
        accept_ok = [i["accepted"] for i in rl["iterations"]] == [i["accepted"] for i in rd["iterations"]]
        score_ok = rl["best_score"] == rd["best_score"]
        final_ok = (live / "final.md").exists()
        print(json.dumps({
            "live_best_score": rl["best_score"],
            "dry_best_score": rd["best_score"],
            "accepted": [i["accepted"] for i in rl["iterations"]],
            "beam_candidates": len(rl["iterations"][0]["candidates"]),
            "final_written": final_ok,
        }, sort_keys=True))
        return 0 if shape_ok and beam_ok and accept_ok and score_ok and final_ok else 1


def check_divergence():
    with tempfile.TemporaryDirectory() as td:
        proc = refine("divergence", td, 4, 3, samples=DIV_SAMPLES,
                      extra=["--patience", "3"])
        if proc.returncode != 0:
            print(proc.stderr)
            return 1
        r = load_report(td)
        a = [i["best_a_score"] for i in r["iterations"]]
        dev = [i["best_dev_score"] for i in r["iterations"]]
        # A improving (down) while DEV worsening (up) across the run.
        trend = a[0] > a[1] > a[2] and dev[0] < dev[1] < dev[2]
        ok = (r["stop_reason"] == "divergence" and r["reward_hacking_warning"] and trend)
        print(json.dumps({"stop_reason": r["stop_reason"],
                          "reward_hacking_warning": r["reward_hacking_warning"],
                          "a_scores": a, "dev_scores": dev}, sort_keys=True))
        return 0 if ok else 1


def _rejection_reason(scenario, out, seed):
    proc = refine(scenario, out, seed, 1)
    if proc.returncode != 0:
        print(proc.stderr)
        return None
    r = load_report(out)
    rej = r["iterations"][0]["gate_rejections"]
    print(json.dumps(rej, sort_keys=True))
    return rej


def check_copy_gate():
    with tempfile.TemporaryDirectory() as td:
        rej = _rejection_reason("copygate", td, 1)
        return 0 if rej and any(x["reason"] == "copy_gate" for x in rej) else 1


def check_fact_gate():
    with tempfile.TemporaryDirectory() as td:
        rej = _rejection_reason("factgate", td, 1)
        return 0 if rej and any(x["reason"] == "preservation" for x in rej) else 1


def check_determinism():
    with tempfile.TemporaryDirectory() as td:
        # Same --out both times so card_path (which embeds the out dir) matches.
        out = Path(td) / "run"
        p1 = refine("accept", out, 1, 3)
        first = (out / "report.json").read_text()
        p2 = refine("accept", out, 1, 3)
        second = (out / "report.json").read_text()
        if p1.returncode or p2.returncode:
            print(p1.stderr, p2.stderr)
            return 1
        print(f"len1={len(first)} len2={len(second)} identical={first == second}")
        return 0 if first == second else 1


def check_stats():
    win = run(["python3", "evals/mimic_stats.py", str(STATS / "win.json"), "--seed", "7"])
    null = run(["python3", "evals/mimic_stats.py", str(STATS / "null.json"), "--seed", "7"])
    if win.returncode or null.returncode:
        print(win.stderr, null.stderr)
        return 1
    w = json.loads(win.stdout)
    n = json.loads(null.stdout)
    print(json.dumps({"win_improved": w["improved"], "null_improved": n["improved"]},
                     sort_keys=True))
    return 0 if w["improved"] and not n["improved"] else 1


def check_split_refusal():
    proc = refine("accept", tempfile.mkdtemp(), 1, 3, samples=SMALL)
    print(f"exit={proc.returncode} stderr={proc.stderr.strip()}")
    return 0 if proc.returncode == 2 else 1


def check_directives():
    with tempfile.TemporaryDirectory() as td:
        proc = refine("accept", td, 1, 3)
        if proc.returncode != 0:
            print(proc.stderr)
            return 1
        r = load_report(td)
        dirs = r["directives"]
        keys_ok = all({"metric", "directive", "card_amendment"} <= set(d) for d in dirs)
        iter_dirs = any(i["directives"] for i in r["iterations"])
        print(json.dumps({"n_directives": len(dirs),
                          "metrics": [d["metric"] for d in dirs]}, sort_keys=True))
        return 0 if dirs and keys_ok and iter_dirs else 1


# ------------------------------ CARD checks -----------------------------

def _build_profile(samples, out):
    return run(["python3", "scripts/voice_profile.py", str(samples), "-o", str(out)])


def _build_card(profile, samples, out, name="amara", provenance=False):
    cmd = ["python3", "scripts/voice_card.py", "--profile", str(profile),
           "--samples", str(samples), "--out", str(out), "--name", name]
    if provenance:
        cmd.append("--provenance")
    return run(cmd)


def _card_word_count(text):
    return len(re.findall(r"[A-Za-z0-9']+", text))


def check_card_determinism():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        prof = td / "p.json"
        _build_profile(SAMPLES, prof)
        _build_card(prof, SAMPLES, td / "o1")
        _build_card(prof, SAMPLES, td / "o2")
        a = (td / "o1" / "card.md").read_text()
        b = (td / "o2" / "card.md").read_text()
        sheets_a = {p.name: p.read_text() for p in (td / "o1" / "card").glob("*.md")}
        sheets_b = {p.name: p.read_text() for p in (td / "o2" / "card").glob("*.md")}
        print(f"card_identical={a == b} sheets_identical={sheets_a == sheets_b}")
        return 0 if a == b and sheets_a == sheets_b else 1


def check_card_budget():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        prof = td / "p.json"
        _build_profile(SAMPLES, prof)
        _build_card(prof, SAMPLES, td / "o")
        card = (td / "o" / "card.md").read_text()
        wc = _card_word_count(card)
        required = ["Rhythm:", "Contractions:", "Never:", "Openers:",
                    "When writing", "| Situation | Sheet |"]
        missing = [s for s in required if s not in card]
        print(f"word_count={wc} missing_sections={missing}")
        return 0 if wc <= 300 and not missing else 1


def check_card_facts():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        prof = td / "p.json"
        _build_profile(SAMPLES, prof)
        _build_card(prof, SAMPLES, td / "o")
        card = (td / "o" / "card.md").read_text()
        profile = json.loads(prof.read_text())
        med = int(profile["sentence_lengths"]["median"])
        rate = f"{profile['contraction_rate']:.3f}"
        m = re.search(r"median sentence (\d+) words", card)
        card_med = int(m.group(1)) if m else None
        rate_ok = f"rate {rate}" in card
        print(f"profile_median={med} card_median={card_med} rate={rate} rate_in_card={rate_ok}")
        return 0 if card_med == med and rate_ok else 1


def check_card_layout():
    """Full teach layout: profile.json, card.md, provenance.json + hash verify."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        prof = td / "profile.json"
        _build_profile(SAMPLES, prof)
        _build_card(prof, SAMPLES, td, provenance=True)
        files = [prof, td / "card.md", td / "provenance.json"]
        exist = all(f.exists() for f in files)
        prov = json.loads((td / "provenance.json").read_text())
        hashes_ok = True
        for entry in prov["samples"]:
            actual = hashlib.sha256((SAMPLES / entry["file"]).read_bytes()).hexdigest()
            if actual != entry["sha256"]:
                hashes_ok = False
        print(f"files_exist={exist} doc_count={prov['doc_count']} hashes_ok={hashes_ok}")
        return 0 if exist and hashes_ok and prov["doc_count"] == 5 else 1


_NEVER_MARKS = {
    "semicolons": ";", "exclamation points": "!", "colons": ":",
    "hyphenated dashes": "-", "parentheticals": "(",
}


def check_card_never_does():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        prof = td / "p.json"
        _build_profile(SAMPLES, prof)
        _build_card(prof, SAMPLES, td / "o")
        card = (td / "o" / "card.md").read_text()
        profile = json.loads(prof.read_text())
        m = re.search(r"^Never: (.+)$", card, re.M)
        if not m:
            print("no Never line")
            return 1
        claims = [c.strip().rstrip(".") for c in m.group(1).split(";")]
        bad = []
        for claim in claims:
            mark = _NEVER_MARKS.get(claim)
            if mark is None or profile["punctuation"].get(mark, 0.0) != 0.0:
                bad.append(claim)
        print(f"claims={claims} violated={bad}")
        return 0 if claims and not bad else 1


def check_coverage_gap():
    """A sample set with no numeric writing must flag numbers-data as a gap."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        prof = td / "p.json"
        _build_profile(NO_NUMBERS, prof)
        proc = run(["python3", "scripts/voice_card.py", "--profile", str(prof),
                    "--samples", str(NO_NUMBERS), "--coverage"])
        matrix = json.loads(proc.stdout)
        covered = matrix["numbers-data"]["covered"]
        print(json.dumps({"numbers-data": matrix["numbers-data"]}, sort_keys=True))
        return 0 if covered is False else 1


def check_no_fabrication():
    """An uncovered dimension gets no sheet and is named uncovered in card.md."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        prof = td / "p.json"
        _build_profile(NO_NUMBERS, prof)
        _build_card(prof, NO_NUMBERS, td / "o", name="tester")
        card = (td / "o" / "card.md").read_text()
        sheet = td / "o" / "card" / "numbers-data.md"
        m = re.search(r"^Uncovered .*: (.+)$", card, re.M)
        listed = m and "numbers-data" in m.group(1)
        print(f"sheet_exists={sheet.exists()} listed_uncovered={bool(listed)}")
        return 0 if not sheet.exists() and listed else 1


def check_card_profile_mismatch():
    """F2: a supplied profile that does not describe the --samples must be caught.
    A committed 4-doc Amara profile against the 5-doc Amara samples dir is a
    named mismatch and a non-zero exit; voice_card must not silently emit a card."""
    with tempfile.TemporaryDirectory() as td:
        proc = run([
            "python3", "scripts/voice_card.py",
            "--profile", str(ROOT / "evals" / "fixtures" / "voice" / "profiles" / "amara.json"),
            "--samples", str(ROOT / "evals" / "fixtures" / "voice" / "authors" / "amara"),
            "--out", td, "--name", "amara",
        ])
        card_written = (Path(td) / "card.md").exists()
        named = "does not match --samples" in proc.stderr and "'" in proc.stderr
        print(f"exit={proc.returncode} named_mismatch={named} card_written={card_written} "
              f"stderr={proc.stderr.strip()}")
        return 0 if proc.returncode == 2 and named and not card_written else 1


CHECKS = {
    "acceptance": check_acceptance,
    "patience": check_patience,
    "divergence": check_divergence,
    "stuffed-attack": check_stuffed_attack,
    "live-path": check_live_path,
    "copy-gate": check_copy_gate,
    "fact-gate": check_fact_gate,
    "determinism": check_determinism,
    "stats": check_stats,
    "split-refusal": check_split_refusal,
    "directives": check_directives,
    "card-determinism": check_card_determinism,
    "card-budget": check_card_budget,
    "card-facts": check_card_facts,
    "card-layout": check_card_layout,
    "card-never-does": check_card_never_does,
    "coverage-gap": check_coverage_gap,
    "no-fabrication": check_no_fabrication,
    "card-profile-mismatch": check_card_profile_mismatch,
}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in CHECKS:
        parser.add_argument(f"--{name}", action="store_true")
    args = parser.parse_args(argv)
    for name, fn in CHECKS.items():
        if getattr(args, name.replace("-", "_")):
            return fn()
    parser.error("choose a check")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
