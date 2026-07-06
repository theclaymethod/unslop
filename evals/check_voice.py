#!/usr/bin/env python3
"""Voice scorer regression checks for WP10a."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from _check_support import ROOT  # noqa: E402

SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import voice_profile  # noqa: E402
import voice_score  # noqa: E402

VOICE = ROOT / "evals" / "fixtures" / "voice"
AUTHORS = ["amara", "boris", "celia"]


def run_score(profile, candidate, seed=17, samples=None):
    """In-process equivalent of scripts/voice_score.py's CLI: builds and
    returns the same result dict main() would print, without the subprocess
    and JSON-serialization round trip."""
    profile_path = VOICE / "profiles" / f"{profile}.json"
    impostors_path = VOICE / "impostors"
    if not profile_path.exists() or not impostors_path.is_dir():
        print("missing profile or impostors", file=sys.stderr)
        raise SystemExit(2)
    try:
        text = voice_score.read_candidate(str(candidate))
    except FileNotFoundError as e:
        print(f"missing candidate: {e}", file=sys.stderr)
        raise SystemExit(2)
    profile_data = json.loads(profile_path.read_text())
    feats = voice_profile.feature_bundle(text)
    low = feats["total_words"] < 150
    impostors = voice_score.impostor_features(str(impostors_path))
    dist = voice_score.distances(profile_data, feats)
    imp_dist = [voice_score.distances(profile_data, f) for _, f in impostors]
    zs = voice_score.zscores(dist, imp_dist)
    zsum = sum(
        voice_score.WEIGHTS[k] * max(-3.0, min(3.0, zs[k] if zs[k] is not None else 0.0))
        for k in voice_score.WEIGHTS
    )
    gi = voice_score.gi_score(profile_data, feats, impostors, seed) if impostors else 0.0
    result = {
        "candidate_words": feats["total_words"],
        "low_confidence": low,
        "distances": {k: (None if low and k in {"sentence_emd", "mtld"} else v) for k, v in dist.items()},
        "z_scores": {k: (None if low and k in {"sentence_emd", "mtld"} else v) for k, v in zs.items()},
        "gi": gi,
        "composite": 0.5 * (1 - gi) + 0.5 * zsum,
    }
    if samples:
        result["copy_gate"] = voice_score.copy_gate(text, samples)
    return result


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
            profile = voice_profile.build_profile(sample)
            got = json.dumps(profile, indent=2, sort_keys=True) + "\n"
            expected = (VOICE / "profiles" / f"{author}.json").read_text()
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
