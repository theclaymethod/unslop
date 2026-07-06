#!/usr/bin/env python3
"""Voice scorer regression checks for WP10a."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICE = ROOT / "evals" / "fixtures" / "voice"
AUTHORS = ["amara", "boris", "celia"]


def run_score(profile, candidate, seed=17, samples=None):
    cmd = [
        "python3", "scripts/voice_score.py",
        "--profile", str(VOICE / "profiles" / f"{profile}.json"),
        "--impostors", str(VOICE / "impostors"),
        "--seed", str(seed),
    ]
    if samples:
        cmd += ["--samples", str(samples)]
    cmd.append(str(candidate))
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    return json.loads(proc.stdout)


def matrix():
    rows = {}
    for profile in AUTHORS:
        rows[profile] = {}
        for author in AUTHORS:
            candidate = VOICE / "authors" / author / "doc5.md"
            rows[profile][author] = run_score(profile, candidate)["composite"]
    return rows


def print_matrix(rows):
    print("3x3 separation matrix (composite; lower is more profile-like)")
    print("profile\\candidate amara boris celia")
    for profile in AUTHORS:
        vals = " ".join(f"{rows[profile][author]:.6f}" for author in AUTHORS)
        print(f"{profile} {vals}")


def check_separation():
    rows = matrix()
    print_matrix(rows)
    ok = True
    for profile in AUTHORS:
        own = rows[profile][profile]
        ok = ok and all(own < rows[profile][other] for other in AUTHORS if other != profile)
    for author in AUTHORS:
        own = rows[author][author]
        ok = ok and all(own < rows[profile][author] for profile in AUTHORS if profile != author)
    return 0 if ok else 1


def check_gi():
    ok = True
    for profile in AUTHORS:
        own = run_score(profile, VOICE / "authors" / profile / "doc5.md")["gi"]
        print(f"{profile} own GI {own:.6f}")
        for author in AUTHORS:
            if author == profile:
                continue
            cross = run_score(profile, VOICE / "authors" / author / "doc5.md")["gi"]
            print(f"{profile} vs {author} GI {cross:.6f}")
            ok = ok and own > cross
    return 0 if ok else 1


def check_gaming():
    genuine = run_score("amara", VOICE / "authors" / "amara" / "doc5.md")
    stuffed = run_score("amara", VOICE / "stuffed_boris_for_amara.md")
    print(f"genuine composite={genuine['composite']:.6f} GI={genuine['gi']:.6f}")
    print(f"stuffed composite={stuffed['composite']:.6f} GI={stuffed['gi']:.6f}")
    return 0 if stuffed["composite"] > genuine["composite"] and stuffed["gi"] < genuine["gi"] else 1


def check_copy(expect_violation):
    if expect_violation:
        candidate = VOICE / "copy_lift.md"
        data = run_score("amara", candidate, samples=VOICE / "authors" / "amara")
    else:
        candidate = VOICE / "authors" / "amara" / "doc5.md"
        with tempfile.TemporaryDirectory() as td:
            sample = Path(td) / "amara"
            sample.mkdir()
            for idx in range(1, 5):
                (sample / f"doc{idx}.md").write_text((VOICE / "authors" / "amara" / f"doc{idx}.md").read_text())
            data = run_score("amara", candidate, samples=sample)
    print(json.dumps(data["copy_gate"], sort_keys=True))
    return 0 if data["copy_gate"]["violation"] is expect_violation else 1


def check_determinism():
    cand = VOICE / "authors" / "celia" / "doc5.md"
    one = run_score("celia", cand, seed=101)["composite"]
    two = run_score("celia", cand, seed=101)["composite"]
    print(f"{one:.12f}\n{two:.12f}")
    return 0 if one == two else 1


def check_short():
    with tempfile.NamedTemporaryFile("w", suffix=".txt") as f:
        f.write("Tiny note. Too short to trust.")
        f.flush()
        data = run_score("amara", Path(f.name))
    print(json.dumps({"low_confidence": data["low_confidence"], "sentence_emd": data["distances"]["sentence_emd"]}))
    return 0 if data["low_confidence"] and data["distances"]["sentence_emd"] is None else 1


def check_profiles():
    ok = True
    for author in AUTHORS:
        with tempfile.TemporaryDirectory() as td:
            sample = Path(td) / author
            sample.mkdir()
            for idx in range(1, 5):
                (sample / f"doc{idx}.md").write_text((VOICE / "authors" / author / f"doc{idx}.md").read_text())
            out = Path(td) / "profile.json"
            proc = subprocess.run(["python3", "scripts/voice_profile.py", str(sample), "-o", str(out)], cwd=ROOT, text=True, capture_output=True)
            if proc.returncode != 0:
                print(proc.stderr)
                return proc.returncode
            expected = (VOICE / "profiles" / f"{author}.json").read_text()
            got = out.read_text()
            if got != expected:
                print(f"profile drift: {author}")
                ok = False
    print("profiles ok" if ok else "profiles drifted")
    return 0 if ok else 1


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--separation", action="store_true")
    parser.add_argument("--gi", action="store_true")
    parser.add_argument("--gaming", action="store_true")
    parser.add_argument("--copy-violation", action="store_true")
    parser.add_argument("--copy-clean", action="store_true")
    parser.add_argument("--determinism", action="store_true")
    parser.add_argument("--short", action="store_true")
    parser.add_argument("--profiles", action="store_true")
    args = parser.parse_args(argv)
    if args.separation:
        return check_separation()
    if args.gi:
        return check_gi()
    if args.gaming:
        return check_gaming()
    if args.copy_violation:
        return check_copy(True)
    if args.copy_clean:
        return check_copy(False)
    if args.determinism:
        return check_determinism()
    if args.short:
        return check_short()
    if args.profiles:
        return check_profiles()
    parser.error("choose a check")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
