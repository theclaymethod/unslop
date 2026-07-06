#!/usr/bin/env python3
"""Model-parity harness for the two model-dependent product surfaces.

The unslop pipeline (references/pipeline.md) leans on a model in exactly two
places: Tier-1 pack DETECTION and Tier-2 REPLACEMENT generation. Everything else
is deterministic. This harness measures whether a cheap model matches a strong
model on those two surfaces so the tiering table can be set from data instead of
assumption (see docs product decisions: "MEASURED by evals, not assumed").

Two tasks, both graded deterministically:

  Task A (pack detection): each model reads ONE pack file plus a short seeded
    chunk (the Tier-1 contract) and returns JSON findings. We grade recall of the
    seeded findings and count false findings against a fixed manifest.

  Task B (replacement generation): each model is handed a seeded finding
    (span + rationale) and asked for a span-minimal replacement. We grade with the
    co-writer contract: the replacement removes the flagged tell without adding a
    new one (both scanners), preserves must-keep constraints, and stays minimal.

Config-driven model matrix. Entries are {name, kind, model_id}:
  - kind "claude-cli":  runs `claude -p --model <model_id>` (Anthropic spectrum).
  - kind "openrouter":  POSTs to the OpenRouter chat/completions API with the key
    from the macOS keychain (service OPENROUTER_API_KEY); GPT spectrum and more.

Modes:
  live       (default) call each model over the network and grade the responses.
  --dry-run  grade PRE-CANNED responses from a --responses fixture file. No
             network, fully deterministic; this is what the PARITY-* eval rows use.
  --no-network  take the live path but force every model call to fail, proving a
             missing key / dead network degrades gracefully (status "unavailable")
             and never breaks the suite.

Output: a per-model / per-task score table as JSON on stdout (default), or a
markdown summary (--format md), or both. Grading is deterministic: --format json
emits nothing but the JSON object so eval rows can assert on it.

Exit codes match scripts/*.py: 0 ran, 1 bad config/args, 2 a required file is
missing. The parity VERDICT is data in the payload, not the exit code.

DO NOT run the live matrix casually. Per CLAUDE.md / references/pipeline.md, any
change to the co-writer, mimic, or detector-pack features must run this across
both the GPT and Anthropic spectrums before merge.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
PACKS = ROOT / "references" / "packs"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
KEYCHAIN_SERVICE = "OPENROUTER_API_KEY"

# Documented default matrix — spans the GPT spectrum (openrouter) and the
# Anthropic spectrum (claude-cli). Not run unless the caller asks for live mode.
DEFAULT_MODELS = [
    {"name": "gpt-4o-mini", "kind": "openrouter", "model_id": "openai/gpt-4o-mini"},
    {"name": "gpt-4o", "kind": "openrouter", "model_id": "openai/gpt-4o"},
    {"name": "claude-haiku", "kind": "claude-cli", "model_id": "claude-3-5-haiku-latest"},
    {"name": "claude-sonnet", "kind": "claude-cli", "model_id": "claude-sonnet-4-5"},
]

# --------------------------------------------------------------------------- #
# Seeded corpus. Fixed on purpose: parity is only meaningful against a frozen
# corpus. Each Task-A fixture seeds exactly two findings from ONE pack family;
# two of the six are register-guard cases (the load-bearing preservation family).
# --------------------------------------------------------------------------- #

TASK_A_FIXTURES = [
    {
        "id": "A1",
        "pack": "pack-phrases-core",
        "text": "Here's the thing: this quarterly result really underscores the "
                "importance of shipping fast.",
        "manifest": [
            {"any_of": ["here's the thing"]},
            {"any_of": ["underscores the importance", "underscores the importance of"]},
        ],
    },
    {
        "id": "A2",
        "pack": "pack-phrases-core",
        "text": "This release unlocks seamless cross-functional synergy across every team.",
        "manifest": [
            {"any_of": ["seamless"]},
            {"any_of": ["synergy", "cross-functional synergy"]},
        ],
    },
    {
        "id": "A3",
        "pack": "pack-voice",
        "text": "Not the tool. The team. The result: alignment across the whole org.",
        "manifest": [
            {"any_of": ["not the tool. the team.", "not the tool. the team"]},
            {"any_of": ["the result: alignment", "result: alignment"]},
        ],
    },
    {
        "id": "A4",
        "pack": "pack-voice",
        "text": "We build things that matter. Emit tokens. Ship bytes. That is the whole job.",
        "manifest": [
            {"any_of": ["emit tokens. ship bytes.", "emit tokens. ship bytes"]},
            {"any_of": ["things that matter", "build things that matter"]},
        ],
    },
    {
        # register-guard case #1: safety/medical hedges that must survive a rewrite
        "id": "A5",
        "pack": "pack-register-guards",
        "text": "Users should never store secrets in client-side code. The trial may "
                "cause drowsiness in some patients.",
        "manifest": [
            {"any_of": ["never store secrets", "never"]},
            {"any_of": ["may cause", "may", "some patients"]},
        ],
    },
    {
        # register-guard case #2: legal negation/scope
        "id": "A6",
        "pack": "pack-register-guards",
        "text": "The incident arguably does not rise to gross negligence under Section "
                "12(b), unless the party consents in writing.",
        "manifest": [
            {"any_of": [
                "arguably does not rise to gross negligence",
                "does not rise to gross negligence",
                "arguably",
            ]},
            {"any_of": ["unless the party consents", "unless"]},
        ],
    },
]

# Task-B fixtures: a seeded finding (span inside context + rationale). The model
# returns ONLY a replacement for the span. B5 doubles as the register-guard
# preservation case — fixing the opener must not strip the load-bearing "never".
TASK_B_FIXTURES = [
    {
        "id": "B1",
        "context": "Here's the thing: the service returns a 200 status code on success.",
        "span": "Here's the thing: the",
        "rule": "throat_clearing",
        "rationale": "Throat-clearing opener; cut it and start with the claim.",
    },
    {
        "id": "B2",
        "context": "This release unlocks seamless integration with 3 external providers.",
        "span": "seamless",
        "rule": "academic_excess",
        "rationale": "Empty polish word; drop or replace with a concrete adjective.",
    },
    {
        "id": "B3",
        "context": "The data speaks for itself in these 5 charts.",
        "span": "speaks for itself",
        "rule": "false_agency",
        "rationale": "Data has no agency; state what the charts show.",
    },
    {
        "id": "B4",
        "context": "Latency dropped from 900ms to 120ms, which underscores the importance "
                   "of caching.",
        "span": "which underscores the importance of caching",
        "rule": "significance_inflation",
        "rationale": "Inflated significance tail; state the cause plainly.",
    },
    {
        # register-guard preservation: the fix touches the opener, NOT the "never".
        "id": "B5",
        "context": "Let's dive in: users must never store secrets in client-side code.",
        "span": "Let's dive in: users",
        "rule": "throat_clearing",
        "rationale": "Cut the throat-clearing opener; keep the security rule exact.",
    },
    {
        "id": "B6",
        "context": "In conclusion, the deploy finished in 4 minutes with 0 errors.",
        "span": "In conclusion, the",
        "rule": "conclusion_scaffold",
        "rationale": "Generic conclusion scaffold; start with the fact.",
    },
]


# --------------------------------------------------------------------------- #
# Response parsing
# --------------------------------------------------------------------------- #

def _strip_fences(raw):
    """Drop markdown code fences a model may wrap JSON in."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)
    return text.strip()


def parse_findings(raw):
    """Best-effort parse of a Task-A response into a list of finding dicts.

    Tolerant to fences, a wrapping {"findings": [...]}, or JSONL. Returns [] when
    nothing parses (an empty response is a legitimate zero-recall result, not a
    crash).
    """
    if not raw or not raw.strip():
        return []
    text = _strip_fences(raw)
    for candidate in (text, _extract_array(text)):
        if candidate is None:
            continue
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and "findings" in data:
            data = data["findings"]
        if isinstance(data, dict):
            data = [data]
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    # JSONL fallback: one JSON object per line.
    out = []
    for line in text.splitlines():
        line = line.strip().rstrip(",")
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _extract_array(text):
    start = text.find("[")
    end = text.rfind("]")
    if 0 <= start < end:
        return text[start:end + 1]
    return None


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


# --------------------------------------------------------------------------- #
# Task A grading (deterministic recall + false findings vs manifest)
# --------------------------------------------------------------------------- #

def grade_task_a(fixture, raw):
    findings = parse_findings(raw)
    got_spans = [_norm(f.get("span", "")) for f in findings]
    matched_flags = [False] * len(got_spans)
    matched_expected = 0
    for exp in fixture["manifest"]:
        alts = [_norm(a) for a in exp["any_of"]]
        hit = False
        for i, gs in enumerate(got_spans):
            if not gs:
                continue
            if any(a and (a in gs or gs in a) for a in alts):
                matched_flags[i] = True
                hit = True
        if hit:
            matched_expected += 1
    n_expected = len(fixture["manifest"])
    recall = matched_expected / n_expected if n_expected else 0.0
    false_findings = sum(1 for i, gs in enumerate(got_spans)
                         if gs and not matched_flags[i])
    return {
        "recall": round(recall, 6),
        "false_findings": false_findings,
        "n_expected": n_expected,
        "n_matched": matched_expected,
        "n_returned": len(got_spans),
    }


# --------------------------------------------------------------------------- #
# Scanner helpers for Task B
# --------------------------------------------------------------------------- #

def _run_script(rel_args, stdin_text):
    return subprocess.run(
        ["python3", str(SCRIPTS / rel_args[0]), *rel_args[1:]],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=30,
    )


def _banned_signal(text):
    """Set of (category, phrase) violations the banned-phrase scanner reports."""
    proc = _run_script(["banned_phrase_scan.py"], text)
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return set()
    return {(v.get("category", ""), _norm(v.get("phrase", "")))
            for v in data.get("violations", [])}


def _structure_signal(text):
    """Set of structure-scan flags for the text."""
    proc = _run_script(["structure_scan.py"], text)
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return set()
    flags = data.get("flags", data.get("flagged", []))
    if isinstance(flags, dict):
        flags = [k for k, v in flags.items() if v]
    return {("structure", _norm(str(f))) for f in flags}


def _preservation_ok(original, transformed):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        op = Path(d) / "original.txt"
        tp = Path(d) / "transformed.txt"
        op.write_text(original)
        tp.write_text(transformed)
        proc = _run_script(["validate_preservation.py", str(op), str(tp)], "")
    return proc.returncode == 0


def grade_task_b(fixture, replacement):
    context = fixture["context"]
    span = fixture["span"]
    if replacement is None:
        replacement = ""
    idx = context.find(span)
    if idx < 0:
        # Fixture defect, not a model failure. Surface it explicitly.
        return {
            "pass": False,
            "span_found": False,
            "scanners_ok": False,
            "constraints_preserved": False,
            "span_minimal": False,
            "detail": "seed span not found in context",
        }
    new_context = context[:idx] + replacement + context[idx + len(span):]

    before = _banned_signal(context) | _structure_signal(context)
    after = _banned_signal(new_context) | _structure_signal(new_context)
    added = after - before
    removed = before - after
    scanners_ok = (not added) and bool(removed)

    constraints_preserved = _preservation_ok(context, new_context)

    span_words = max(1, len(span.split()))
    repl_words = len(replacement.split())
    span_minimal = repl_words <= max(3, 2 * span_words)

    passed = scanners_ok and constraints_preserved and span_minimal
    return {
        "pass": passed,
        "span_found": True,
        "scanners_ok": scanners_ok,
        "added_signals": sorted(f"{c}:{p}" for c, p in added),
        "removed_signals": sorted(f"{c}:{p}" for c, p in removed),
        "constraints_preserved": constraints_preserved,
        "span_minimal": span_minimal,
        "replacement_words": repl_words,
    }


# --------------------------------------------------------------------------- #
# Prompts (Tier-1 / co-writer contract)
# --------------------------------------------------------------------------- #

def build_prompt_a(fixture):
    pack_text = (PACKS / f"{fixture['pack']}.md").read_text()
    return (
        "You are a Tier-1 unslop detector. You may only use the pack below. "
        "Read the chunk and return a JSON array of findings, each "
        '{"span":"...","rule":"...","pack":"...","severity":"hard|soft","note":"..."}. '
        "Report only spans this pack owns. Do not rewrite. Return JSON only.\n\n"
        f"=== PACK: {fixture['pack']} ===\n{pack_text}\n\n"
        f"=== CHUNK ===\n{fixture['text']}\n"
    )


def build_prompt_b(fixture):
    return (
        "You are an unslop co-writer. Below is one flagged span inside its "
        "context and why it was flagged. Return ONLY a span-minimal replacement "
        "string for the flagged span (no quotes, no JSON, no explanation). The "
        "replacement must remove the tell, keep every fact/number/negation in the "
        "context intact, and change as little as possible.\n\n"
        f"CONTEXT: {fixture['context']}\n"
        f"FLAGGED SPAN: {fixture['span']}\n"
        f"RULE: {fixture['rule']}\n"
        f"WHY: {fixture['rationale']}\n"
    )


# --------------------------------------------------------------------------- #
# Model calls (live). Every path is wrapped so a missing key / dead network
# yields (None, reason) instead of raising.
# --------------------------------------------------------------------------- #

def keychain_key(service):
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    key = proc.stdout.strip()
    return key or None


def call_openrouter(model_id, prompt, timeout=60):
    key = keychain_key(KEYCHAIN_SERVICE)
    if not key:
        return None, "no OPENROUTER_API_KEY in keychain"
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"], None
    except (urllib.error.URLError, KeyError, ValueError, OSError, TimeoutError) as e:
        return None, f"openrouter error: {e}"


def call_claude_cli(model_id, prompt, timeout=120):
    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", model_id],
            input=prompt,
            capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as e:
        return None, f"claude cli error: {e}"
    if proc.returncode != 0:
        return None, f"claude cli exit {proc.returncode}: {proc.stderr.strip()[:200]}"
    return proc.stdout, None


def call_model(entry, prompt, no_network):
    if no_network:
        return None, "no-network mode"
    kind = entry.get("kind")
    model_id = entry.get("model_id", "")
    if kind == "openrouter":
        return call_openrouter(model_id, prompt)
    if kind == "claude-cli":
        return call_claude_cli(model_id, prompt)
    return None, f"unknown kind {kind!r}"


# --------------------------------------------------------------------------- #
# Matrix run
# --------------------------------------------------------------------------- #

def _score_a(per_fixture):
    recalls = [r["recall"] for r in per_fixture.values()]
    return {
        "mean_recall": round(sum(recalls) / len(recalls), 6) if recalls else 0.0,
        "total_false_findings": sum(r["false_findings"] for r in per_fixture.values()),
        "n_fixtures": len(per_fixture),
        "fixtures": per_fixture,
    }


def _score_b(per_fixture):
    n_pass = sum(1 for r in per_fixture.values() if r["pass"])
    return {
        "pass_rate": round(n_pass / len(per_fixture), 6) if per_fixture else 0.0,
        "n_pass": n_pass,
        "n_fixtures": len(per_fixture),
        "fixtures": per_fixture,
    }


def _canned_response(responses, model_name, task, fixture_id):
    return (responses.get(model_name, {}).get(task, {}) or {}).get(fixture_id)


def run_matrix(models, tasks, dry_run, no_network, responses):
    result = {
        "mode": "dry-run" if dry_run else ("no-network" if no_network else "live"),
        "tasks": list(tasks),
        "n_fixtures": {"A": len(TASK_A_FIXTURES), "B": len(TASK_B_FIXTURES)},
        "models": {},
    }
    for entry in models:
        name = entry["name"]
        model_out = {"kind": entry.get("kind", "canned"), "status": "ok"}
        errors = []

        if "A" in tasks:
            per = {}
            for fx in TASK_A_FIXTURES:
                if dry_run:
                    raw = _canned_response(responses, name, "A", fx["id"]) or ""
                else:
                    raw, err = call_model(entry, build_prompt_a(fx), no_network)
                    if err:
                        errors.append(f"A/{fx['id']}: {err}")
                        raw = ""
                per[fx["id"]] = grade_task_a(fx, raw)
            model_out["A"] = _score_a(per)

        if "B" in tasks:
            per = {}
            for fx in TASK_B_FIXTURES:
                if dry_run:
                    repl = _canned_response(responses, name, "B", fx["id"])
                    if repl is None:
                        repl = ""
                else:
                    repl, err = call_model(entry, build_prompt_b(fx), no_network)
                    if err:
                        errors.append(f"B/{fx['id']}: {err}")
                        repl = ""
                per[fx["id"]] = grade_task_b(fx, repl)
            model_out["B"] = _score_b(per)

        # In a live/no-network run, a model that never produced a usable response
        # is "unavailable" — recorded, not fatal.
        if not dry_run and errors and len(errors) >= len(tasks) * len(TASK_A_FIXTURES):
            model_out["status"] = "unavailable"
        if errors:
            model_out["errors"] = errors
        result["models"][name] = model_out
    return result


# --------------------------------------------------------------------------- #
# Markdown summary
# --------------------------------------------------------------------------- #

def to_markdown(result):
    lines = []
    lines.append(f"# Model Parity — {result['mode']} run")
    lines.append("")
    lines.append(f"Fixtures: {result['n_fixtures']['A']} detection, "
                 f"{result['n_fixtures']['B']} replacement.")
    lines.append("")
    if "A" in result["tasks"]:
        lines.append("## Task A — pack detection")
        lines.append("")
        lines.append("| Model | Kind | Status | Mean recall | False findings |")
        lines.append("|---|---|---|---:|---:|")
        for name, m in result["models"].items():
            a = m.get("A", {})
            lines.append(f"| {name} | {m['kind']} | {m['status']} | "
                         f"{a.get('mean_recall', '-')} | "
                         f"{a.get('total_false_findings', '-')} |")
        lines.append("")
    if "B" in result["tasks"]:
        lines.append("## Task B — replacement generation")
        lines.append("")
        lines.append("| Model | Kind | Status | Pass rate | Passed/Total |")
        lines.append("|---|---|---|---:|---:|")
        for name, m in result["models"].items():
            b = m.get("B", {})
            passed = (f"{b.get('n_pass', '-')}/{b.get('n_fixtures', '-')}"
                      if b else "-")
            lines.append(f"| {name} | {m['kind']} | {m['status']} | "
                         f"{b.get('pass_rate', '-')} | {passed} |")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _load_json_file(path, what):
    p = Path(path)
    if not p.exists():
        print(f"missing {what}: {path}", file=sys.stderr)
        raise SystemExit(2)
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, ValueError) as e:
        print(f"malformed {what} ({path}): {e}", file=sys.stderr)
        raise SystemExit(1)


def parse_args(argv):
    p = argparse.ArgumentParser(description="unslop model-parity harness")
    p.add_argument("--models", metavar="FILE",
                   help="JSON file: list of {name,kind,model_id} model entries")
    p.add_argument("--responses", metavar="FILE",
                   help="dry-run canned responses (may also carry a 'models' list)")
    p.add_argument("--dry-run", action="store_true",
                   help="grade canned --responses; no network, deterministic")
    p.add_argument("--no-network", action="store_true",
                   help="take the live path but force every call to fail (graceful-degrade test)")
    p.add_argument("--check-determinism", action="store_true",
                   help="grade twice and add {'deterministic': bool} to the payload")
    p.add_argument("--task", choices=["A", "B", "both"], default="both",
                   help="which task(s) to run")
    p.add_argument("--format", choices=["json", "md", "both"], default="json",
                   help="output format (json is pure JSON for eval assertions)")
    return p.parse_args(argv)


def resolve_models(args, responses):
    if args.models:
        models = _load_json_file(args.models, "models file")
        if isinstance(models, dict) and "models" in models:
            models = models["models"]
        return models
    if isinstance(responses, dict) and responses.get("models"):
        return responses["models"]
    if args.dry_run:
        # Derive canned model names from the response payload.
        resp = (responses or {}).get("responses", responses or {})
        return [{"name": n, "kind": "canned"} for n in resp]
    return DEFAULT_MODELS


def main(argv):
    args = parse_args(argv)
    tasks = ["A", "B"] if args.task == "both" else [args.task]

    responses = {}
    if args.responses:
        payload = _load_json_file(args.responses, "responses file")
        responses = payload.get("responses", payload) if isinstance(payload, dict) else {}
        resp_models = payload if isinstance(payload, dict) else {}
    else:
        resp_models = {}

    if args.dry_run and not args.responses:
        print("--dry-run needs --responses FILE", file=sys.stderr)
        return 1

    models = resolve_models(args, resp_models)
    if not models:
        print("no models resolved", file=sys.stderr)
        return 1

    result = run_matrix(models, tasks, args.dry_run, args.no_network, responses)

    if args.check_determinism:
        again = run_matrix(models, tasks, args.dry_run, args.no_network, responses)
        canon = lambda r: json.dumps(r, sort_keys=True)
        result["deterministic"] = canon(result) == canon(again)

    if args.format in ("json", "both"):
        print(json.dumps(result, indent=2))
    if args.format in ("md", "both"):
        if args.format == "both":
            print()
        print(to_markdown(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
